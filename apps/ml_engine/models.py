"""
Machine Learning Engine Models.
Complies with Master Specification Section 18.
Stores versioned ML models, features, training ranges, evaluation metrics,
and time-series predictions strictly avoiding lookahead bias.
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


class MLModelRecord(AuditedModel):
    """
    Versioned registry of machine learning classification and ranking models.
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

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "ML Model Record"
        verbose_name_plural = "ML Model Records"

    def __str__(self) -> str:
        return f"{self.model_name} [{self.version}]"


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

    class Meta:
        ordering = ["-prediction_timestamp"]
        verbose_name = "ML Prediction"
        verbose_name_plural = "ML Predictions"
        indexes = [
            models.Index(fields=["listing", "-prediction_timestamp"], name="idx_mlp_listing_time"),
            models.Index(fields=["prediction_label", "-prediction_timestamp"], name="idx_mlp_label_time"),
        ]

    def __str__(self) -> str:
        return f"{self.listing.symbol}: {self.get_prediction_label_display()} ({self.confidence_score:.1%})"

