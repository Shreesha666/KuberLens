from django.urls import path

from apps.technical_analysis.views import TechnicalOverviewView

app_name = "technical_analysis"

urlpatterns = [
    path("", TechnicalOverviewView.as_view(), name="overview"),
]
