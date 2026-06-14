import logging
from decimal import Decimal

from django.apps import AppConfig
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

logger = logging.getLogger(__name__)


class ExperimentConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'experiment'

    def ready(self):
        from project.models import ProjectLayer
        from . import models, views

        def get_approval_status_by_role(self):
            status = {}
            for role in self.get_required_approval_roles():
                approvers = self.get_approvers_for_role(role)
                approvals = self.experimentapproval_set.filter(role=role).filter(
                    Q(approver__in=approvers) | Q(approver__is_superuser=True)
                )
                if not approvers and not approvals.exists():
                    status[role] = 'تعریف نشده'
                elif not approvals.exists():
                    status[role] = 'در انتظار'
                elif approvals.filter(status=models.ExperimentApproval.REJECTED).exists():
                    status[role] = 'رد شده'
                elif approvals.filter(status=models.ExperimentApproval.RECOMPACT).exists():
                    status[role] = 'ری‌کامپکت'
                elif approvals.filter(status=models.ExperimentApproval.APPROVED, approver__is_superuser=True).exists():
                    status[role] = 'تایید شده'
                elif approvers and approvals.filter(status=models.ExperimentApproval.APPROVED, approver__in=approvers).count() == len(approvers):
                    status[role] = 'تایید شده'
                else:
                    status[role] = 'در انتظار'
            return status

        def is_fully_approved(self):
            status = self.get_approval_status_by_role()
            return all(value == 'تایید شده' for value in status.values() if value != 'تعریف نشده')

        def approved_ranges_cover(covered_ranges, start, end):
            tolerance = Decimal('0.001')
            current_end = start
            for covered_start, covered_end in sorted(covered_ranges, key=lambda item: item[0]):
                if covered_end <= current_end:
                    continue
                if covered_start > current_end + tolerance:
                    return False
                current_end = max(current_end, covered_end)
                if current_end >= end - tolerance:
                    return True
            return current_end >= end - tolerance

        def find_blocking_lower_layers(project, target_layer, ranges):
            if not ranges:
                return []
            lower_layers = ProjectLayer.objects.filter(
                project=project,
                order_from_top__gt=target_layer.order_from_top,
            ).order_by('order_from_top')
            blocking = []
            for lower in lower_layers:
                layer_blocked = False
                for start, end in ranges:
                    start_decimal = Decimal(str(start))
                    end_decimal = Decimal(str(end))
                    if end_decimal <= start_decimal:
                        continue
                    overlap_requests = models.ExperimentRequest.objects.filter(
                        project=project,
                        layer=lower,
                        start_kilometer__lt=end_decimal,
                        end_kilometer__gt=start_decimal,
                    ).order_by('start_kilometer')
                    if not overlap_requests.exists():
                        continue
                    covered_ranges = []
                    for lower_request in overlap_requests:
                        request_start = Decimal(str(lower_request.start_kilometer))
                        request_end = Decimal(str(lower_request.end_kilometer))
                        overlap_start = max(start_decimal, request_start)
                        overlap_end = min(end_decimal, request_end)
                        if overlap_start >= overlap_end:
                            continue
                        if any(response.is_fully_approved() for response in lower_request.experimentresponse_set.all()):
                            covered_ranges.append((overlap_start, overlap_end))
                    if not approved_ranges_cover(covered_ranges, start_decimal, end_decimal):
                        layer_blocked = True
                        break
                if layer_blocked:
                    blocking.append(lower)
            return blocking

        models.ExperimentResponse.get_approval_status_by_role = get_approval_status_by_role
        models.ExperimentResponse.is_fully_approved = is_fully_approved
        views.find_blocking_lower_layers = find_blocking_lower_layers


def get_user_approval_roles(experiment_response, user):
    required_roles = list(experiment_response.get_required_approval_roles())
    if user.is_superuser:
        return required_roles
    user_roles = []
    for role in required_roles:
        approvers = experiment_response.get_approvers_for_role(role)
        logger.debug("Role: %s, Approvers: %s, Current user: %s", role, [approver.username for approver in approvers], user.username)
        if user in approvers:
            user_roles.append(role)
    return user_roles


@login_required
def experiment_approval_create(request, response_id):
    from . import forms, models
    experiment_response = get_object_or_404(models.ExperimentResponse, pk=response_id)
    user_roles = get_user_approval_roles(experiment_response, request.user)
    if not user_roles:
        logger.warning("User %s cannot approve response %s. Required roles: %s", request.user.username, experiment_response.pk, experiment_response.get_required_approval_roles())
        messages.error(request, 'شما مجاز به ثبت تاییدیه برای این پاسخ آزمایش نیستید.')
        return redirect('experiment:experiment_response_detail', pk=response_id)
    if request.method == 'POST':
        post_data = request.POST.copy()
        if not post_data.get('experiment_response'):
            post_data['experiment_response'] = experiment_response.pk
        if not post_data.get('role') and len(user_roles) == 1:
            post_data['role'] = user_roles[0]
        form = forms.ExperimentApprovalForm(post_data, user_roles=user_roles)
        if form.is_valid():
            approval = form.save(commit=False)
            approval.experiment_response = experiment_response
            approval.approver = request.user
            if not approval.role and user_roles:
                approval.role = user_roles[0]
            try:
                approval.save()
            except IntegrityError:
                form.add_error(None, 'برای این نقش قبلا توسط این کاربر تاییدیه ثبت شده است.')
            else:
                notified_users = set()
                for role in experiment_response.get_required_approval_roles():
                    for user in experiment_response.get_approvers_for_role(role):
                        if user and user.id not in notified_users:
                            models.Notification.objects.create(user=user, experiment_request=experiment_response.experiment_request, message=f'یک تاییدیه جدید برای پاسخ آزمایش پروژه {experiment_response.experiment_request.project.name} ثبت شد.')
                            notified_users.add(user.id)
                messages.success(request, 'تایید آزمایش با موفقیت ثبت شد.')
                return redirect('experiment:experiment_response_detail', pk=response_id)
    else:
        initial = {'experiment_response': experiment_response.pk}
        if len(user_roles) == 1:
            initial['role'] = user_roles[0]
        form = forms.ExperimentApprovalForm(initial=initial, user_roles=user_roles)
    return render(request, 'experiment/experiment_approval_form.html', {'form': form, 'experiment_response': experiment_response, 'user_roles': user_roles})
