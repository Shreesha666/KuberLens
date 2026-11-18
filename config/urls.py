"""
Main URL Configuration for Indian Stock Market Research & Intelligence Platform.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path

handler404 = "apps.core.views.custom_page_not_found"
handler500 = "apps.core.views.custom_server_error"

urlpatterns = [
    path("favicon.ico", lambda request: HttpResponse(b"", content_type="image/x-icon", status=200)),
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls", namespace="accounts")),
    path("core/", include("apps.core.urls", namespace="core")),
    path("stocks/", include("apps.stocks.urls", namespace="stocks")),
    path("research/technical/", include("apps.technical_analysis.urls", namespace="technical_analysis")),
    path("research/fundamental/", include("apps.fundamental_analysis.urls", namespace="fundamental_analysis")),
    path("research/ai/", include("apps.ai_analysis.urls", namespace="ai_analysis")),
    path("portfolio/holdings/", include("apps.holdings.urls", namespace="holdings")),
    path("portfolio/", include("apps.portfolio.urls", namespace="portfolio")),
    path("screener/", include("apps.screener.urls", namespace="screener")),
    path("watchlists/", include("apps.watchlists.urls", namespace="watchlists")),
    path("trading/", include("apps.trading.urls", namespace="trading")),
    path("backtesting/", include("apps.backtesting.urls", namespace="backtesting")),
    path("ml/", include("apps.ml_engine.urls", namespace="ml_engine")),
    path("brokers/", include("apps.brokers.urls", namespace="brokers")),
    path("reports/", include("apps.reports.urls", namespace="reports")),
    path("news/", include("apps.news.urls", namespace="news")),
    path("alerts/", include("apps.alerts.urls", namespace="alerts")),
    path("notifications/", include("apps.notifications.urls", namespace="notifications")),
    path("ipo/", include("apps.ipo.urls", namespace="ipo")),
    path("papertrading/", include("apps.paper_trading.urls", namespace="paper_trading")),
    path("settings/", include("apps.settings_app.urls", namespace="settings_app")),
    path("", include("apps.dashboard.urls", namespace="dashboard")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


