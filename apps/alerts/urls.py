from django.urls import path

from apps.alerts.views import (
    AlertCreateView,
    AlertDeleteView,
    AlertListView,
    AlertRunEvaluationView,
    AlertStockTargetsView,
    AlertToggleActiveView,
    AlertUpdateView,
)

app_name = "alerts"

urlpatterns = [
    path("", AlertListView.as_view(), name="list"),
    path("create/", AlertCreateView.as_view(), name="create"),
    path("stock-targets/<str:symbol>/", AlertStockTargetsView.as_view(), name="stock_targets"),
    path("<uuid:pk>/toggle/", AlertToggleActiveView.as_view(), name="toggle"),
    path("<uuid:pk>/edit/", AlertUpdateView.as_view(), name="update"),
    path("<uuid:pk>/delete/", AlertDeleteView.as_view(), name="delete"),
    path("evaluate/", AlertRunEvaluationView.as_view(), name="evaluate"),
]
