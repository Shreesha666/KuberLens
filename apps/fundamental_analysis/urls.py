from django.urls import path

from apps.fundamental_analysis.views import FundamentalOverviewView

app_name = "fundamental_analysis"

urlpatterns = [
    path("", FundamentalOverviewView.as_view(), name="overview"),
]
