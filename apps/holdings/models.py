"""
Holding & Transaction Ledger Models.
Implements the Immutable Transaction Ledger, FIFO Lot Allocation, and Derived Holding State.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.core.models import AuditedModel


class TransactionType(models.TextChoices):
    BUY = "BUY", "Buy"
    SELL = "SELL", "Sell"
    DIVIDEND = "DIVIDEND", "Cash Dividend"
    BONUS = "BONUS", "Bonus Issue"
    SPLIT = "SPLIT", "Stock Split"
    BUY_REVERSAL = "BUY_REVERSAL", "Buy Reversal"
    SELL_REVERSAL = "SELL_REVERSAL", "Sell Reversal"
    COST_ADJUSTMENT = "COST_ADJUSTMENT", "Cost Basis Adjustment"


class HoldingTransaction(AuditedModel):
    """
    Immutable transaction ledger entry. Source of truth for all portfolio calculations.
    Direct modification or deletion of historical transactions is forbidden.
    """
    portfolio = models.ForeignKey(
        "portfolio.Portfolio",
        on_delete=models.CASCADE,
        related_name="transactions",
        db_index=True,
    )
    listing = models.ForeignKey(
        "instruments.ExchangeListing",
        on_delete=models.CASCADE,
        related_name="transactions",
        db_index=True,
    )
    transaction_type = models.CharField(
        max_length=25,
        choices=TransactionType.choices,
        default=TransactionType.BUY,
        db_index=True,
    )
    quantity = models.PositiveIntegerField(default=0)
    price = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=Decimal("0.0000"),
    )
    brokerage = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    statutory_taxes = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="STT, GST, Stamp Duty, SEBI turnover fees",
    )
    executed_at = models.DateTimeField(db_index=True)
    reference_transaction_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        db_index=True,
        help_text="Target transaction ID for reversals or adjustments",
    )
    split_ratio = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="Ratio for split/bonus e.g. '2:1' (adds 1 share per 2 held)",
    )
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "holdings_holding_transaction"
        ordering = ["executed_at", "created_at"]
        indexes = [
            models.Index(fields=["portfolio", "listing", "executed_at"]),
            models.Index(fields=["portfolio", "transaction_type", "executed_at"]),
        ]

    def clean(self):
        super().clean()
        if self.transaction_type in (TransactionType.BUY, TransactionType.SELL) and self.quantity <= 0:
            raise ValidationError("Quantity must be greater than zero for Buy and Sell transactions.")
        if self.transaction_type in (TransactionType.BUY, TransactionType.SELL) and self.price <= Decimal("0.0"):
            raise ValidationError("Price must be greater than zero for Buy and Sell transactions.")

    @property
    def gross_amount(self) -> Decimal:
        return Decimal(str(self.quantity)) * self.price

    @property
    def total_charges(self) -> Decimal:
        return self.brokerage + self.statutory_taxes

    @property
    def effective_total_cost(self) -> Decimal:
        """
        Total cost for buys (capitalized charges) or net proceeds for sells (charges deducted).
        """
        if self.transaction_type == TransactionType.BUY:
            return self.gross_amount + self.total_charges
        elif self.transaction_type == TransactionType.SELL:
            return max(Decimal("0.00"), self.gross_amount - self.total_charges)
        return self.gross_amount

    @property
    def effective_unit_cost(self) -> Decimal:
        if self.quantity > 0:
            return self.effective_total_cost / Decimal(str(self.quantity))
        return Decimal("0.0000")

    def __str__(self):
        return f"{self.transaction_type} {self.quantity} {self.listing.symbol} @ ₹{self.price} on {self.executed_at.date()}"


class Holding(AuditedModel):
    """
    Derived materialization of an active position for a portfolio & listing.
    Deterministically calculated from the immutable transaction ledger.
    """
    portfolio = models.ForeignKey(
        "portfolio.Portfolio",
        on_delete=models.CASCADE,
        related_name="holdings",
        db_index=True,
    )
    listing = models.ForeignKey(
        "instruments.ExchangeListing",
        on_delete=models.CASCADE,
        related_name="holdings",
        db_index=True,
    )
    total_quantity = models.PositiveIntegerField(default=0)
    average_buy_price = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=Decimal("0.0000"),
    )
    invested_amount = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    current_price = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=Decimal("0.0000"),
    )
    current_value = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    unrealised_pnl = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    unrealised_pnl_percent = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    realised_pnl = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    dividend_earned = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    first_purchased_at = models.DateTimeField(null=True, blank=True)
    last_reconciled_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "holdings_holding"
        ordering = ["listing__symbol"]
        constraints = [
            models.UniqueConstraint(
                fields=["portfolio", "listing"],
                name="unique_portfolio_listing_holding",
            )
        ]

    def __str__(self):
        return f"{self.listing.symbol} ({self.total_quantity} shares) - {self.portfolio.name}"


class LotAllocation(AuditedModel):
    """
    Audit record linking a SELL transaction to the specific BUY lot(s) it consumed (FIFO).
    Stores allocated cost basis and realized P&L for precise historical tax accounting.
    """
    sell_transaction = models.ForeignKey(
        HoldingTransaction,
        on_delete=models.CASCADE,
        related_name="closed_allocations",
        db_index=True,
    )
    buy_transaction = models.ForeignKey(
        HoldingTransaction,
        on_delete=models.CASCADE,
        related_name="lot_allocations",
        db_index=True,
    )
    matched_quantity = models.PositiveIntegerField()
    allocated_unit_cost = models.DecimalField(max_digits=14, decimal_places=4)
    allocated_cost_basis = models.DecimalField(max_digits=16, decimal_places=2)
    allocated_net_proceeds = models.DecimalField(max_digits=16, decimal_places=2)
    realised_pnl = models.DecimalField(max_digits=16, decimal_places=2)
    allocated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "holdings_lot_allocation"
        ordering = ["-allocated_at"]

    def __str__(self):
        return (
            f"Matched {self.matched_quantity} sh of {self.sell_transaction.listing.symbol} "
            f"(P&L: ₹{self.realised_pnl})"
        )
