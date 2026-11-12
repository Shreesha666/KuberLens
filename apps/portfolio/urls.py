from django.urls import path

from apps.portfolio.views import PortfolioOverviewView

app_name = "portfolio"

urlpatterns = [
    path("", PortfolioOverviewView.as_view(), name="overview"),
]
