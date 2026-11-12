"""
Reports Models.
Complies with Master Specification Section 23.
Stores audit records of generated CSV exports and printable tear-sheets with
traceable metadata, timestamp, data sources, and modeling assumptions.
"""
from django.conf import settings
from django.db import models

from apps.core.models import AuditedModel


class ReportType(models.TextChoices):
    PORTFOLIO_TEARSHEET = "PORTFOLIO_TEARSHEET", "Portfolio Comprehensive Tear-Sheet"
    HOLDINGS_ANALYSIS = "HOLDINGS_ANALYSIS", "Holdings & Lot Allocation Analysis"
    SWING_SETUPS = "SWING_SETUPS", "Swing Trade Scanner Opportunities"
    TRADE_JOURNAL = "TRADE_JOURNAL", "Trade Journal Execution Audit"
    BACKTEST_SUMMARY = "BACKTEST_SUMMARY", "Strategy Backtest Performance Report"
    WATCHLIST_SUMMARY = "WATCHLIST_SUMMARY", "Watchlist Monitoring Summary"
    STOCK_RESEARCH_MEMO = "STOCK_RESEARCH_MEMO", "Stock Research Institutional Memo"


class ExportFormat(models.TextChoices):
    CSV = "CSV", "Comma-Separated Values (CSV)"
    HTML_PRINT = "HTML_PRINT", "Printable Executive Tear-Sheet (HTML/PDF)"


class GeneratedReport(AuditedModel):
    """
    Audit record for a generated research report or data export.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="generated_reports",
        db_index=True,
    )
    report_type = models.CharField(
        max_length=50,
        choices=ReportType.choices,
        db_index=True,
    )
    export_format = models.CharField(
        max_length=20,
        choices=ExportFormat.choices,
        default=ExportFormat.CSV,
    )
    title = models.CharField(max_length=200)
    parameters = models.JSONField(
        default=dict,
        blank=True,
        help_text="Query parameters, filters, or symbol used to generate report.",
    )
    report_metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Traceable metadata: data source, period, modeling assumptions, and record counts.",
    )
    record_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Generated Report"
        verbose_name_plural = "Generated Reports"

    def __str__(self) -> str:
        return f"{self.title} ({self.get_export_format_display()}) by {self.user.username}"

