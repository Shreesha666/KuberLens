from django.urls import path

from apps.portfolio.views import (
    InvestmentJournalCreateView,
    InvestmentJournalDeleteView,
    InvestmentJournalListView,
    PortfolioImportView,
    PortfolioOverviewView,
)

app_name = "portfolio"

urlpatterns = [
    path("", PortfolioOverviewView.as_view(), name="overview"),
    path("import/", PortfolioImportView.as_view(), name="import_holdings"),
    path("journal/", InvestmentJournalListView.as_view(), name="investment_journal"),
    path("journal/add/", InvestmentJournalCreateView.as_view(), name="investment_journal_add"),
    path("journal/<uuid:pk>/delete/", InvestmentJournalDeleteView.as_view(), name="investment_journal_delete"),
]
