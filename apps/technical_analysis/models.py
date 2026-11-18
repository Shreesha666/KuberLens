"""
Technical Analysis Data Models.
Stores versioned indicator snapshots calculated deterministically from raw historical candles.
"""
from django.db import models
from django.utils import timezone

from apps.core.models import AuditedModel


class TechnicalIndicatorSnapshot(AuditedModel):
    """
    Derived analytical indicator snapshot for an exchange listing at a specific candle timestamp.
    Decoupled from raw candles and versioned so indicators can be recalculated without redownload.
    """
    listing = models.ForeignKey(
        "instruments.ExchangeListing",
        on_delete=models.CASCADE,
        related_name="technical_snapshots",
        db_index=True,
    )
    interval = models.CharField(max_length=10, default="1d", db_index=True)
    timestamp = models.DateTimeField(db_index=True)

    # 1. Trend Indicators
    sma_20 = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    sma_50 = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    sma_100 = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    sma_200 = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    ema_9 = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    ema_20 = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    ema_50 = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    macd_line = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    macd_signal = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    macd_histogram = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)

    # 2. Momentum Indicators
    rsi_14 = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    stoch_rsi_k = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    stoch_rsi_d = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    adx_14 = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    roc_10 = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    supertrend_value = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    supertrend_direction = models.IntegerField(null=True, blank=True, help_text="1 for Bullish, -1 for Bearish")
    vwap = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)

    # 3. Volatility Indicators
    bollinger_upper = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    bollinger_middle = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    bollinger_lower = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    bollinger_bandwidth = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    atr_14 = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)

    # 4. Volume Indicators
    volume_sma_20 = models.BigIntegerField(null=True, blank=True)
    relative_volume = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    obv = models.BigIntegerField(null=True, blank=True)

    # 5. Price Structure
    support_level = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    resistance_level = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    swing_high = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    swing_low = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)

    # 6. Generated Signals
    trend_signal = models.CharField(
        max_length=20,
        choices=[("BULLISH", "Bullish"), ("BEARISH", "Bearish"), ("NEUTRAL", "Neutral")],
        default="NEUTRAL",
    )
    rsi_signal = models.CharField(
        max_length=20,
        choices=[("OVERBOUGHT", "Overbought"), ("OVERSOLD", "Oversold"), ("NEUTRAL", "Neutral")],
        default="NEUTRAL",
    )
    macd_signal_type = models.CharField(
        max_length=20,
        choices=[("BULLISH_CROSS", "Bullish Crossover"), ("BEARISH_CROSS", "Bearish Crossover"), ("NEUTRAL", "Neutral")],
        default="NEUTRAL",
    )
    ma_cross_signal = models.CharField(
        max_length=20,
        choices=[("GOLDEN_CROSS", "Golden Cross"), ("DEATH_CROSS", "Death Cross"), ("NEUTRAL", "Neutral")],
        default="NEUTRAL",
    )
    breakout_signal = models.CharField(
        max_length=25,
        choices=[("RESISTANCE_BREAKOUT", "Resistance Breakout"), ("SUPPORT_BREAKDOWN", "Support Breakdown"), ("NEUTRAL", "Neutral")],
        default="NEUTRAL",
    )

    # Calculation Provenance
    calculation_version = models.CharField(max_length=30, default="tech-v2.0.0")
    calculated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "technical_indicator_snapshot"
        ordering = ["-timestamp"]
        constraints = [
            models.UniqueConstraint(
                fields=["listing", "interval", "timestamp", "calculation_version"],
                name="unique_listing_candle_calc",
            )
        ]
        indexes = [
            models.Index(fields=["listing", "interval", "-timestamp"]),
            models.Index(fields=["trend_signal", "rsi_signal"]),
        ]

    def __str__(self):
        return f"{self.listing.symbol} ({self.interval}) @ {self.timestamp} [{self.calculation_version}]"
