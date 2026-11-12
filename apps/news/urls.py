from django.urls import path

from apps.news.views import CorporateEventsCalendarView, NewsFeedView

app_name = "news"

urlpatterns = [
    path("", NewsFeedView.as_view(), name="feed"),
    path("calendar/", CorporateEventsCalendarView.as_view(), name="calendar"),
]
