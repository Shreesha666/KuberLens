from django.contrib import admin

from apps.ml_engine.models import (
    MLDatasetSnapshot,
    MLFeatureDefinition,
    MLModelRecord,
    MLMonitoringEvent,
    MLPrediction,
    MLPredictionArchive,
)


@admin.register(MLDatasetSnapshot)
class MLDatasetSnapshotAdmin(admin.ModelAdmin):
    list_display = ("name", "version", "start_date", "end_date", "universe_size", "total_samples", "quality_status", "created_at")
    list_filter = ("quality_status",)
    search_fields = ("name", "version", "universe_hash")


@admin.register(MLFeatureDefinition)
class MLFeatureDefinitionAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "lookback_periods", "calculation_version", "is_active")
    list_filter = ("category", "is_active")
    search_fields = ("name", "category")


@admin.register(MLModelRecord)
class MLModelRecordAdmin(admin.ModelAdmin):
    list_display = (
        "model_name",
        "version",
        "algorithm",
        "horizon_sessions",
        "model_state",
        "brier_score",
        "pr_auc",
        "is_active",
        "created_at",
    )
    list_filter = ("model_state", "algorithm", "horizon_sessions", "is_active")
    search_fields = ("model_name", "version", "artifact_hash")


@admin.register(MLPrediction)
class MLPredictionAdmin(admin.ModelAdmin):
    list_display = (
        "listing",
        "horizon_sessions",
        "prediction_label",
        "confidence_score",
        "calibrated_probability",
        "inference_state",
        "execution_mode",
        "calibration_status",
        "as_of_session",
    )
    list_filter = ("horizon_sessions", "inference_state", "execution_mode", "calibration_status", "regime_classification")
    search_fields = ("listing__symbol", "prediction_label")


@admin.register(MLPredictionArchive)
class MLPredictionArchiveAdmin(admin.ModelAdmin):
    list_display = (
        "listing",
        "horizon_sessions",
        "prediction_label",
        "confidence_score",
        "execution_mode",
        "as_of_session",
        "archive_reason",
        "archived_at",
    )
    list_filter = ("horizon_sessions", "execution_mode", "archive_reason")
    search_fields = ("listing__symbol", "original_prediction_id")


@admin.register(MLMonitoringEvent)
class MLMonitoringEventAdmin(admin.ModelAdmin):
    list_display = ("model_record", "event_type", "severity", "created_at")
    list_filter = ("event_type", "severity")
    search_fields = ("model_record__model_name", "event_type")
