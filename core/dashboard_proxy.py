class DashboardChartMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.rstrip('/') == '/dashboard':
            from .dashboard_fixes import FixedDashboardView
            return FixedDashboardView.as_view()(request)
        return self.get_response(request)
