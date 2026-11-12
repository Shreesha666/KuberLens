from django.urls import path

from apps.ml_engine.views import MLPredictionsDashboardView, MLRegeneratePredictionsView

app_name = "ml_engine"

urlpatterns = [
    path("", MLPredictionsDashboardView.as_view(), name="dashboard"),
    path("regenerate/", MLRegeneratePredictionsView.as_view(), name="regenerate"),
]
