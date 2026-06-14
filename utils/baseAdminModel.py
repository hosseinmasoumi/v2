from django.contrib import admin


class BtnDeleteSelected:
    """Admin mixin that keeps Django's selected-row delete action available."""

    actions = ['delete_selected']

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' not in actions:
            delete_action = admin.site.get_action('delete_selected')
            if delete_action:
                actions['delete_selected'] = delete_action
        return actions
