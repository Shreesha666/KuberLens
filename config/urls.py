"""
Main URL Configuration for Indian Stock Market Research & Intelligence Platform.
"""
from django.contrib import admin
from django.urls import include, path

handler404 = "apps.core.views.custom_page_not_found"
handler500 = "apps.core.views.custom_server_error"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls", namespace="accounts")),
    path("core/", include("apps.core.urls", namespace="core")),
    path("", include("apps.dashboard.urls", namespace="dashboard")),
]
