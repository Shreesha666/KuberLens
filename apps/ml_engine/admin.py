from django.contrib import admin

from apps.ml_engine.models import MLModelRecord, MLPrediction


@admin.register(MLModelRecord)
class MLModelRecordAdmin(admin.ModelAdmin):
    list_display = ("model_name", "version", "target_variable", "training_start_date", "training_end_date", "is_active")
    list_filter = ("is_active", "version")


@admin.register(MLPrediction)
class MLPredictionAdmin(admin.ModelAdmin):
    list_display = ("listing", "prediction_label", "confidence_score", "regime_classification", "prediction_timestamp")
    list_filter = ("prediction_label", "regime_classification")
    search_fields = ("listing__symbol", "prediction_label")
