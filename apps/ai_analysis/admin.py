from django.contrib import admin

from apps.ai_analysis.models import StockAIAnalysis


@admin.register(StockAIAnalysis)
class StockAIAnalysisAdmin(admin.ModelAdmin):
    list_display = ("listing", "role", "overall_view", "confidence_level", "model_name", "created_at")
    list_filter = ("role", "overall_view", "confidence_level", "model_name")
    search_fields = ("listing__symbol", "listing__instrument__name", "summary")
    readonly_fields = ("created_at", "updated_at")
