from io import StringIO
from django.contrib import admin, messages
from django.core.management import call_command
from django.shortcuts import redirect, render
from django.urls import path
from django.utils import timezone

from apps.ml_engine.models import (
    MLDatasetSnapshot,
    MLFeatureDefinition,
    MLModelRecord,
    MLMonitoringEvent,
    MLPipelineLease,
    MLPrediction,
    MLPredictionArchive,
    MLShadowEvaluationRecord,
    MLShadowPipelineRun,
)
from apps.ml_engine.views import PILOT_SYMBOLS
from services.calendar.exchange_calendar import ExchangeCalendar


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


@admin.register(MLShadowPipelineRun)
class MLShadowPipelineRunAdmin(admin.ModelAdmin):
    list_display = (
        "session_date",
        "status",
        "health_state",
        "trigger_type",
        "records_created",
        "outcomes_matured_20d",
        "duration_seconds",
        "started_at",
    )
    list_filter = ("status", "health_state", "trigger_type")
    search_fields = ("session_date", "run_id", "error_details")
    date_hierarchy = "session_date"
    change_list_template = "admin/ml_engine/mlshadowpipelinerun/change_list.html"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "run-pipeline/",
                self.admin_site.admin_view(self.run_pipeline_view),
                name="ml_engine_shadow_pipeline_trigger",
            ),
        ]
        return custom_urls + urls

    def run_pipeline_view(self, request):
        if request.method == "POST":
            session_date = request.POST.get("session_date", "").strip() or None
            universe = request.POST.get("universe", "").strip() or None
            setup_name = request.POST.get("setup_name", "").strip() or "TREND_PULLBACK_HEURISTIC"
            capture_mode = request.POST.get("capture_mode", "FORWARD_CAPTURED").strip()
            ingest_eod = request.POST.get("ingest_eod") == "true"
            catchup_missed = request.POST.get("catchup_missed") == "true"
            force = request.POST.get("force") == "true"
            dry_run = request.POST.get("dry_run") == "true"

            kwargs = {
                "setup_name": setup_name,
                "capture_mode": capture_mode,
            }
            if session_date:
                kwargs["session_date"] = session_date
            if universe:
                kwargs["universe"] = universe
            if ingest_eod:
                kwargs["ingest_eod"] = True
            if catchup_missed:
                kwargs["catchup_missed"] = True
            if force:
                kwargs["force"] = True
            if dry_run:
                kwargs["dry_run"] = True

            out = StringIO()
            err = StringIO()
            try:
                call_command("run_shadow_eod_pipeline", stdout=out, stderr=err, **kwargs)
                out_msg = out.getvalue()
                first_lines = "\n".join([line for line in out_msg.splitlines() if line.strip()][:5])
                messages.success(
                    request,
                    f"EOD Shadow Pipeline executed successfully. Summary:\n{first_lines}",
                )
            except Exception as e:
                messages.error(request, f"EOD Shadow Pipeline failed: {e}")

            return redirect("admin:ml_engine_mlshadowpipelinerun_changelist")

        # GET request: render the execution form
        today = timezone.now().date()
        default_session_date = (
            today if ExchangeCalendar.is_trading_day(today) else ExchangeCalendar.get_last_trading_day(today)
        )
        recent_runs = MLShadowPipelineRun.objects.order_by("-started_at")[:6]

        context = {
            **self.admin_site.each_context(request),
            "title": "Run EOD Pipeline",
            "default_session_date": str(default_session_date) if default_session_date else str(today),
            "default_universe": ", ".join(PILOT_SYMBOLS),
            "recent_runs": recent_runs,
        }
        return render(request, "admin/ml_engine/mlshadowpipelinerun/run_pipeline.html", context)


@admin.register(MLShadowEvaluationRecord)
class MLShadowEvaluationRecordAdmin(admin.ModelAdmin):
    list_display = (
        "listing",
        "session_date",
        "setup_name",
        "market_regime",
        "risk_level",
        "risk_score",
        "is_vetoed",
        "capture_mode",
        "is_matured",
        "forward_return_20d",
        "created_at",
    )
    list_filter = (
        "setup_name",
        "market_regime",
        "risk_level",
        "is_vetoed",
        "capture_mode",
        "is_matured",
        "status_5d",
        "status_10d",
        "status_20d",
    )
    search_fields = ("listing__symbol", "setup_name", "feature_snapshot_checksum", "processing_run_id")
    date_hierarchy = "session_date"


@admin.register(MLPipelineLease)
class MLPipelineLeaseAdmin(admin.ModelAdmin):
    list_display = ("lease_name", "owner_id", "is_active", "acquired_at", "heartbeat_at", "expires_at")
    list_filter = ("is_active", "lease_name")
    search_fields = ("lease_name", "owner_id")

