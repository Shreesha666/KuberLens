"""
Portfolio Data Models.
Defines user portfolio containers, cash balances, and multi-portfolio ownership.
"""
from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.core.models import AuditedModel


class Portfolio(AuditedModel):
    """
    User portfolio container tracking aggregate asset allocations and cash balance.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="portfolios",
        db_index=True,
    )
    name = models.CharField(max_length=100, default="Main Portfolio")
    currency = models.CharField(max_length=10, default="INR")
    cash_balance = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    is_default = models.BooleanField(default=True)
    description = models.TextField(blank=True)

    class Meta:
        db_table = "portfolio_portfolio"
        ordering = ["-is_default", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "name"],
                name="unique_user_portfolio_name",
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.user.email})"


class ConvictionLevel(models.TextChoices):
    HIGH = "HIGH", "High Conviction"
    MEDIUM = "MEDIUM", "Medium Conviction"
    SPECULATIVE = "SPECULATIVE", "Speculative / Turnaround"


class InvestmentHorizon(models.TextChoices):
    SHORT = "1_YEAR", "1 Year (Tactical)"
    MEDIUM = "3_YEARS", "3 Years (Multi-Year)"
    LONG = "5_PLUS_YEARS", "5+ Years (Long-Term Compounder)"


class InvestmentJournalStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active Holding Thesis"
    UNDER_REVIEW = "UNDER_REVIEW", "Under Review"
    EXITED = "EXITED", "Thesis Exited"


class InvestmentJournalEntry(AuditedModel):
    """
    Long-term investor journal tracking investment theses, competitive moats,
    quarterly catalysts, and review notes for portfolio assets.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="investment_journal_entries",
        db_index=True,
    )
    portfolio = models.ForeignKey(
        Portfolio,
        on_delete=models.CASCADE,
        related_name="journal_entries",
        null=True,
        blank=True,
    )
    listing = models.ForeignKey(
        "instruments.ExchangeListing",
        on_delete=models.CASCADE,
        related_name="investment_theses",
        db_index=True,
    )
    title = models.CharField(max_length=200)
    thesis_narrative = models.TextField(help_text="Why invest: business model, competitive moat, industry tailwinds.")
    moat_description = models.CharField(max_length=255, blank=True, help_text="Competitive advantage / economic moat.")
    conviction = models.CharField(
        max_length=20,
        choices=ConvictionLevel.choices,
        default=ConvictionLevel.HIGH,
        db_index=True,
    )
    horizon = models.CharField(
        max_length=20,
        choices=InvestmentHorizon.choices,
        default=InvestmentHorizon.MEDIUM,
    )
    target_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Estimated fair value or long-term target price.",
    )
    key_risks = models.TextField(blank=True, help_text="Key downside risks to monitor.")
    catalysts = models.TextField(blank=True, help_text="Upcoming growth catalysts or earnings triggers.")
    review_notes = models.TextField(blank=True, help_text="Periodic earnings notes or thesis updates.")
    status = models.CharField(
        max_length=20,
        choices=InvestmentJournalStatus.choices,
        default=InvestmentJournalStatus.ACTIVE,
        db_index=True,
    )

    class Meta:
        db_table = "portfolio_investment_journal"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
        ]

    def __str__(self):
        return f"{self.listing.symbol} - {self.title} ({self.get_conviction_display()})"
