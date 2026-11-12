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
    path("stocks/", include("apps.stocks.urls", namespace="stocks")),
    path("research/technical/", include("apps.technical_analysis.urls", namespace="technical_analysis")),
    path("research/fundamental/", include("apps.fundamental_analysis.urls", namespace="fundamental_analysis")),
    path("portfolio/holdings/", include("apps.holdings.urls", namespace="holdings")),
    path("portfolio/", include("apps.portfolio.urls", namespace="portfolio")),
    path("settings/", include("apps.settings_app.urls", namespace="settings_app")),
    path("", include("apps.dashboard.urls", namespace="dashboard")),
]

