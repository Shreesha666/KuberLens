from django.urls import path

from apps.alerts.views import (
    AlertCreateView,
    AlertDeleteView,
    AlertListView,
    AlertRunEvaluationView,
    AlertToggleActiveView,
)

app_name = "alerts"

urlpatterns = [
    path("", AlertListView.as_view(), name="list"),
    path("create/", AlertCreateView.as_view(), name="create"),
    path("<uuid:pk>/toggle/", AlertToggleActiveView.as_view(), name="toggle"),
    path("<uuid:pk>/delete/", AlertDeleteView.as_view(), name="delete"),
    path("evaluate/", AlertRunEvaluationView.as_view(), name="evaluate"),
]
