from django.urls import path

from apps.notifications.views import (
    NotificationClearAllView,
    NotificationDeleteView,
    NotificationListView,
    NotificationMarkAllReadView,
    NotificationMarkReadView,
)

app_name = "notifications"

urlpatterns = [
    path("", NotificationListView.as_view(), name="list"),
    path("<uuid:pk>/read/", NotificationMarkReadView.as_view(), name="mark_read"),
    path("read-all/", NotificationMarkAllReadView.as_view(), name="mark_all_read"),
    path("<uuid:pk>/delete/", NotificationDeleteView.as_view(), name="delete"),
    path("clear-all/", NotificationClearAllView.as_view(), name="clear_all"),
]
