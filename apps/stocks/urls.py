from django.urls import path

from apps.stocks.views import (
    SectorAnalysisView,
    StockChartDataView,
    StockDetailView,
    StockListView,
    StockLogoProxyView,
    StockSearchView,
)

app_name = "stocks"

urlpatterns = [
    path("", StockListView.as_view(), name="stock_list"),
    path("search/", StockSearchView.as_view(), name="stock_search"),
    path("sectors/", SectorAnalysisView.as_view(), name="sector_analysis"),
    path("<str:symbol>/", StockDetailView.as_view(), name="stock_detail"),
    path("<str:symbol>/chart-data/", StockChartDataView.as_view(), name="stock_chart_data"),
    path("<str:symbol>/logo/", StockLogoProxyView.as_view(), name="stock_logo"),
]
