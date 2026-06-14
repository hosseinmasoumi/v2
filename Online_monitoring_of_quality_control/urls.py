from django.contrib import admin
from django.urls import path, include
from core.views import HomeView
from core.dashboard_fixes import FixedDashboardView
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('grappelli/', include('grappelli.urls')),
    path('admin/', admin.site.urls),
    path('dashboard/', FixedDashboardView.as_view(), name='dashboard'),
    path('', include('core.urls')),
    path("project/",include("project.urls")),
    path('auth/experiment/', include('experiment.urls', namespace='experiment')),
    path("", HomeView.as_view(), name="home"),
    path('select2/', include('django_select2.urls')), 
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

admin.site.site_header = "سامانه کنترل کیفیت"
admin.site.site_title = "سامانه کنترل کیفیت"
