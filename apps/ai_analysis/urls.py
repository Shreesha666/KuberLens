from django.urls import path

from apps.ai_analysis.views import (
    AIRecommendationsView,
    AIResearchHubView,
    AIStockDetailTabPartialView,
)

app_name = "ai_analysis"

urlpatterns = [
    path("", AIResearchHubView.as_view(), name="hub"),
    path("recommendations/", AIRecommendationsView.as_view(), name="recommendations"),
    path("stock/<str:symbol>/", AIStockDetailTabPartialView.as_view(), name="stock_tab_partial"),
]
