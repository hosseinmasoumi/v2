import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render

from . import forms, models

logger = logging.getLogger(__name__)


def get_user_approval_roles(experiment_response, user):
    roles = list(experiment_response.get_required_approval_roles())
    if user.is_superuser:
        return roles

    user_roles = []
    for role in roles:
        if user in experiment_response.get_approvers_for_role(role):
            user_roles.append(role)
    return user_roles


def get_default_approval_role(user_roles):
    if not user_roles:
        return ''
    lab_role = 'مسئول آزمایشگاه'
    if lab_role in user_roles:
        return lab_role
    return user_roles[0]


@login_required
def experiment_approval_create(request, response_id):
    experiment_response = get_object_or_404(models.ExperimentResponse, pk=response_id)
    user_roles = get_user_approval_roles(experiment_response, request.user)

    if not user_roles:
        messages.error(request, 'شما مجاز به ثبت تاییدیه برای این پاسخ آزمایش نیستید.')
        return redirect('experiment:experiment_response_detail', pk=response_id)

    default_role = get_default_approval_role(user_roles)

    if request.method == 'POST':
        post_data = request.POST.copy()
        if not post_data.get('experiment_response'):
            post_data['experiment_response'] = experiment_response.pk
        if not post_data.get('role') and default_role:
            post_data['role'] = default_role

        form = forms.ExperimentApprovalForm(post_data, user_roles=user_roles)
        if form.is_valid():
            approval = form.save(commit=False)
            approval.experiment_response = experiment_response
            approval.approver = request.user
            if not approval.role:
                approval.role = default_role

            try:
                approval.save()
            except IntegrityError:
                form.add_error(None, 'برای این نقش قبلا توسط این کاربر تاییدیه ثبت شده است.')
            else:
                messages.success(request, 'تایید آزمایش با موفقیت ثبت شد.')
                return redirect('experiment:experiment_response_detail', pk=response_id)
    else:
        initial = {
            'experiment_response': experiment_response.pk,
            'role': default_role,
        }
        form = forms.ExperimentApprovalForm(initial=initial, user_roles=user_roles)

    return render(request, 'experiment/experiment_approval_form.html', {
        'form': form,
        'experiment_response': experiment_response,
        'user_roles': user_roles,
    })
