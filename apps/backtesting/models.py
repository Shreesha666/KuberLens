"""
Backtesting Models.
Complies with Master Specification Section 21.
Stores user strategies, simulation configurations, trade execution logs,
and verified performance metrics strictly accounting for slippage and transaction costs.
"""
from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.core.models import AuditedModel
from apps.instruments.models import ExchangeListing


class StrategyType(models.TextChoices):
    SMA_CROSSOVER = "SMA_CROSSOVER", "SMA 20/50 Golden Cross"
    RSI_MEAN_REVERSION = "RSI_MEAN_REVERSION", "RSI Oversold Pullback (<30)"
    BREAKOUT_MOMENTUM = "BREAKOUT_MOMENTUM", "20-Day High Breakout"
    MACD_CROSSOVER = "MACD_CROSSOVER", "MACD Bullish Signal Cross"


class BacktestStatus(models.TextChoices):
    COMPLETED = "COMPLETED", "Completed"
    FAILED = "FAILED", "Failed"


class BacktestStrategy(AuditedModel):
    """
    Configured quantitative trading strategy with risk parameters and execution costs.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="backtest_strategies",
        help_text="Owner user, or null if pre-packaged system strategy.",
    )
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    strategy_type = models.CharField(
        max_length=50,
        choices=StrategyType.choices,
        default=StrategyType.SMA_CROSSOVER,
        db_index=True,
    )
    default_parameters = models.JSONField(
        default=dict,
        blank=True,
        help_text="Custom strategy parameters (e.g. fast_sma, slow_sma, rsi_entry).",
    )
    stop_loss_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("3.00"),
        help_text="Stop loss percentage threshold.",
    )
    target_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("6.00"),
        help_text="Profit target percentage threshold.",
    )
    slippage_pct = models.DecimalField(
        max_digits=5,
        decimal_places=3,
        default=Decimal("0.050"),
        help_text="Estimated percentage execution slippage per order fill (e.g. 0.05%).",
    )
    brokerage_pct = models.DecimalField(
        max_digits=5,
        decimal_places=3,
        default=Decimal("0.030"),
        help_text="Brokerage and regulatory charges percentage per leg.",
    )
    is_system_preset = models.BooleanField(
        default=False,
        db_index=True,
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Backtest Strategy"
        verbose_name_plural = "Backtest Strategies"

    def __str__(self) -> str:
        return f"{self.name} ({self.get_strategy_type_display()})"


class BacktestRun(AuditedModel):
    """
    Historical backtest execution run with complete trade log and performance KPIs.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="backtest_runs",
    )
    strategy = models.ForeignKey(
        BacktestStrategy,
        on_delete=models.CASCADE,
        related_name="runs",
    )
    listing = models.ForeignKey(
        ExchangeListing,
        on_delete=models.CASCADE,
        related_name="backtest_runs",
    )
    start_date = models.DateField()
    end_date = models.DateField()
    initial_capital = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("100000.00"),
    )
    final_capital = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )
    total_return_pct = models.DecimalField(
        max_digits=8,
        decimal_places=2,
    )
    cagr_pct = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    max_drawdown_pct = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    win_rate_pct = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    profit_factor = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    total_trades = models.PositiveIntegerField(default=0)
    winning_trades = models.PositiveIntegerField(default=0)
    losing_trades = models.PositiveIntegerField(default=0)
    avg_profit_pct = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    avg_loss_pct = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    avg_holding_days = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        default=Decimal("0.0"),
    )
    benchmark_return_pct = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
    )
    trades_log = models.JSONField(
        default=list,
        help_text="Detailed chronological trade execution ledger.",
    )
    equity_curve = models.JSONField(
        default=list,
        help_text="Chronological portfolio equity snapshots for charting.",
    )
    status = models.CharField(
        max_length=20,
        choices=BacktestStatus.choices,
        default=BacktestStatus.COMPLETED,
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Backtest Run"
        verbose_name_plural = "Backtest Runs"
        indexes = [
            models.Index(fields=["user", "-created_at"], name="idx_bt_user_created"),
            models.Index(fields=["listing", "strategy"], name="idx_bt_listing_strat"),
        ]

    def __str__(self) -> str:
        return f"{self.strategy.name} on {self.listing.symbol}: {self.total_return_pct:+}% Return"

