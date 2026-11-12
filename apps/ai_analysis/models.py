"""
AI Stock Analysis Models.
Enforces Master Specification Section 17 structured AI research schema,
storing structured analysis from Investor AI, Swing Trader AI, and Portfolio Risk Manager.
"""
from django.conf import settings
from django.db import models

from apps.core.models import AuditedModel
from apps.instruments.models import ExchangeListing


class AIRole(models.TextChoices):
    INVESTOR = "INVESTOR", "Investor AI (Long-Term)"
    SWING_TRADER = "SWING_TRADER", "Swing Trader AI (Short-Term)"
    RISK_MANAGER = "RISK_MANAGER", "Portfolio Risk Manager"


class AIOpinionLabel(models.TextChoices):
    BUY_CANDIDATE = "BUY_CANDIDATE", "BUY CANDIDATE"
    HOLD = "HOLD", "HOLD"
    WATCH = "WATCH", "WATCH"
    AVOID = "AVOID", "AVOID"
    REDUCE = "REDUCE", "REDUCE"
    EXIT = "EXIT", "EXIT"


class ConfidenceLevel(models.TextChoices):
    HIGH = "HIGH", "High"
    MEDIUM = "MEDIUM", "Medium"
    LOW = "LOW", "Low"


class AnalysisHorizon(models.TextChoices):
    LONG_TERM = "LONG_TERM", "Long-Term (1-3 Years)"
    SWING_TERM = "SWING_TERM", "Swing-Term (1-4 Weeks)"
    PORTFOLIO_RISK = "PORTFOLIO_RISK", "Portfolio Risk (Ongoing)"


class StockAIAnalysis(AuditedModel):
    """
    Stores structured AI research briefs generated from verified financial data.
    Strictly forbids hallucinations by tracking input data references and
    explicitly cataloging missing or unverified information.
    """
    listing = models.ForeignKey(
        ExchangeListing,
        on_delete=models.CASCADE,
        related_name="ai_analyses",
        help_text="Exchange listing evaluated by AI.",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_analyses",
        help_text="User who initiated or customized the analysis.",
    )
    role = models.CharField(
        max_length=30,
        choices=AIRole.choices,
        default=AIRole.INVESTOR,
        help_text="AI Persona / Role conducting the research.",
    )
    overall_view = models.CharField(
        max_length=30,
        choices=AIOpinionLabel.choices,
        default=AIOpinionLabel.WATCH,
        help_text="Standardized Master Specification opinion label.",
    )
    confidence_level = models.CharField(
        max_length=20,
        choices=ConfidenceLevel.choices,
        default=ConfidenceLevel.MEDIUM,
    )
    analysis_horizon = models.CharField(
        max_length=30,
        choices=AnalysisHorizon.choices,
        default=AnalysisHorizon.LONG_TERM,
    )
    summary = models.TextField(
        help_text="Executive summary and synthesized verdict.",
    )
    positive_factors = models.JSONField(
        default=list,
        help_text="List of verified positive catalysts, fundamental strengths, or bullish indicators.",
    )
    negative_factors = models.JSONField(
        default=list,
        help_text="List of verified headwinds, valuation concerns, or bearish warning signs.",
    )
    technical_analysis = models.JSONField(
        default=dict,
        help_text="Structured technical analysis (trend, support, resistance, signals).",
    )
    fundamental_analysis = models.JSONField(
        default=dict,
        help_text="Structured fundamental breakdown (valuation, profitability, solvency, growth).",
    )
    risk_assessment = models.TextField(
        help_text="Downside scenario analysis, drawdowns, and sector risks.",
    )
    existing_holder_view = models.TextField(
        help_text="Specific guidance for investors currently holding shares in their portfolio.",
    )
    new_investor_view = models.TextField(
        help_text="Specific guidance for market participants evaluating initiating a new position.",
    )
    entry_conditions = models.TextField(
        blank=True,
        default="",
        help_text="Technical or price conditions required to validate an entry.",
    )
    invalidation_conditions = models.TextField(
        blank=True,
        default="",
        help_text="Stop loss or thesis invalidation triggers.",
    )
    missing_information = models.JSONField(
        default=list,
        help_text="List of missing, unverified, or unavailable data points identified by AI.",
    )
    data_sources_and_assumptions = models.JSONField(
        default=list,
        help_text="Audit list of data sources used (NSE, Jugaad-Data, Yahoo, Internal Snapshots).",
    )
    data_freshness = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Recorded freshness of data used at analysis time.",
    )
    prompt_version = models.CharField(
        max_length=30,
        default="v1.0",
        help_text="System prompt version used for reproducible generation.",
    )
    model_name = models.CharField(
        max_length=50,
        default="gemini-2.0-flash",
        help_text="AI model identifier.",
    )
    raw_response = models.TextField(
        blank=True,
        default="",
        help_text="Complete raw provider response payload.",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Stock AI Analysis"
        verbose_name_plural = "Stock AI Analyses"
        indexes = [
            models.Index(fields=["listing", "role", "-created_at"], name="idx_ai_listing_role"),
            models.Index(fields=["overall_view", "-created_at"], name="idx_ai_view_created"),
        ]

    def __str__(self) -> str:
        return f"{self.listing.symbol} ({self.get_role_display()}): {self.get_overall_view_display()}"

