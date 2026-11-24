"""
Machine Learning Engine Models.
Complies with Master Specification Section 18 and AIML Architecture Specification v2.1.
Stores versioned ML models, features, training ranges, evaluation metrics,
time-series predictions strictly avoiding lookahead bias, and archived prediction records.
"""
from decimal import Decimal

from django.db import models

from apps.core.models import AuditedModel
from apps.instruments.models import ExchangeListing


class MarketRegimeType(models.TextChoices):
    TRENDING_UP = "TRENDING_UP", "Trending Up (Bullish Expansion)"
    TRENDING_DOWN = "TRENDING_DOWN", "Trending Down (Bearish Distribution)"
    RANGE_BOUND = "RANGE_BOUND", "Range Bound (Low Volatility Mean Reversion)"
    HIGH_VOLATILITY = "HIGH_VOLATILITY", "High Volatility (Turbulent / Breakout)"


class MLPredictionLabel(models.TextChoices):
    BULLISH_EXPANSION = "BULLISH_EXPANSION", "Bullish Expansion"
    SIDEWAYS_CONSOLIDATION = "SIDEWAYS_CONSOLIDATION", "Sideways Consolidation"
    BEARISH_CONTRACTION = "BEARISH_CONTRACTION", "Bearish Contraction"
    BREAKOUT_CANDIDATE = "BREAKOUT_CANDIDATE", "Breakout Candidate"


class MLInferenceState(models.TextChoices):
    APPROVED_MODEL = "APPROVED_MODEL", "Approved Model (Calibrated)"
    EXPERIMENTAL_MODEL = "EXPERIMENTAL_MODEL", "Experimental Model"
    HEURISTIC_FALLBACK = "HEURISTIC_FALLBACK", "Heuristic Fallback (Rule-Based)"
    STALE_DATA = "STALE_DATA", "Stale Market Data"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA", "Insufficient Data"


class MLExecutionMode(models.TextChoices):
    ONLINE_REALTIME = "ONLINE_REALTIME", "Online Real-Time"
    EOD_BATCH_SCHEDULED = "EOD_BATCH_SCHEDULED", "EOD Batch Scheduled"
    MANUAL_ADHOC = "MANUAL_ADHOC", "Manual Ad-Hoc"
    BACKTEST_SIMULATED = "BACKTEST_SIMULATED", "Backtest Simulated"


class MLModelState(models.TextChoices):
    EXPERIMENTAL = "EXPERIMENTAL", "Experimental"
    VALIDATED = "VALIDATED", "Validated"
    APPROVED = "APPROVED", "Approved"
    RETIRED = "RETIRED", "Retired"
    FAILED = "FAILED", "Failed"
    LEGACY_HEURISTIC = "LEGACY_HEURISTIC", "Legacy Heuristic"


class MLDatasetSnapshot(AuditedModel):
    """
    Tracks the point-in-time historical dataset window, universe hashes,
    and metadata used for reproducible training runs.
    """
    name = models.CharField(max_length=150)
    version = models.CharField(max_length=50, unique=True, db_index=True)
    start_date = models.DateField()
    end_date = models.DateField()
    universe_hash = models.CharField(max_length=64, help_text="SHA-256 hash of eligible universe ISINs")
    content_hash = models.CharField(max_length=64, blank=True, help_text="SHA-256 hash of canonical extracted dataset")
    universe_size = models.PositiveIntegerField(default=0)
    total_samples = models.PositiveIntegerField(default=0)
    feature_count = models.PositiveIntegerField(default=0)
    corporate_action_version = models.CharField(max_length=50, default="corp-v1.0")
    feature_schema_version = models.CharField(max_length=50, default="feat-v1.0")
    quality_status = models.CharField(max_length=30, default="VALIDATED")
    storage_path = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "ML Dataset Snapshot"
        verbose_name_plural = "ML Dataset Snapshots"

    def __str__(self) -> str:
        return f"{self.name} [{self.version}] ({self.total_samples} samples)"


class MLFeatureDefinition(AuditedModel):
    """
    Catalog of feature specifications, lookbacks, and calculation versions.
    """
    name = models.CharField(max_length=100, unique=True, db_index=True)
    category = models.CharField(max_length=50, db_index=True)  # TREND, MOMENTUM, VOLATILITY, VOLUME, REGIME
    lookback_periods = models.PositiveIntegerField(default=14)
    calculation_version = models.CharField(max_length=50, default="feat-v1.0")
    formula_description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["category", "name"]
        verbose_name = "ML Feature Definition"
        verbose_name_plural = "ML Feature Definitions"

    def __str__(self) -> str:
        return f"{self.name} ({self.category}, {self.lookback_periods}p)"


class MLModelRecord(AuditedModel):
    """
    Versioned registry of machine learning classification and ranking models.
    Supports atomic lifecycle states (at most one APPROVED model per horizon).
    """
    model_name = models.CharField(max_length=100, db_index=True)
    version = models.CharField(max_length=30, default="v1.0")
    target_variable = models.CharField(max_length=50, help_text="e.g. 10_day_forward_direction, regime_type")
    features_used = models.JSONField(
        default=list,
        help_text="List of feature column names used for training (e.g. ['rsi_14', 'sma_ratio', 'atr_volatility']).",
    )
    training_start_date = models.DateField()
    training_end_date = models.DateField()
    evaluation_metrics = models.JSONField(
        default=dict,
        help_text="Out-of-sample time-series evaluation metrics (accuracy, precision, recall, f1).",
    )
    baseline_metrics = models.JSONField(
        default=dict,
        help_text="Comparison benchmark metrics against naive / rule-based baselines.",
    )
    is_active = models.BooleanField(default=True, db_index=True)

    # Architecture v2.1 Extensions
    dataset_snapshot = models.ForeignKey(
        MLDatasetSnapshot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="trained_models",
    )
    previous_approved_version = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="superseded_by",
    )
    artifact_path = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Filesystem path to joblib serialized bundle under models/lightgbm/.",
    )
    artifact_hash = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="SHA-256 checksum of the serialized joblib artifact.",
    )
    algorithm = models.CharField(
        max_length=50,
        default="HEURISTIC_RULE_BASED",
        db_index=True,
        help_text="e.g. LIGHTGBM, HEURISTIC_RULE_BASED",
    )
    horizon_sessions = models.PositiveSmallIntegerField(
        default=10,
        db_index=True,
        help_text="Prediction horizon in trading sessions (5, 10, or 20).",
    )
    calibration_method = models.CharField(
        max_length=50,
        blank=True,
        default="NONE",
        help_text="ISOTONIC, SIGMOID, or NONE.",
    )
    brier_score = models.DecimalField(
        max_digits=6,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Out-of-sample Brier score.",
    )
    brier_skill_score = models.DecimalField(
        max_digits=6,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Brier Skill Score relative to training prevalence prior.",
    )
    pr_auc = models.DecimalField(
        max_digits=6,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Precision-Recall Area Under Curve.",
    )
    model_state = models.CharField(
        max_length=30,
        choices=MLModelState.choices,
        default=MLModelState.EXPERIMENTAL,
        db_index=True,
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "ML Model Record"
        verbose_name_plural = "ML Model Records"
        constraints = [
            models.UniqueConstraint(
                fields=["horizon_sessions"],
                condition=models.Q(model_state=MLModelState.APPROVED),
                name="unique_approved_model_per_horizon",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.model_name} [{self.version}] ({self.get_model_state_display()}, {self.horizon_sessions}d)"


class MLPrediction(AuditedModel):
    """
    Point-in-time machine learning prediction for an exchange listing.
    """
    listing = models.ForeignKey(
        ExchangeListing,
        on_delete=models.CASCADE,
        related_name="ml_predictions",
        db_index=True,
    )
    model_record = models.ForeignKey(
        MLModelRecord,
        on_delete=models.CASCADE,
        related_name="predictions",
    )
    prediction_timestamp = models.DateTimeField(db_index=True)
    prediction_label = models.CharField(
        max_length=50,
        choices=MLPredictionLabel.choices,
        db_index=True,
    )
    confidence_score = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=Decimal("0.5000"),
        help_text="Statistical confidence probability between 0.0000 and 1.0000.",
    )
    regime_classification = models.CharField(
        max_length=50,
        choices=MarketRegimeType.choices,
        default=MarketRegimeType.RANGE_BOUND,
        db_index=True,
    )
    feature_contributions = models.JSONField(
        default=dict,
        help_text="Key driving features and indicator weights for this prediction.",
    )
    disclaimer = models.CharField(
        max_length=250,
        default="Predictive research opinion based on historical statistical patterns. Not a guaranteed future price.",
    )

    # Architecture v2.1 Extensions
    horizon_sessions = models.PositiveSmallIntegerField(
        default=10,
        db_index=True,
        help_text="Prediction horizon in trading sessions (5, 10, or 20).",
    )
    as_of_session = models.DateField(
        db_index=True,
        help_text="Market trading session date (point-in-time close date).",
    )
    target_definition = models.CharField(
        max_length=100,
        default="forward_10d_directional_probability",
    )
    raw_probability = models.DecimalField(
        max_digits=6,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Uncalibrated model probability score.",
    )
    calibrated_probability = models.DecimalField(
        max_digits=6,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Calibrated probability score.",
    )
    calibration_status = models.CharField(
        max_length=30,
        default="UNCALIBRATED",
        db_index=True,
        help_text="CALIBRATED, RAW, UNCALIBRATED, or FALLBACK.",
    )
    is_heuristic = models.BooleanField(
        default=True,
        db_index=True,
        help_text="True if generated by rule fallback, False if trained statistical model.",
    )
    inference_state = models.CharField(
        max_length=30,
        choices=MLInferenceState.choices,
        default=MLInferenceState.HEURISTIC_FALLBACK,
        db_index=True,
        help_text="APPROVED_MODEL, EXPERIMENTAL_MODEL, HEURISTIC_FALLBACK, STALE_DATA, or INSUFFICIENT_DATA.",
    )
    execution_mode = models.CharField(
        max_length=30,
        choices=MLExecutionMode.choices,
        default=MLExecutionMode.ONLINE_REALTIME,
        db_index=True,
        help_text="Execution mode under which inference was triggered.",
    )

    class Meta:
        ordering = ["-prediction_timestamp"]
        verbose_name = "ML Prediction"
        verbose_name_plural = "ML Predictions"
        indexes = [
            models.Index(fields=["listing", "-prediction_timestamp"], name="idx_mlp_listing_time"),
            models.Index(fields=["prediction_label", "-prediction_timestamp"], name="idx_mlp_label_time"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["listing", "model_record", "horizon_sessions", "as_of_session"],
                name="unique_listing_model_horizon_session",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.listing.symbol} ({self.horizon_sessions}d): {self.get_prediction_label_display()} ({self.confidence_score:.1%})"


class MLPredictionArchive(AuditedModel):
    """
    Preserves historical prediction records that were deduplicated or superseded
    during schema migrations or batch recalculations. Ensures zero data loss.
    """
    original_prediction_id = models.UUIDField(db_index=True)
    listing = models.ForeignKey(
        ExchangeListing,
        on_delete=models.CASCADE,
        related_name="archived_ml_predictions",
        db_index=True,
    )
    model_record = models.ForeignKey(
        MLModelRecord,
        on_delete=models.CASCADE,
        related_name="archived_predictions",
    )
    prediction_timestamp = models.DateTimeField(db_index=True)
    prediction_label = models.CharField(max_length=50)
    confidence_score = models.DecimalField(max_digits=5, decimal_places=4, default=Decimal("0.5000"))
    regime_classification = models.CharField(max_length=50, default=MarketRegimeType.RANGE_BOUND)
    feature_contributions = models.JSONField(default=dict, blank=True)
    disclaimer = models.CharField(max_length=250, blank=True)
    horizon_sessions = models.PositiveSmallIntegerField(default=10)
    as_of_session = models.DateField(null=True, blank=True)
    execution_mode = models.CharField(
        max_length=30,
        choices=MLExecutionMode.choices,
        default=MLExecutionMode.ONLINE_REALTIME,
        blank=True,
    )
    archived_at = models.DateTimeField(auto_now_add=True, db_index=True)
    archive_reason = models.CharField(max_length=100, default="MIGRATION_DUPLICATE_KEY_RESOLUTION")

    class Meta:
        ordering = ["-archived_at"]
        verbose_name = "ML Prediction Archive"
        verbose_name_plural = "ML Prediction Archives"

    def __str__(self) -> str:
        return f"Archived {self.listing.symbol} ({self.prediction_timestamp}) - Reason: {self.archive_reason}"


class MLMonitoringEvent(AuditedModel):
    """
    Tracks operational drift, calibration decay, inference failures, and risk vetoes.
    """
    model_record = models.ForeignKey(
        MLModelRecord,
        on_delete=models.CASCADE,
        related_name="monitoring_events",
    )
    event_type = models.CharField(max_length=50, db_index=True)  # DRIFT_DETECTED, CALIBRATION_DECAY, INFERENCE_FAILURE, RISK_VETO
    severity = models.CharField(max_length=20, default="MEDIUM", db_index=True)  # LOW, MEDIUM, HIGH, CRITICAL
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "ML Monitoring Event"
        verbose_name_plural = "ML Monitoring Events"

    def __str__(self) -> str:
        return f"[{self.severity}] {self.event_type} for {self.model_record} ({self.created_at.date()})"
