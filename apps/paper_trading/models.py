"""
PaperTrading Module Models.
Provides a completely isolated, realistic simulated brokerage environment
for the Indian stock market (NSE/BSE), including virtual wallets, multi-leg orders,
real-time MTM positions, and realistic statutory tax & fee tradebook ledgers.
"""
from decimal import Decimal
import uuid

from django.conf import settings
from django.db import models

from apps.core.models import AuditedModel
from apps.instruments.models import ExchangeListing


class OrderSide(models.TextChoices):
    BUY = "BUY", "Buy"
    SELL = "SELL", "Sell"


class ProductType(models.TextChoices):
    CNC = "CNC", "Delivery / Swing (CNC)"
    MIS = "MIS", "Intraday Margin (MIS)"


class OrderType(models.TextChoices):
    MARKET = "MARKET", "Market Order"
    LIMIT = "LIMIT", "Limit Order"
    SL_LIMIT = "SL_LIMIT", "Stop-Loss Limit"
    SL_MARKET = "SL_MARKET", "Stop-Loss Market"


class OrderStatus(models.TextChoices):
    PENDING = "PENDING", "Pending Trigger"
    FILLED = "FILLED", "Filled / Executed"
    PARTIALLY_FILLED = "PARTIALLY_FILLED", "Partially Filled"
    CANCELLED = "CANCELLED", "Cancelled"
    REJECTED = "REJECTED", "Rejected"
    EXPIRED = "EXPIRED", "Expired"


class PositionSide(models.TextChoices):
    LONG = "LONG", "Long"
    SHORT = "SHORT", "Short"


class PaperAccount(AuditedModel):
    """
    Virtual trading account allocated to a user.
    Maintains virtual cash balances, margin utilization, and lifetime realized P&L.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="paper_account",
        db_index=True,
    )
    initial_capital = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("1000000.00"),  # Default ₹10,00,000 (10 Lakhs)
    )
    cash_balance = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("1000000.00"),
    )
    margin_utilized = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    realized_pnl = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "paper_trading_account"
        ordering = ["-created_at"]

    def __str__(self):
        return f"PaperAccount({self.user.username}) - Cash: ₹{self.cash_balance:,.2f}"

    @property
    def available_margin(self) -> Decimal:
        """Liquid cash available to open new positions."""
        return max(Decimal("0.00"), self.cash_balance)

    @property
    def unrealized_pnl(self) -> Decimal:
        """Aggregated mark-to-market floating P&L across all active open positions."""
        return sum(
            (pos.unrealized_pnl for pos in self.positions.filter(quantity__gt=0)),
            Decimal("0.00"),
        ) + sum(
            (pos.unrealized_pnl for pos in self.positions.filter(quantity__lt=0)),
            Decimal("0.00"),
        )

    @property
    def total_portfolio_value(self) -> Decimal:
        """Total equity = Cash Balance + Current Market Value of Open Positions."""
        positions_value = sum(
            (pos.current_market_value for pos in self.positions.exclude(quantity=0)),
            Decimal("0.00"),
        )
        return self.cash_balance + positions_value

    @property
    def total_pnl(self) -> Decimal:
        """Combined lifetime P&L (Realized + Unrealized)."""
        return self.realized_pnl + self.unrealized_pnl

    @property
    def total_return_pct(self) -> Decimal:
        """Percentage return over initial capital."""
        if self.initial_capital and self.initial_capital > Decimal("0.00"):
            equity = self.total_portfolio_value
            return round(((equity - self.initial_capital) / self.initial_capital) * Decimal("100.0"), 2)
        return Decimal("0.00")

    @property
    def margin_utilization_pct(self) -> Decimal:
        """Percentage of total equity currently locked in open positions."""
        equity = self.total_portfolio_value
        if equity > Decimal("0.00") and self.margin_utilized > Decimal("0.00"):
            return round((self.margin_utilized / equity) * Decimal("100.0"), 1)
        return Decimal("0.0")

    def reset_account(self, new_capital: Decimal = Decimal("1000000.00")):
        """Cleanly resets the virtual account to a specified capital amount."""
        self.initial_capital = new_capital
        self.cash_balance = new_capital
        self.margin_utilized = Decimal("0.00")
        self.realized_pnl = Decimal("0.00")
        self.save(update_fields=["initial_capital", "cash_balance", "margin_utilized", "realized_pnl", "updated_at"])
        # Archive / delete open orders and positions
        self.positions.all().delete()
        self.orders.filter(status=OrderStatus.PENDING).update(
            status=OrderStatus.CANCELLED,
            rejection_reason="Account reset by user"
        )


class PaperOrder(AuditedModel):
    """
    Virtual order placed by a user.
    Tracks status, price triggers (Limit/SL/Target), and execution lifecycle.
    """
    account = models.ForeignKey(
        PaperAccount,
        on_delete=models.CASCADE,
        related_name="orders",
        db_index=True,
    )
    listing = models.ForeignKey(
        ExchangeListing,
        on_delete=models.CASCADE,
        related_name="paper_orders",
        db_index=True,
    )
    order_side = models.CharField(
        max_length=4,
        choices=OrderSide.choices,
        db_index=True,
    )
    product_type = models.CharField(
        max_length=4,
        choices=ProductType.choices,
        default=ProductType.CNC,
        db_index=True,
    )
    order_type = models.CharField(
        max_length=12,
        choices=OrderType.choices,
        default=OrderType.MARKET,
        db_index=True,
    )
    quantity = models.PositiveIntegerField()
    filled_quantity = models.PositiveIntegerField(default=0)
    limit_price = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
    )
    trigger_price = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
    )
    target_price = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Optional bracket target execution price.",
    )
    stop_loss_price = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Optional bracket stop-loss execution price.",
    )
    status = models.CharField(
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.PENDING,
        db_index=True,
    )
    rejection_reason = models.CharField(
        max_length=255,
        blank=True,
    )
    setup = models.ForeignKey(
        "trading.TradeSetup",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="paper_orders",
        help_text="Optional link to quantitative swing trade setup that inspired this order.",
    )
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "paper_trading_order"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["account", "status"]),
            models.Index(fields=["listing", "status"]),
        ]

    def __str__(self):
        return f"{self.order_side} {self.quantity}x {self.listing.symbol} [{self.product_type} {self.order_type}] - {self.status}"

    @property
    def is_active(self) -> bool:
        return self.status in (OrderStatus.PENDING, OrderStatus.PARTIALLY_FILLED)


class PaperPosition(AuditedModel):
    """
    Open position for an instrument in a paper trading account.
    Tracks average cost basis, live mark-to-market, and bracket protective orders.
    """
    account = models.ForeignKey(
        PaperAccount,
        on_delete=models.CASCADE,
        related_name="positions",
        db_index=True,
    )
    listing = models.ForeignKey(
        ExchangeListing,
        on_delete=models.CASCADE,
        related_name="paper_positions",
        db_index=True,
    )
    product_type = models.CharField(
        max_length=4,
        choices=ProductType.choices,
        default=ProductType.CNC,
    )
    quantity = models.IntegerField(
        help_text="Net position quantity: positive for Long, negative for Short.",
    )
    average_price = models.DecimalField(
        max_digits=12,
        decimal_places=4,
    )
    current_price = models.DecimalField(
        max_digits=12,
        decimal_places=4,
    )
    unrealized_pnl = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    realized_pnl = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    stop_loss = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
    )
    target = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "paper_trading_position"
        unique_together = [("account", "listing", "product_type")]
        ordering = ["-updated_at"]

    def __str__(self):
        side = "LONG" if self.quantity > 0 else "SHORT"
        return f"{side} {abs(self.quantity)}x {self.listing.symbol} @ ₹{self.average_price:,.2f}"

    @property
    def side(self) -> str:
        return PositionSide.LONG if self.quantity > 0 else PositionSide.SHORT

    @property
    def invested_value(self) -> Decimal:
        """Total capital invested at cost basis."""
        return round(abs(self.quantity) * self.average_price, 2)

    @property
    def current_market_value(self) -> Decimal:
        """Current market value based on live LTP."""
        return round(abs(self.quantity) * self.current_price, 2)

    @property
    def unrealized_pnl_percent(self) -> Decimal:
        """Percentage return on invested capital."""
        if self.average_price and self.average_price > Decimal("0.00"):
            if self.quantity > 0:
                return round(((self.current_price - self.average_price) / self.average_price) * Decimal("100.0"), 2)
            elif self.quantity < 0:
                return round(((self.average_price - self.current_price) / self.average_price) * Decimal("100.0"), 2)
        return Decimal("0.00")

    def recalculate_pnl(self, latest_price: Decimal):
        """Updates position MTM against latest market price."""
        self.current_price = latest_price
        if self.quantity > 0:
            self.unrealized_pnl = round(Decimal(str(self.quantity)) * (latest_price - self.average_price), 2)
        elif self.quantity < 0:
            self.unrealized_pnl = round(Decimal(str(abs(self.quantity))) * (self.average_price - latest_price), 2)
        else:
            self.unrealized_pnl = Decimal("0.00")
        self.save(update_fields=["current_price", "unrealized_pnl", "updated_at"])


class PaperTrade(AuditedModel):
    """
    Immutable tradebook execution record.
    Itemizes trade price, execution slippage, and standard Indian statutory levies.
    """
    account = models.ForeignKey(
        PaperAccount,
        on_delete=models.CASCADE,
        related_name="trades",
        db_index=True,
    )
    order = models.ForeignKey(
        PaperOrder,
        on_delete=models.CASCADE,
        related_name="trades",
        db_index=True,
    )
    listing = models.ForeignKey(
        ExchangeListing,
        on_delete=models.CASCADE,
        related_name="paper_trades",
        db_index=True,
    )
    trade_side = models.CharField(
        max_length=4,
        choices=OrderSide.choices,
        db_index=True,
    )
    product_type = models.CharField(
        max_length=4,
        choices=ProductType.choices,
    )
    execution_price = models.DecimalField(
        max_digits=12,
        decimal_places=4,
    )
    quantity = models.PositiveIntegerField()
    turnover = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )
    brokerage = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("20.00"),
    )
    stt = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    exchange_charges = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    gst = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    sebi_charges = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    stamp_duty = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    total_charges = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    net_realized_pnl = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )
    executed_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )

    class Meta:
        db_table = "paper_trading_trade"
        ordering = ["-executed_at"]

    def __str__(self):
        return f"Trade: {self.trade_side} {self.quantity}x {self.listing.symbol} @ ₹{self.execution_price:,.2f}"
