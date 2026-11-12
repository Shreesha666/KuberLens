from decimal import Decimal

from django.db import models

from apps.core.models import AuditedModel
from apps.instruments.models import ExchangeListing


class DataProvider(models.Model):
    """
    Registry of configured external market data providers.
    """
    code = models.CharField(max_length=20, primary_key=True)  # "JUGAAD", "YAHOO", "ZERODHA"
    name = models.CharField(max_length=100)
    is_enabled = models.BooleanField(default=True)
    priority = models.PositiveSmallIntegerField(default=1)   # 1 = primary, 2 = secondary
    health_status = models.CharField(
        max_length=20,
        choices=[
            ("HEALTHY", "Healthy"),
            ("DEGRADED", "Degraded"),
            ("OFFLINE", "Offline"),
        ],
        default="HEALTHY",
    )
    last_successful_request = models.DateTimeField(null=True, blank=True)
    last_successful_refresh = models.DateTimeField(null=True, blank=True)
    last_error_message = models.TextField(blank=True)
    measured_latency_ms = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "market_data_provider"
        ordering = ["priority", "code"]

    def __str__(self):
        return f"{self.name} ({self.code}) - {self.health_status}"

class MarketQuote(AuditedModel):
    """
    Latest traded quote for an exchange listing with explicit 2D status dimensions:
    source_type (DIRECT, DELAYED, EOD) and freshness_status (FRESH, CACHED, STALE, OFFLINE).
    """
    listing = models.ForeignKey(
        ExchangeListing,
        on_delete=models.CASCADE,
        related_name="quotes",
        db_index=True,
    )
    price = models.DecimalField(max_digits=14, decimal_places=4)
    change = models.DecimalField(max_digits=14, decimal_places=4)
    change_percent = models.DecimalField(max_digits=8, decimal_places=4)
    open = models.DecimalField(max_digits=14, decimal_places=4)
    high = models.DecimalField(max_digits=14, decimal_places=4)
    low = models.DecimalField(max_digits=14, decimal_places=4)
    close = models.DecimalField(max_digits=14, decimal_places=4)
    previous_close = models.DecimalField(max_digits=14, decimal_places=4)
    volume = models.BigIntegerField(default=0)
    source_provider = models.CharField(max_length=20)
    source_type = models.CharField(
        max_length=20,
        choices=[
            ("DIRECT", "Direct Feed"),
            ("DELAYED", "Delayed (15m)"),
            ("EOD", "End of Day"),
        ],
        default="EOD",
    )
    freshness_status = models.CharField(
        max_length=20,
        choices=[
            ("FRESH", "Fresh"),
            ("CACHED", "Cached"),
            ("STALE", "Stale"),
            ("OFFLINE", "Offline"),
        ],
        default="FRESH",
    )
    source_timestamp = models.DateTimeField()
    retrieved_at = models.DateTimeField(db_index=True)
    measured_latency_ms = models.PositiveIntegerField(null=True, blank=True)
    configured_delay_minutes = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "market_market_quote"
        ordering = ["-retrieved_at"]
        indexes = [
            models.Index(fields=["listing", "-retrieved_at"]),
        ]

    def __str__(self):
        return f"{self.listing.symbol}: {self.price} ({self.source_type} / {self.freshness_status})"

class HistoricalCandle(models.Model):
    """
    Raw, immutable time-series OHLCV candle stored strictly in UTC.
    """
    id = models.BigAutoField(primary_key=True)
    listing = models.ForeignKey(
        ExchangeListing,
        on_delete=models.CASCADE,
        related_name="candles",
        db_index=True,
    )
    timestamp = models.DateTimeField(db_index=True)
    interval = models.CharField(max_length=10, default="1d")  # "1d", "1h", "15m", "5m"
    open = models.DecimalField(max_digits=14, decimal_places=4)
    high = models.DecimalField(max_digits=14, decimal_places=4)
    low = models.DecimalField(max_digits=14, decimal_places=4)
    close = models.DecimalField(max_digits=14, decimal_places=4)
    volume = models.BigIntegerField(default=0)
    adjusted_close = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    source_provider = models.CharField(max_length=20)
    retrieved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "market_historical_candle"
        ordering = ["-timestamp"]
        constraints = [
            models.UniqueConstraint(
                fields=["listing", "interval", "timestamp"],
                name="unique_listing_interval_timestamp",
            )
        ]
        indexes = [
            models.Index(fields=["listing", "interval", "-timestamp"]),
        ]

    def __str__(self):
        return f"{self.listing.symbol} [{self.interval}] {self.timestamp}: Close {self.close}"

class DataRefreshLog(AuditedModel):
    """
    Operational audit trail for bulk ingestion, Bhavcopy imports, and health syncs.
    """
    provider = models.ForeignKey(
        DataProvider,
        on_delete=models.CASCADE,
        related_name="refresh_logs",
    )
    data_type = models.CharField(max_length=50)  # "BHAVCOPY", "HISTORICAL", "QUOTE"
    records_ingested = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=[
            ("SUCCESS", "Success"),
            ("FAILED", "Failed"),
            ("PARTIAL", "Partial"),
        ],
        default="SUCCESS",
    )
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    error_details = models.TextField(blank=True)

    class Meta:
        db_table = "market_data_refresh_log"
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.provider.code} {self.data_type} [{self.status}] on {self.started_at}"

class DataQualityIssue(AuditedModel):
    """
    Records data quality flags such as invalid OHLC relations, negative volumes,
    and provider discrepancies without price fabrication.
    """
    listing = models.ForeignKey(
        ExchangeListing,
        on_delete=models.CASCADE,
        related_name="quality_issues",
        null=True,
        blank=True,
    )
    issue_type = models.CharField(
        max_length=50,
        choices=[
            ("INVALID_OHLC", "Invalid OHLC Relation"),
            ("NEGATIVE_VOLUME", "Negative Volume"),
            ("PROVIDER_DISCREPANCY", "Provider Discrepancy"),
            ("GAP_DETECTED", "Historical Gap"),
        ],
    )
    severity = models.CharField(
        max_length=20,
        choices=[
            ("LOW", "Low"),
            ("MEDIUM", "Medium"),
            ("HIGH", "High"),
            ("CRITICAL", "Critical"),
        ],
        default="MEDIUM",
    )
    details = models.JSONField(default=dict)
    detected_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "market_data_quality_issue"
        ordering = ["-detected_at"]

    def __str__(self):
        symbol = self.listing.symbol if self.listing else "GLOBAL"
        return f"[{self.severity}] {self.issue_type} for {symbol}"


class DerivativeContractType(models.TextChoices):
    FUTURES = "FUTURES", "Futures"
    OPTIONS = "OPTIONS", "Options"


class OptionType(models.TextChoices):
    CE = "CE", "Call Option (CE)"
    PE = "PE", "Put Option (PE)"
    NONE = "NONE", "None (Futures)"


class DerivativeContract(AuditedModel):
    """
    Derivative contract specification for NSE/BSE Equity & Index Futures and Options.
    Prepares data structures for Phase 10 F&O intelligence.
    """
    underlying_listing = models.ForeignKey(
        ExchangeListing,
        on_delete=models.CASCADE,
        related_name="derivative_contracts",
        db_index=True,
    )
    contract_type = models.CharField(
        max_length=20,
        choices=DerivativeContractType.choices,
        default=DerivativeContractType.OPTIONS,
        db_index=True,
    )
    option_type = models.CharField(
        max_length=10,
        choices=OptionType.choices,
        default=OptionType.NONE,
        db_index=True,
    )
    strike_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        db_index=True,
    )
    expiry_date = models.DateField(db_index=True)
    lot_size = models.PositiveIntegerField(default=1)
    tick_size = models.DecimalField(max_digits=6, decimal_places=4, default=Decimal("0.0500"))
    trading_symbol = models.CharField(max_length=80, db_index=True)
    open_interest = models.BigIntegerField(default=0)
    change_in_oi = models.BigIntegerField(default=0)
    implied_volatility = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "market_derivative_contract"
        ordering = ["expiry_date", "strike_price", "option_type"]
        indexes = [
            models.Index(fields=["underlying_listing", "expiry_date", "contract_type"]),
            models.Index(fields=["trading_symbol"]),
        ]

    def __str__(self) -> str:
        return f"{self.trading_symbol} (Lot: {self.lot_size})"

