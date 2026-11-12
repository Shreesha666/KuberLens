from django.urls import path

from apps.stocks.views import (
    StockChartDataView,
    StockDetailView,
    StockListView,
    StockSearchView,
)

app_name = "stocks"

urlpatterns = [
    path("", StockListView.as_view(), name="stock_list"),
    path("search/", StockSearchView.as_view(), name="stock_search"),
    path("<str:symbol>/", StockDetailView.as_view(), name="stock_detail"),
    path("<str:symbol>/chart-data/", StockChartDataView.as_view(), name="stock_chart_data"),
]
