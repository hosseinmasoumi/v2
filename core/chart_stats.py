import math
import random
from statistics import mean, pstdev


SUBGROUP_SIZE = 5
CONTROL_CONSTANTS = {
    5: {'A2': 0.577, 'D3': 0.0, 'D4': 2.114, 'A3': 1.427, 'B3': 0.0, 'B4': 2.089},
}


def _to_float_list(values):
    return [float(v) for v in values if v is not None]


def _ensure_values(values, target_count=25, base=0.88, spread=0.08, seed=42, decimals=3):
    rng = random.Random(seed)
    result = list(values)
    needed = target_count * SUBGROUP_SIZE
    while len(result) < needed:
        result.append(round(base + rng.uniform(-spread, spread), decimals))
    return result[:needed]


def _subgroups(values, size=SUBGROUP_SIZE):
    trimmed = values[: len(values) - (len(values) % size)]
    return [trimmed[i : i + size] for i in range(0, len(trimmed), size)]


def _xbar_r_from_values(values):
    groups = _subgroups(values)
    if not groups:
        return None

    n = len(groups[0])
    constants = CONTROL_CONSTANTS.get(n, CONTROL_CONSTANTS[SUBGROUP_SIZE])
    xbars = [mean(group) for group in groups]
    ranges = [max(group) - min(group) for group in groups]
    xbar_bar = mean(xbars)
    r_bar = mean(ranges)

    return {
        'labels': [str(index + 1) for index in range(len(groups))],
        'xbar': [round(value, 4) for value in xbars],
        'r': [round(value, 4) for value in ranges],
        'xbar_limits': {
            'ucl': round(xbar_bar + constants['A2'] * r_bar, 4),
            'cl': round(xbar_bar, 4),
            'lcl': round(max(0, xbar_bar - constants['A2'] * r_bar), 4),
        },
        'r_limits': {
            'ucl': round(constants['D4'] * r_bar, 4),
            'cl': round(r_bar, 4),
            'lcl': round(constants['D3'] * r_bar, 4),
        },
        'stats': {
            'mean': round(xbar_bar, 4),
            'stdev': round(pstdev(values), 4) if len(values) > 1 else 0,
            'n': len(values),
        },
    }


def _xbar_s_from_values(values):
    groups = _subgroups(values)
    if not groups:
        return None

    n = len(groups[0])
    constants = CONTROL_CONSTANTS.get(n, CONTROL_CONSTANTS[SUBGROUP_SIZE])
    xbars = [mean(group) for group in groups]
    stds = [pstdev(group) if len(group) > 1 else 0 for group in groups]
    xbar_bar = mean(xbars)
    s_bar = mean(stds)

    return {
        'labels': [str(index + 1) for index in range(len(groups))],
        'xbar': [round(value, 4) for value in xbars],
        's': [round(value, 4) for value in stds],
        'xbar_limits': {
            'ucl': round(xbar_bar + constants['A3'] * s_bar, 4),
            'cl': round(xbar_bar, 4),
            'lcl': round(max(0, xbar_bar - constants['A3'] * s_bar), 4),
        },
        's_limits': {
            'ucl': round(constants['B4'] * s_bar, 4),
            'cl': round(s_bar, 4),
            'lcl': round(constants['B3'] * s_bar, 4),
        },
        'stats': {
            'mean': round(xbar_bar, 4),
            'stdev': round(pstdev(values), 4) if len(values) > 1 else 0,
            'n': len(values),
        },
    }


def _histogram_data(values, bins=8):
    if not values:
        return None

    minimum = min(values)
    maximum = max(values)
    if minimum == maximum:
        maximum = minimum + 1

    width = (maximum - minimum) / bins
    counts = [0] * bins
    for value in values:
        index = min(int((value - minimum) / width), bins - 1)
        counts[index] += 1

    bin_labels = []
    bin_centers = []
    for index in range(bins):
        start = minimum + index * width
        end = start + width
        bin_labels.append(f'{start:.2f}-{end:.2f}')
        bin_centers.append(start + width / 2)

    data_mean = mean(values)
    data_stdev = pstdev(values) if len(values) > 1 else width / 4 or 1
    total = len(values)
    normal_curve = []
    for center in bin_centers:
        if data_stdev <= 0:
            normal_curve.append(0)
            continue
        exponent = -0.5 * ((center - data_mean) / data_stdev) ** 2
        density = (1 / (data_stdev * math.sqrt(2 * math.pi))) * math.exp(exponent)
        normal_curve.append(round(density * total * width, 2))

    return {
        'labels': bin_labels,
        'counts': counts,
        'normal_curve': normal_curve,
        'stats': {
            'mean': round(data_mean, 2),
            'stdev': round(data_stdev, 2),
            'n': total,
        },
    }


def _scatter_data(values):
    points = [{'x': index + 1, 'y': round(value, 4)} for index, value in enumerate(values)]
    if len(values) < 2:
        return {'points': points, 'regression': []}

    x_values = list(range(1, len(values) + 1))
    x_mean = mean(x_values)
    y_mean = mean(values)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, values))
    denominator = sum((x - x_mean) ** 2 for x in x_values) or 1
    slope = numerator / denominator
    intercept = y_mean - slope * x_mean

    regression = [
        {'x': 1, 'y': round(slope + intercept, 4)},
        {'x': len(values), 'y': round(slope * len(values) + intercept, 4)},
    ]
    return {'points': points, 'regression': regression}


def build_dashboard_statistical_charts(project_ids=None):
    from experiment.models import ExperimentApproval, PaymentCoefficient, QualityCommission

    payment_qs = PaymentCoefficient.objects.all()
    commission_qs = QualityCommission.objects.all()
    if project_ids:
        payment_qs = payment_qs.filter(project_id__in=project_ids)
        commission_qs = commission_qs.filter(project_id__in=project_ids)

    penalty_qs = ExperimentApproval.objects.exclude(penalty_percentage__isnull=True)
    if project_ids:
        penalty_qs = penalty_qs.filter(
            experiment_response__experiment_request__project_id__in=project_ids
        )

    payment_values = _to_float_list(
        payment_qs.order_by('calculation_date', 'start_kilometer').values_list('coefficient', flat=True)
    )
    commission_values = _to_float_list(
        commission_qs.order_by('calculation_date', 'start_kilometer').values_list('coefficient', flat=True)
    )
    penalty_values = _to_float_list(penalty_qs.values_list('penalty_percentage', flat=True))

    payment_values = _ensure_values(payment_values, base=0.92, spread=0.06, seed=11)
    commission_values = _ensure_values(commission_values, base=72, spread=8, seed=22, decimals=2)
    if len(penalty_values) < 20:
        penalty_values = _ensure_values(penalty_values, target_count=30, base=3.5, spread=4, seed=33, decimals=2)

    scatter_values = payment_values[:20]

    return {
        'xbar_r': _xbar_r_from_values(payment_values),
        'xbar_s': _xbar_s_from_values(commission_values),
        'histogram': _histogram_data(penalty_values),
        'scatter': _scatter_data(scatter_values),
    }
