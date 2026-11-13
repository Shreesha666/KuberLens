from django.urls import path

from apps.ipo.views import (
    IPOBidPlannerView,
    IPOCalendarView,
    IPODashboardView,
    IPODetailView,
    IPOIssuesListView,
    IPOResearchListView,
)

app_name = "ipo"

urlpatterns = [
    path("", IPODashboardView.as_view(), name="dashboard"),
    path("issues/", IPOIssuesListView.as_view(), name="issues"),
    path("calendar/", IPOCalendarView.as_view(), name="calendar"),
    path("research/", IPOResearchListView.as_view(), name="research"),
    path("<str:symbol>/bid-planner/", IPOBidPlannerView.as_view(), name="bid_planner"),
    path("<str:symbol>/", IPODetailView.as_view(), name="detail"),
]

