from django.urls import path

from apps.ipo.views import (
    IPOApplicationDeleteView,
    IPOApplicationListView,
    IPOBacktestView,
    IPOBatchApplyView,
    IPOBidPlannerView,
    IPOCalendarView,
    IPOComparisonView,
    IPODashboardView,
    IPODetailView,
    IPOFamilyMemberCreateView,
    IPOFamilyMemberDeleteView,
    IPOFamilyVaultView,
    IPOIssuesListView,
    IPOLogApplicationView,
    IPOPerformanceView,
    IPORegistrarCheckView,
    IPOResearchListView,
    IPOSyncView,
    IPOTransferToPortfolioView,
    IPOUpdateApplicationOutcomeView,
)

app_name = "ipo"

urlpatterns = [
    path("", IPODashboardView.as_view(), name="dashboard"),
    path("sync/", IPOSyncView.as_view(), name="sync"),
    path("issues/", IPOIssuesListView.as_view(), name="issues"),
    path("calendar/", IPOCalendarView.as_view(), name="calendar"),
    path("research/", IPOResearchListView.as_view(), name="research"),
    path("performance/", IPOPerformanceView.as_view(), name="performance"),
    path("compare/", IPOComparisonView.as_view(), name="compare"),
    path("backtest/", IPOBacktestView.as_view(), name="backtest"),
    path("family-vault/", IPOFamilyVaultView.as_view(), name="family_vault"),
    path("family-vault/create/", IPOFamilyMemberCreateView.as_view(), name="family_member_create"),
    path("family-vault/<uuid:pk>/delete/", IPOFamilyMemberDeleteView.as_view(), name="family_member_delete"),
    path("applications/", IPOApplicationListView.as_view(), name="applications"),
    path("applications/create/", IPOLogApplicationView.as_view(), name="application_create"),
    path("applications/<uuid:pk>/outcome/", IPOUpdateApplicationOutcomeView.as_view(), name="application_outcome"),
    path("applications/<uuid:pk>/transfer-to-portfolio/", IPOTransferToPortfolioView.as_view(), name="application_transfer_portfolio"),
    path("applications/<uuid:pk>/delete/", IPOApplicationDeleteView.as_view(), name="application_delete"),
    path("applications/<uuid:pk>/registrar-check/", IPORegistrarCheckView.as_view(), name="application_registrar_check"),
    path("<str:symbol>/bid-planner/", IPOBidPlannerView.as_view(), name="bid_planner"),
    path("<str:symbol>/batch-apply/", IPOBatchApplyView.as_view(), name="batch_apply"),
    path("<str:symbol>/", IPODetailView.as_view(), name="detail"),
]

