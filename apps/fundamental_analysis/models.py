"""
Fundamental Analysis Data Models.
Stores versioned fundamental snapshot metrics and multi-factor scores.
"""
from django.db import models
from django.utils import timezone

from apps.core.models import AuditedModel


class FundamentalSnapshot(AuditedModel):
    """
    Derived snapshot of corporate financial metrics, ratios, and multi-factor scores.
    Separated from provider-specific scrapers and tagged with a calculation version.
    """
    instrument = models.ForeignKey(
        "instruments.Instrument",
        on_delete=models.CASCADE,
        related_name="fundamental_snapshots",
        db_index=True,
    )

    # 1. Valuation Ratios
    pe_ratio = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    pb_ratio = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    ps_ratio = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    ev_to_ebitda = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    dividend_yield = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    sector_pe = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # 2. Profitability Ratios
    roe = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)          # Return on Equity (%)
    roce = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)         # Return on Capital Employed (%)
    operating_margin = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)  # Operating Margin (%)
    net_profit_margin = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True) # Net Margin (%)
    eps = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)        # Earnings Per Share (₹)

    # 3. Financial Health & Solvency
    debt_to_equity = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    current_ratio = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    interest_coverage_ratio = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    free_cash_flow = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)  # in ₹ Crores

    # 4. Growth Metrics
    revenue_growth_yoy = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)  # YoY %
    profit_growth_yoy = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)   # YoY %

    # 5. Shareholding Pattern (%)
    promoter_holding = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    fii_holding = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    dii_holding = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    public_holding = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    # 6. Multi-Factor Scoring (0 to 100)
    overall_score = models.IntegerField(default=50)
    growth_score = models.IntegerField(default=50)
    profitability_score = models.IntegerField(default=50)
    valuation_score = models.IntegerField(default=50)
    financial_health_score = models.IntegerField(default=50)
    ownership_score = models.IntegerField(default=50)

    # 7. Institutional Quantitative Metrics (v2.0)
    piotroski_f_score = models.IntegerField(null=True, blank=True, help_text="Piotroski 9-Criteria F-Score (0-9)")
    altman_z_score = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, help_text="Altman Z-Score Solvency Metric")
    dupont_asset_turnover = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    dupont_equity_multiplier = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)

    # Contextual Qualitative Factors
    positive_factors = models.JSONField(default=list, blank=True)
    negative_factors = models.JSONField(default=list, blank=True)
    missing_fields = models.JSONField(default=list, blank=True)

    # Calculation Provenance
    calculation_version = models.CharField(max_length=30, default="fund-v2.0.0")
    calculated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "fundamental_snapshot"
        ordering = ["-calculated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["instrument", "calculation_version"],
                name="unique_instrument_fund_calc",
            )
        ]

    def __str__(self):
        return f"{self.instrument.display_name} Score: {self.overall_score}/100 [{self.calculation_version}]"
