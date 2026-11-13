from django.urls import path

from apps.holdings.views import (
    HoldingDetailView,
    HoldingListView,
    HoldingTransactionCreateView,
)

app_name = "holdings"

urlpatterns = [
    path("", HoldingListView.as_view(), name="list"),
    path("transactions/add/", HoldingTransactionCreateView.as_view(), name="add_transaction"),
    path("add/", HoldingTransactionCreateView.as_view(), name="add"),
    path("<str:symbol>/", HoldingDetailView.as_view(), name="detail"),
]
