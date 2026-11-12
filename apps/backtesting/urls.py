from django.urls import path

from apps.backtesting.views import BacktestDashboardView, BacktestRunDetailView

app_name = "backtesting"

urlpatterns = [
    path("", BacktestDashboardView.as_view(), name="dashboard"),
    path("run/<uuid:pk>/", BacktestRunDetailView.as_view(), name="run_detail"),
]
