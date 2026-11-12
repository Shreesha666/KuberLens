from django.urls import path

from apps.portfolio.views import PortfolioImportView, PortfolioOverviewView

app_name = "portfolio"

urlpatterns = [
    path("", PortfolioOverviewView.as_view(), name="overview"),
    path("import/", PortfolioImportView.as_view(), name="import_holdings"),
]
