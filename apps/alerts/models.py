"""
Alert Rules and Condition Models.
Complies with Master Specification Section 20.
Enforces price, technical, and portfolio alerts with market-hours awareness
and deduplication cooldown protection.
"""
from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.core.models import AuditedModel
from apps.instruments.models import ExchangeListing


class AlertType(models.TextChoices):
    # Price alerts
    PRICE_ABOVE = "PRICE_ABOVE", "Price Crosses Above"
    PRICE_BELOW = "PRICE_BELOW", "Price Crosses Below"
    PERCENT_MOVE = "PERCENT_MOVE", "Daily % Movement Above"
    BREAKOUT_52W_HIGH = "BREAKOUT_52W_HIGH", "52-Week High Breakout"
    BREAKDOWN_52W_LOW = "BREAKDOWN_52W_LOW", "52-Week Low Breakdown"

    # Technical alerts
    RSI_OVERSOLD = "RSI_OVERSOLD", "RSI Oversold (<= Threshold)"
    RSI_OVERBOUGHT = "RSI_OVERBOUGHT", "RSI Overbought (>= Threshold)"
    MACD_BULLISH_CROSS = "MACD_BULLISH_CROSS", "MACD Bullish Crossover"
    MACD_BEARISH_CROSS = "MACD_BEARISH_CROSS", "MACD Bearish Crossover"
    SMA_CROSSOVER = "SMA_CROSSOVER", "SMA 20 Crosses Above SMA 50"
    SMA_BEARISH_CROSS = "SMA_BEARISH_CROSS", "SMA 20 Crosses Below SMA 50"
    GOLDEN_CROSS = "GOLDEN_CROSS", "Golden Cross: 50 SMA > 200 SMA"
    DEATH_CROSS = "DEATH_CROSS", "Death Cross: 50 SMA < 200 SMA"
    VOLUME_SPIKE = "VOLUME_SPIKE", "Volume Surge (> 2x 20-Day Avg)"
    BOLLINGER_UPPER_BREAK = "BOLLINGER_UPPER_BREAK", "Price Touches Upper Bollinger Band"
    BOLLINGER_LOWER_BREAK = "BOLLINGER_LOWER_BREAK", "Price Touches Lower Bollinger Band"

    # Portfolio alerts
    PORTFOLIO_STOP_LOSS = "PORTFOLIO_STOP_LOSS", "Holding Stop-Loss Hit"
    PORTFOLIO_TARGET = "PORTFOLIO_TARGET", "Holding Profit Target Hit"
    PORTFOLIO_DRAWDOWN = "PORTFOLIO_DRAWDOWN", "Portfolio Drawdown Alert"
    CONCENTRATION_THRESHOLD = "CONCENTRATION_THRESHOLD", "Holding Concentration (> Threshold %)"


class AlertRule(AuditedModel):
    """
    User-configured monitoring rule evaluating live market quotes, technical indicators,
    and portfolio holdings.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="alert_rules",
    )
    listing = models.ForeignKey(
        ExchangeListing,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="alert_rules",
        help_text="Stock listing to monitor. Null for account-wide portfolio alerts.",
    )
    alert_type = models.CharField(
        max_length=50,
        choices=AlertType.choices,
        db_index=True,
    )
    target_value = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        null=True,
        blank=True,
        default=Decimal("0.0000"),
        help_text="Threshold price, percentage, or indicator value.",
    )
    notes = models.CharField(
        max_length=250,
        blank=True,
        help_text="Optional user note or trade thesis reminder.",
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Enabled or paused.",
    )
    is_market_hours_only = models.BooleanField(
        default=True,
        help_text="When True, evaluates alerts strictly during active NSE trading hours.",
    )
    cooldown_minutes = models.PositiveIntegerField(
        default=60,
        help_text="Minimum minutes to wait between duplicate triggers for unchanged conditions.",
    )
    last_triggered_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    trigger_count = models.PositiveIntegerField(
        default=0,
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Alert Rule"
        verbose_name_plural = "Alert Rules"
        indexes = [
            models.Index(fields=["user", "is_active"], name="idx_alert_user_active"),
            models.Index(fields=["listing", "alert_type"], name="idx_alert_listing_type"),
        ]

    def __str__(self) -> str:
        sym = f"[{self.listing.symbol}] " if self.listing else "[PORTFOLIO] "
        return f"{self.user.username} - {sym}{self.get_alert_type_display()} @ {self.target_value}"

