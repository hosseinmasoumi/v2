import json

from . import views


class FixedDashboardView(views.DashboardView):
    """Dashboard wrapper for separated experiment and volume doughnut charts."""

    VOLUME_BUCKETS = ("embankment", "concrete", "asphalt")
    EXPERIMENT_BUCKETS = VOLUME_BUCKETS

    @staticmethod
    def _to_float(value):
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def _empty_volume(cls):
        return {bucket: 0.0 for bucket in cls.VOLUME_BUCKETS}

    @classmethod
    def _empty_experiment_stats(cls):
        return {
            "acceptable": 0,
            "recompact": 0,
            "retest": 0,
            "penalty": 0,
            "demolition": 0,
            "in_progress": 0,
            "pending": 0,
            "total": 0,
        }

    @classmethod
    def _empty_experiment_groups(cls):
        return {bucket: cls._empty_experiment_stats() for bucket in cls.EXPERIMENT_BUCKETS}

    @classmethod
    def _bucket_for_text(cls, text):
        normalized = (text or "").lower().replace(" ", "")
        if "آسفالت" in normalized or "asphalt" in normalized:
            return "asphalt"
        if "بتن" in normalized or "concrete" in normalized:
            return "concrete"
        if (
            "خاک" in normalized
            or "embankment" in normalized
            or "زیراساس" in normalized
            or "زیرمبنا" in normalized
            or "اساس" in normalized
            or "subbase" in normalized
            or "base" in normalized
        ):
            return "embankment"
        return None

    @classmethod
    def _bucket_for_experiment(cls, experiment_request):
        if experiment_request.layer and experiment_request.layer.layer_type:
            bucket = cls._bucket_for_text(experiment_request.layer.layer_type.name)
            if bucket:
                return bucket

        names = []
        names.extend(list(experiment_request.experiment_type.values_list("name", flat=True)))
        names.extend(list(experiment_request.experiment_subtype.values_list("name", flat=True)))
        for name in names:
            bucket = cls._bucket_for_text(name)
            if bucket:
                return bucket
        return None

    @classmethod
    def _project_length_km(cls, project):
        masafat = cls._to_float(getattr(project, "masafat", None))
        if masafat > 0:
            return masafat

        start_km = getattr(project, "start_kilometer", None)
        end_km = getattr(project, "end_kilometer", None)
        if start_km is not None and end_km is not None:
            return max(cls._to_float(end_km) - cls._to_float(start_km), 0)
        return 0.0

    @classmethod
    def _planned_project_volume(cls, project):
        from project.models import ProjectLayer

        totals = cls._empty_volume()
        if not project:
            return totals

        width = cls._to_float(getattr(project, "width", None))
        length_km = cls._project_length_km(project)
        if width <= 0 or length_km <= 0:
            return totals

        layers = ProjectLayer.objects.filter(project=project).select_related("layer_type")
        for layer in layers:
            bucket = cls._bucket_for_text(getattr(layer.layer_type, "name", ""))
            thickness_cm = cls._to_float(getattr(layer, "thickness_cm", None))
            if not bucket or thickness_cm <= 0:
                continue
            totals[bucket] += length_km * 1000 * width * (thickness_cm / 100)
        return totals

    @classmethod
    def _volume_item(cls, done_value, total_value):
        done = round(cls._to_float(done_value), 3)
        total = round(max(cls._to_float(total_value), done), 3)
        return {"done": done, "total": total}

    @staticmethod
    def _latest_response(experiment_request):
        return experiment_request.experimentresponse_set.order_by("-created_at").first()

    @classmethod
    def _has_recompact(cls, experiment_request):
        from experiment.models import ExperimentApproval

        response = cls._latest_response(experiment_request)
        if not response:
            return False
        return response.experimentapproval_set.filter(status=ExperimentApproval.RECOMPACT).exists()

    @classmethod
    def _has_penalty(cls, experiment_request):
        response = cls._latest_response(experiment_request)
        if not response:
            return False
        return response.experimentapproval_set.filter(penalty_percentage__gt=0).exists()

    @classmethod
    def _add_experiment(cls, groups, experiment_request):
        from experiment.models import ExperimentRequest

        bucket = cls._bucket_for_experiment(experiment_request)
        if not bucket:
            return

        stats = groups[bucket]
        actual_status = experiment_request.get_actual_status()

        if actual_status == ExperimentRequest.COMPLETED:
            if bucket == "embankment" and cls._has_recompact(experiment_request):
                stats["recompact"] += 1
            elif bucket in ("concrete", "asphalt") and cls._has_penalty(experiment_request):
                stats["penalty"] += 1
            else:
                stats["acceptable"] += 1
        elif actual_status == ExperimentRequest.REJECTED:
            if bucket == "embankment":
                stats["retest"] += 1
            else:
                stats["demolition"] += 1
        elif actual_status == ExperimentRequest.IN_PROGRESS:
            stats["in_progress"] += 1
        else:
            stats["pending"] += 1

        stats["total"] += 1

    def _filtered_experiments(self):
        from datetime import timedelta
        import jdatetime
        from django.utils import timezone
        from experiment.models import ExperimentRequest

        experiments = ExperimentRequest.objects.all().select_related(
            "project", "layer", "layer__layer_type"
        ).prefetch_related("experiment_type", "experiment_subtype")

        date_from = self.request.GET.get("date_from")
        date_to = self.request.GET.get("date_to")
        days_filter = self.request.GET.get("days")

        if date_from and date_to:
            try:
                from_parts = date_from.replace("/", "-").split("-")
                to_parts = date_to.replace("/", "-").split("-")
                if len(from_parts) == 3 and len(to_parts) == 3:
                    from_obj = jdatetime.date(
                        int(from_parts[0]), int(from_parts[1]), int(from_parts[2])
                    ).togregorian()
                    to_obj = jdatetime.date(
                        int(to_parts[0]), int(to_parts[1]), int(to_parts[2])
                    ).togregorian() + timedelta(days=1)
                    experiments = experiments.filter(request_date__gte=from_obj, request_date__lt=to_obj)
            except Exception:
                pass
        elif days_filter:
            try:
                days = int(days_filter)
                start_date = timezone.now().date() - timedelta(days=days)
                jalali_start = jdatetime.date.fromgregorian(date=start_date)
                experiments = experiments.filter(request_date__year__gte=jalali_start.year)
                if jalali_start.year == jdatetime.date.today().year:
                    experiments = experiments.filter(request_date__month__gte=jalali_start.month)
            except (TypeError, ValueError):
                pass

        return experiments

    @classmethod
    def _serialize_project(cls, project):
        return {"id": project.id, "name": project.name}

    def _build_experiment_payload(self, context):
        from project.models import Project

        payload = {"projects": [], "global": self._empty_experiment_groups()}
        filtered_experiments = self._filtered_experiments()
        project_filter = self.request.GET.get("project")

        for experiment_request in filtered_experiments:
            self._add_experiment(payload["global"], experiment_request)

        if project_filter:
            try:
                projects = Project.objects.filter(id=int(project_filter))
            except (TypeError, ValueError):
                projects = Project.objects.none()
        else:
            projects = [item.get("project") for item in context.get("projects_stats") or [] if item.get("project")]

        for project in projects:
            groups = self._empty_experiment_groups()
            for experiment_request in filtered_experiments.filter(project=project):
                self._add_experiment(groups, experiment_request)
            payload["projects"].append({"project": self._serialize_project(project), "groups": groups})

        return payload

    def _build_volume_payload(self, context):
        payload = {"projects": [], "global": {bucket: {"done": 0, "total": 0} for bucket in self.VOLUME_BUCKETS}}

        for project_stat in context.get("projects_stats") or []:
            project = project_stat.get("project")
            if not project:
                continue
            done_volume = project_stat.get("volume") or {}
            planned_volume = self._planned_project_volume(project)
            payload["projects"].append({
                "project": self._serialize_project(project),
                "volume": {
                    bucket: self._volume_item(done_volume.get(bucket, 0), planned_volume.get(bucket, 0))
                    for bucket in self.VOLUME_BUCKETS
                },
            })

        global_done = context.get("volume_data") or {}
        global_planned = self._empty_volume()
        for project in context.get("all_projects") or []:
            project_planned = self._planned_project_volume(project)
            for bucket in self.VOLUME_BUCKETS:
                global_planned[bucket] += project_planned[bucket]

        payload["global"] = {
            bucket: self._volume_item(global_done.get(bucket, 0), global_planned.get(bucket, 0))
            for bucket in self.VOLUME_BUCKETS
        }
        return payload

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["fixed_dashboard_payload"] = {
            "experiments": self._build_experiment_payload(context),
            "volumes": self._build_volume_payload(context),
        }
        return context

    @staticmethod
    def _dashboard_fix_script(payload):
        payload_json = json.dumps(payload, ensure_ascii=False)
        js = f"""
document.addEventListener('DOMContentLoaded', function() {{
  const payload = {payload_json};
  const root = document.querySelector('.charts-section .row.g-4');
  if (!root || !window.Chart) return;

  const colors = {{
    acceptable: '#4CAF50',
    recompact: '#9C27B0',
    retest: '#F44336',
    penalty: '#FF9800',
    demolition: '#795548',
    in_progress: '#2196F3',
    pending: '#607D8B',
    embankment: '#9C27B0',
    concrete: '#FF9800',
    asphalt: '#2196F3'
  }};

  const titles = {{
    embankment: 'خاکریزی',
    concrete: 'بتن ریزی',
    asphalt: 'آسفالت'
  }};

  const soilStatuses = [
    ['acceptable', 'قابل قبول'],
    ['recompact', 'ری‌کامپکت'],
    ['retest', 'ریتست'],
    ['in_progress', 'در حال انجام'],
    ['pending', 'در حال آزمایش']
  ];

  const concreteAsphaltStatuses = [
    ['acceptable', 'قابل قبول'],
    ['penalty', 'جریمه'],
    ['demolition', 'تخریب'],
    ['in_progress', 'در حال انجام'],
    ['pending', 'در حال آزمایش']
  ];

  function formatNumber(value) {{
    return Number(value || 0).toLocaleString('fa-IR', {{ maximumFractionDigits: 2 }});
  }}

  function chartHtml(canvasId, title, subtitle) {{
    return '<div class="col-6 col-md-4 col-lg-2"><div class="chart-card text-center">' +
      '<div style="max-width: 100px; margin: 0 auto;"><canvas id="' + canvasId + '" width="100" height="100"></canvas></div>' +
      '<h6 class="mt-2 mb-0 small">' + title + '</h6>' +
      '<p class="text-muted small mb-0">' + subtitle + '</p>' +
      '</div></div>';
  }}

  function drawDoughnut(canvasId, value, total, color, label, unitText) {{
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const safeTotal = Math.max(Number(total || 0), Number(value || 0), 0);
    const percentage = safeTotal > 0 ? Math.min(100, Math.round((Number(value || 0) / safeTotal) * 100)) : 0;
    const remaining = Math.max(0, 100 - percentage);
    new Chart(canvas, {{
      type: 'doughnut',
      data: {{
        labels: [label, 'باقیمانده'],
        datasets: [{{
          data: [percentage, remaining],
          backgroundColor: [Number(value || 0) > 0 ? color : '#CCCCCC', '#E0E0E0'],
          borderWidth: 0
        }}]
      }},
      options: {{
        responsive: true,
        maintainAspectRatio: true,
        cutout: '70%',
        plugins: {{
          legend: {{ display: false }},
          tooltip: {{
            callbacks: {{
              label: function(context) {{
                if (context.dataIndex === 0) {{
                  return label + ': ' + formatNumber(value) + unitText + ' (' + percentage + '%)';
                }}
                return 'باقیمانده: ' + remaining + '%';
              }}
            }}
          }}
        }}
      }},
      plugins: [{{
        id: 'centerText' + canvasId,
        beforeDraw: function(chart) {{
          const ctx = chart.ctx;
          const x = chart.chartArea.left + (chart.chartArea.right - chart.chartArea.left) / 2;
          const y = chart.chartArea.top + (chart.chartArea.bottom - chart.chartArea.top) / 2;
          ctx.save();
          ctx.font = 'bold 14px Arial';
          ctx.fillStyle = '#333';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillText(percentage + '%', x, y);
          ctx.restore();
        }}
      }}]
    }});
  }}

  function experimentGroupHtml(prefix, groupKey, stats) {{
    const statusList = groupKey === 'embankment' ? soilStatuses : concreteAsphaltStatuses;
    let html = '<div class="mb-4"><h6 class="fw-bold border-bottom pb-2">' + titles[groupKey] + '</h6><div class="row g-3">';
    statusList.forEach(function(item) {{
      const key = item[0];
      const label = item[1];
      html += chartHtml(prefix + '-' + groupKey + '-' + key, label, formatNumber(stats[key] || 0) + ' مورد');
    }});
    html += '</div></div>';
    return html;
  }}

  function experimentCardHtml(item, index) {{
    const suffix = item.project ? item.project.id : 'global';
    const title = item.project ? 'وضعیت آزمایشات - ' + item.project.name : 'وضعیت آزمایشات (کلی)';
    let html = '<div class="col-12"><div class="card shadow-sm border-0 rounded-4">' +
      '<div class="card-header bg-light"><h5 class="mb-0"><i class="bi bi-pie-chart me-2"></i>' + title + '</h5></div>' +
      '<div class="card-body">';
    Object.keys(titles).forEach(function(groupKey) {{
      html += experimentGroupHtml('experiment-' + suffix + '-' + index, groupKey, item.groups[groupKey]);
    }});
    html += '</div></div></div>';
    return html;
  }}

  function volumeCardHtml(item, index) {{
    const suffix = item.project ? item.project.id : 'global';
    const title = item.project ? 'حجم کل کار انجام شده - ' + item.project.name : 'حجم کل کار انجام شده (کلی)';
    let html = '<div class="col-12"><div class="card shadow-sm border-0 rounded-4">' +
      '<div class="card-header bg-light"><h5 class="mb-0"><i class="bi bi-bar-chart me-2"></i>' + title + '</h5></div>' +
      '<div class="card-body"><div class="row g-3">';
    Object.keys(titles).forEach(function(groupKey) {{
      const itemData = item.volume[groupKey] || {{done: 0, total: 0}};
      html += chartHtml('volume-fixed-' + suffix + '-' + index + '-' + groupKey, titles[groupKey], formatNumber(itemData.done) + ' از ' + formatNumber(itemData.total) + ' متر³');
    }});
    html += '</div></div></div></div>';
    return html;
  }}

  const experimentItems = (payload.experiments.projects && payload.experiments.projects.length) ? payload.experiments.projects : [{{project: null, groups: payload.experiments.global}}];
  const volumeItems = (payload.volumes.projects && payload.volumes.projects.length) ? payload.volumes.projects : [{{project: null, volume: payload.volumes.global}}];
  let html = '';

  experimentItems.forEach(function(item, index) {{ html += experimentCardHtml(item, index); }});
  volumeItems.forEach(function(item, index) {{ html += volumeCardHtml(item, index); }});
  root.innerHTML = html;

  experimentItems.forEach(function(item, index) {{
    const suffix = item.project ? item.project.id : 'global';
    Object.keys(titles).forEach(function(groupKey) {{
      const stats = item.groups[groupKey];
      const statusList = groupKey === 'embankment' ? soilStatuses : concreteAsphaltStatuses;
      statusList.forEach(function(statusItem) {{
        const key = statusItem[0];
        const label = statusItem[1];
        drawDoughnut('experiment-' + suffix + '-' + index + '-' + groupKey + '-' + key, stats[key] || 0, stats.total || 0, colors[key], label, ' مورد');
      }});
    }});
  }});

  volumeItems.forEach(function(item, index) {{
    const suffix = item.project ? item.project.id : 'global';
    Object.keys(titles).forEach(function(groupKey) {{
      const itemData = item.volume[groupKey] || {{done: 0, total: 0}};
      drawDoughnut('volume-fixed-' + suffix + '-' + index + '-' + groupKey, itemData.done, itemData.total, colors[groupKey], titles[groupKey], ' متر³');
    }});
  }});
}});
"""
        return "<" + "script>" + js + "<" + "/script>"

    def render_to_response(self, context, **response_kwargs):
        response = super().render_to_response(context, **response_kwargs)
        if hasattr(response, "render") and not response.is_rendered:
            response.render()

        charset = getattr(response, "charset", None) or "utf-8"
        html = response.content.decode(charset)
        script = self._dashboard_fix_script(context.get("fixed_dashboard_payload", {}))

        if "</body>" in html:
            html = html.replace("</body>", script + "</body>", 1)
        else:
            html += script

        response.content = html.encode(charset)
        return response
