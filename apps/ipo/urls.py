from django.urls import path

from apps.ipo.views import (
    IPOApplicationDeleteView,
    IPOApplicationListView,
    IPOBidPlannerView,
    IPOCalendarView,
    IPODashboardView,
    IPODetailView,
    IPOIssuesListView,
    IPOLogApplicationView,
    IPOResearchListView,
    IPOTransferToPortfolioView,
    IPOUpdateApplicationOutcomeView,
)

app_name = "ipo"

urlpatterns = [
    path("", IPODashboardView.as_view(), name="dashboard"),
    path("issues/", IPOIssuesListView.as_view(), name="issues"),
    path("calendar/", IPOCalendarView.as_view(), name="calendar"),
    path("research/", IPOResearchListView.as_view(), name="research"),
    path("applications/", IPOApplicationListView.as_view(), name="applications"),
    path("applications/create/", IPOLogApplicationView.as_view(), name="application_create"),
    path("applications/<uuid:pk>/outcome/", IPOUpdateApplicationOutcomeView.as_view(), name="application_outcome"),
    path("applications/<uuid:pk>/transfer-to-portfolio/", IPOTransferToPortfolioView.as_view(), name="application_transfer_portfolio"),
    path("applications/<uuid:pk>/delete/", IPOApplicationDeleteView.as_view(), name="application_delete"),
    path("<str:symbol>/bid-planner/", IPOBidPlannerView.as_view(), name="bid_planner"),
    path("<str:symbol>/", IPODetailView.as_view(), name="detail"),
]

