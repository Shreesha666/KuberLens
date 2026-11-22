from django.urls import path

from apps.ai_analysis.views import AIRecommendationsView
from apps.portfolio.views import InvestmentJournalListView
from apps.stocks.views import SectorAnalysisView
from apps.trading.views import RiskManagementView

from .views import DashboardView, MarketOverviewView, ModulePlaceholderView

app_name = "dashboard"

urlpatterns = [
    path("", DashboardView.as_view(), name="index"),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("market-overview/", MarketOverviewView.as_view(), name="market_overview"),
    path("modules/sector_analysis/", SectorAnalysisView.as_view(), name="sector_analysis_alias"),
    path("modules/investment_journal/", InvestmentJournalListView.as_view(), name="investment_journal_alias"),
    path("modules/ai_recommendations/", AIRecommendationsView.as_view(), name="ai_recommendations_alias"),
    path("modules/risk_management/", RiskManagementView.as_view(), name="risk_management_alias"),
    path("modules/<slug:module_name>/", ModulePlaceholderView.as_view(), name="placeholder"),
]
