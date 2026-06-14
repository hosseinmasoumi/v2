import logging

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
        from . import models

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
                elif approvals.filter(
                    status=models.ExperimentApproval.APPROVED,
                    approver__is_superuser=True,
                ).exists():
                    status[role] = 'تایید شده'
                elif approvers and approvals.filter(
                    status=models.ExperimentApproval.APPROVED,
                    approver__in=approvers,
                ).count() == len(approvers):
                    status[role] = 'تایید شده'
                else:
                    status[role] = 'در انتظار'

            return status

        def is_fully_approved(self):
            status = self.get_approval_status_by_role()
            return all(value == 'تایید شده' for value in status.values() if value != 'تعریف نشده')

        models.ExperimentResponse.get_approval_status_by_role = get_approval_status_by_role
        models.ExperimentResponse.is_fully_approved = is_fully_approved


def get_user_approval_roles(experiment_response, user):
    required_roles = list(experiment_response.get_required_approval_roles())

    if user.is_superuser:
        return required_roles

    user_roles = []
    for role in required_roles:
        approvers = experiment_response.get_approvers_for_role(role)
        logger.debug(
            "Role: %s, Approvers: %s, Current user: %s",
            role,
            [approver.username for approver in approvers],
            user.username,
        )
        if user in approvers:
            user_roles.append(role)

    return user_roles


@login_required
def experiment_approval_create(request, response_id):
    from . import forms, models

    experiment_response = get_object_or_404(models.ExperimentResponse, pk=response_id)
    user_roles = get_user_approval_roles(experiment_response, request.user)

    if not user_roles:
        logger.warning(
            "User %s cannot approve response %s. Required roles: %s",
            request.user.username,
            experiment_response.pk,
            experiment_response.get_required_approval_roles(),
        )
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
                            models.Notification.objects.create(
                                user=user,
                                experiment_request=experiment_response.experiment_request,
                                message=f'یک تاییدیه جدید برای پاسخ آزمایش پروژه {experiment_response.experiment_request.project.name} ثبت شد.'
                            )
                            notified_users.add(user.id)

                messages.success(request, 'تایید آزمایش با موفقیت ثبت شد.')
                return redirect('experiment:experiment_response_detail', pk=response_id)
    else:
        initial = {'experiment_response': experiment_response.pk}
        if len(user_roles) == 1:
            initial['role'] = user_roles[0]
        form = forms.ExperimentApprovalForm(initial=initial, user_roles=user_roles)

    return render(request, 'experiment/experiment_approval_form.html', {
        'form': form,
        'experiment_response': experiment_response,
        'user_roles': user_roles,
    })
