from django.urls import path

from apps.trading.views import (
    PositionSizerCalculateView,
    RiskManagementView,
    SwingScannerView,
    TradeJournalCloseView,
    TradeJournalCreateView,
    TradeJournalDeleteView,
    TradeJournalListView,
)

app_name = "trading"

urlpatterns = [
    path("", SwingScannerView.as_view(), name="scanner"),
    path("risk-management/", RiskManagementView.as_view(), name="risk_management"),
    path("calculate-size/", PositionSizerCalculateView.as_view(), name="calculate_size"),
    path("journal/", TradeJournalListView.as_view(), name="journal"),
    path("journal/add/", TradeJournalCreateView.as_view(), name="journal_add"),
    path("journal/<uuid:pk>/close/", TradeJournalCloseView.as_view(), name="journal_close"),
    path("journal/<uuid:pk>/delete/", TradeJournalDeleteView.as_view(), name="journal_delete"),
]

