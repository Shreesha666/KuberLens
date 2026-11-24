from django.urls import path

from apps.ml_engine.views import (
    MLPredictionsDashboardView,
    MLRegeneratePredictionsView,
    RiskIntelligenceDashboardView,
    RunShadowEvaluationStepView,
)

app_name = "ml_engine"

urlpatterns = [
    path("", MLPredictionsDashboardView.as_view(), name="dashboard"),
    path("regenerate/", MLRegeneratePredictionsView.as_view(), name="regenerate"),
    path("risk-dashboard/", RiskIntelligenceDashboardView.as_view(), name="risk_dashboard"),
    path("shadow/run/", RunShadowEvaluationStepView.as_view(), name="shadow_run"),
]
