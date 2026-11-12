from django.urls import path

from apps.stocks.views import SectorAnalysisView

from .views import DashboardView, MarketOverviewView, ModulePlaceholderView

app_name = "dashboard"

urlpatterns = [
    path("", DashboardView.as_view(), name="index"),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("market-overview/", MarketOverviewView.as_view(), name="market_overview"),
    path("modules/sector_analysis/", SectorAnalysisView.as_view(), name="sector_analysis_alias"),
    path("modules/<slug:module_name>/", ModulePlaceholderView.as_view(), name="placeholder"),
]
