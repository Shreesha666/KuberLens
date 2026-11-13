from django.urls import path

from apps.ipo.views import (
    IPOCalendarView,
    IPODashboardView,
    IPODetailView,
    IPOIssuesListView,
)

app_name = "ipo"

urlpatterns = [
    path("", IPODashboardView.as_view(), name="dashboard"),
    path("issues/", IPOIssuesListView.as_view(), name="issues"),
    path("calendar/", IPOCalendarView.as_view(), name="calendar"),
    path("<str:symbol>/", IPODetailView.as_view(), name="detail"),
]
