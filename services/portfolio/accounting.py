"""
Portfolio FIFO Accounting Engine & Reconciliation Service.
Calculates position quantities, capitalized acquisition costs, realized & unrealized P&L,
and corporate action adjustments using the Immutable Transaction Ledger.
"""
import logging
from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.holdings.models import (
    Holding,
    HoldingTransaction,
    LotAllocation,
    TransactionType,
)
from apps.instruments.models import ExchangeListing
from apps.portfolio.models import Portfolio

logger = logging.getLogger(__name__)


@dataclass
class OpenLot:
    buy_transaction: HoldingTransaction
    remaining_quantity: int
    effective_unit_cost: Decimal
    total_lot_cost: Decimal


class FIFOAccountingEngine:
    @classmethod
    def reconcile_holding(
        cls,
        portfolio: Portfolio,
        listing: ExchangeListing,
        current_price: Decimal | None = None,
    ) -> Holding:
        """
        Reconciles the entire transaction history for a portfolio and listing in chronological order.
        Recomputes FIFO lot matching, updates LotAllocation records, and saves the derived Holding.
        """
        transactions = list(
            HoldingTransaction.objects.filter(portfolio=portfolio, listing=listing)
            .order_by("executed_at", "created_at")
        )

        # Clear existing lot allocations for this pair to re-match deterministically
        sell_tx_ids = [t.id for t in transactions if t.transaction_type == TransactionType.SELL]
        LotAllocation.objects.filter(sell_transaction_id__in=sell_tx_ids).delete()

        open_lots: list[OpenLot] = []
        cum_realised_pnl = Decimal("0.00")
        cum_dividend = Decimal("0.00")
        first_purchase_dt = None

        # Identify reversed transaction IDs
        reversed_tx_ids = set()
        for tx in transactions:
            if tx.transaction_type in (TransactionType.BUY_REVERSAL, TransactionType.SELL_REVERSAL):
                if tx.reference_transaction_id:
                    reversed_tx_ids.add(str(tx.reference_transaction_id))

        new_allocations: list[LotAllocation] = []

        with transaction.atomic():
            for tx in transactions:
                # Skip reversed transactions and the reversal entries themselves during forward processing
                if str(tx.id) in reversed_tx_ids:
                    logger.info("Skipping reversed transaction %s", tx.id)
                    continue

                if tx.transaction_type == TransactionType.BUY:
                    if first_purchase_dt is None:
                        first_purchase_dt = tx.executed_at

                    # Buy charges are capitalized into unit cost basis
                    tot_cost = tx.effective_total_cost
                    unit_cost = tot_cost / Decimal(str(tx.quantity)) if tx.quantity > 0 else Decimal("0.0000")
                    open_lots.append(
                        OpenLot(
                            buy_transaction=tx,
                            remaining_quantity=tx.quantity,
                            effective_unit_cost=unit_cost,
                            total_lot_cost=tot_cost,
                        )
                    )

                elif tx.transaction_type == TransactionType.SELL:
                    needed_qty = tx.quantity
                    # Deduct sell brokerage and statutory taxes from proceeds
                    net_proceeds = tx.effective_total_cost
                    net_unit_proceeds = net_proceeds / Decimal(str(tx.quantity)) if tx.quantity > 0 else Decimal("0.0000")

                    while needed_qty > 0 and open_lots:
                        current_lot = open_lots[0]
                        matched_qty = min(needed_qty, current_lot.remaining_quantity)

                        alloc_cost = Decimal(str(matched_qty)) * current_lot.effective_unit_cost
                        alloc_proceeds = Decimal(str(matched_qty)) * net_unit_proceeds
                        realised_slice = alloc_proceeds - alloc_cost

                        new_allocations.append(
                            LotAllocation(
                                sell_transaction=tx,
                                buy_transaction=current_lot.buy_transaction,
                                matched_quantity=matched_qty,
                                allocated_unit_cost=current_lot.effective_unit_cost,
                                allocated_cost_basis=alloc_cost,
                                allocated_net_proceeds=alloc_proceeds,
                                realised_pnl=realised_slice,
                                allocated_at=tx.executed_at,
                            )
                        )

                        cum_realised_pnl += realised_slice
                        needed_qty -= matched_qty
                        current_lot.remaining_quantity -= matched_qty

                        if current_lot.remaining_quantity == 0:
                            open_lots.pop(0)

                elif tx.transaction_type == TransactionType.DIVIDEND:
                    cum_dividend += tx.gross_amount

                elif tx.transaction_type == TransactionType.BONUS:
                    # Bonus Issue: Distribute bonus shares proportionally across all open lots
                    # Total cost remains unchanged; effective unit cost decreases
                    bonus_qty = tx.quantity
                    total_open = sum(lot.remaining_quantity for lot in open_lots)
                    if total_open > 0 and bonus_qty > 0:
                        allocated_bonus = 0
                        for i, lot in enumerate(open_lots):
                            # Proportional share of bonus
                            if i == len(open_lots) - 1:
                                lot_bonus = bonus_qty - allocated_bonus
                            else:
                                lot_bonus = int(round(bonus_qty * (lot.remaining_quantity / total_open)))
                                allocated_bonus += lot_bonus

                            lot.remaining_quantity += lot_bonus
                            if lot.remaining_quantity > 0:
                                lot.effective_unit_cost = lot.total_lot_cost / Decimal(str(lot.remaining_quantity))

                elif tx.transaction_type == TransactionType.SPLIT:
                    # Stock Split: e.g. 5:1 (1 old share becomes 5 new shares)
                    # Parses split_ratio or uses quantity
                    mult = 1
                    div = 1
                    if tx.split_ratio and ":" in tx.split_ratio:
                        parts = tx.split_ratio.split(":")
                        mult = int(parts[0])
                        div = int(parts[1]) if len(parts) > 1 and int(parts[1]) > 0 else 1
                    elif tx.quantity > 0:
                        mult = tx.quantity

                    for lot in open_lots:
                        new_qty = int(lot.remaining_quantity * mult / div)
                        lot.remaining_quantity = new_qty
                        if new_qty > 0:
                            lot.effective_unit_cost = lot.total_lot_cost / Decimal(str(new_qty))

                elif tx.transaction_type == TransactionType.COST_ADJUSTMENT:
                    # Cost basis adjustment: adjusts open lot costs
                    adj_amount = tx.price  # Can be positive or negative
                    total_open = sum(lot.remaining_quantity for lot in open_lots)
                    if total_open > 0:
                        for lot in open_lots:
                            lot_adj = adj_amount * (Decimal(str(lot.remaining_quantity)) / Decimal(str(total_open)))
                            lot.total_lot_cost = max(Decimal("0.00"), lot.total_lot_cost + lot_adj)
                            if lot.remaining_quantity > 0:
                                lot.effective_unit_cost = lot.total_lot_cost / Decimal(str(lot.remaining_quantity))

            if new_allocations:
                LotAllocation.objects.bulk_create(new_allocations)

            # Compute aggregated holding metrics
            total_remaining_qty = sum(lot.remaining_quantity for lot in open_lots)
            total_invested_capital = sum(
                Decimal(str(lot.remaining_quantity)) * lot.effective_unit_cost for lot in open_lots
            )
            avg_cost = (
                total_invested_capital / Decimal(str(total_remaining_qty))
                if total_remaining_qty > 0
                else Decimal("0.0000")
            )

            # Determine price
            if current_price is None:
                from apps.market.models import MarketQuote
                latest_quote = MarketQuote.objects.filter(listing=listing).order_by("-retrieved_at").first()
                if latest_quote:
                    current_price = latest_quote.price
                else:
                    current_price = avg_cost

            market_val = Decimal(str(total_remaining_qty)) * current_price
            unrealised = market_val - total_invested_capital
            unrealised_pct = (
                (unrealised / total_invested_capital * Decimal("100.0"))
                if total_invested_capital > Decimal("0.00")
                else Decimal("0.00")
            )

            holding, _ = Holding.objects.update_or_create(
                portfolio=portfolio,
                listing=listing,
                defaults={
                    "total_quantity": total_remaining_qty,
                    "average_buy_price": avg_cost,
                    "invested_amount": total_invested_capital,
                    "current_price": current_price,
                    "current_value": market_val,
                    "unrealised_pnl": unrealised,
                    "unrealised_pnl_percent": unrealised_pct,
                    "realised_pnl": cum_realised_pnl,
                    "dividend_earned": cum_dividend,
                    "first_purchased_at": first_purchase_dt,
                    "last_reconciled_at": timezone.now(),
                },
            )
            return holding

    @classmethod
    def get_open_lots(cls, portfolio: Portfolio, listing: ExchangeListing) -> list[OpenLot]:
        """
        Returns breakdown of active unclosed FIFO lots for a holding.
        """
        transactions = list(
            HoldingTransaction.objects.filter(portfolio=portfolio, listing=listing)
            .order_by("executed_at", "created_at")
        )

        reversed_tx_ids = {
            str(tx.reference_transaction_id)
            for tx in transactions
            if tx.transaction_type in (TransactionType.BUY_REVERSAL, TransactionType.SELL_REVERSAL)
            and tx.reference_transaction_id
        }

        open_lots: list[OpenLot] = []
        for tx in transactions:
            if str(tx.id) in reversed_tx_ids:
                continue

            if tx.transaction_type == TransactionType.BUY:
                unit_cost = tx.effective_total_cost / Decimal(str(tx.quantity)) if tx.quantity > 0 else Decimal("0.00")
                open_lots.append(
                    OpenLot(
                        buy_transaction=tx,
                        remaining_quantity=tx.quantity,
                        effective_unit_cost=unit_cost,
                        total_lot_cost=tx.effective_total_cost,
                    )
                )
            elif tx.transaction_type == TransactionType.SELL:
                needed_qty = tx.quantity
                while needed_qty > 0 and open_lots:
                    current_lot = open_lots[0]
                    matched_qty = min(needed_qty, current_lot.remaining_quantity)
                    needed_qty -= matched_qty
                    current_lot.remaining_quantity -= matched_qty
                    if current_lot.remaining_quantity == 0:
                        open_lots.pop(0)

            elif tx.transaction_type == TransactionType.BONUS:
                bonus_qty = tx.quantity
                total_open = sum(lot.remaining_quantity for lot in open_lots)
                if total_open > 0 and bonus_qty > 0:
                    allocated_bonus = 0
                    for i, lot in enumerate(open_lots):
                        if i == len(open_lots) - 1:
                            lot_bonus = bonus_qty - allocated_bonus
                        else:
                            lot_bonus = int(round(bonus_qty * (lot.remaining_quantity / total_open)))
                            allocated_bonus += lot_bonus
                        lot.remaining_quantity += lot_bonus
                        if lot.remaining_quantity > 0:
                            lot.effective_unit_cost = lot.total_lot_cost / Decimal(str(lot.remaining_quantity))

            elif tx.transaction_type == TransactionType.SPLIT:
                mult = 1
                div = 1
                if tx.split_ratio and ":" in tx.split_ratio:
                    parts = tx.split_ratio.split(":")
                    mult = int(parts[0])
                    div = int(parts[1]) if len(parts) > 1 and int(parts[1]) > 0 else 1
                elif tx.quantity > 0:
                    mult = tx.quantity

                for lot in open_lots:
                    new_qty = int(lot.remaining_quantity * mult / div)
                    lot.remaining_quantity = new_qty
                    if new_qty > 0:
                        lot.effective_unit_cost = lot.total_lot_cost / Decimal(str(new_qty))

            elif tx.transaction_type == TransactionType.COST_ADJUSTMENT:
                adj_amount = tx.price
                total_open = sum(lot.remaining_quantity for lot in open_lots)
                if total_open > 0:
                    for lot in open_lots:
                        lot_adj = adj_amount * (Decimal(str(lot.remaining_quantity)) / Decimal(str(total_open)))
                        lot.total_lot_cost = max(Decimal("0.00"), lot.total_lot_cost + lot_adj)
                        if lot.remaining_quantity > 0:
                            lot.effective_unit_cost = lot.total_lot_cost / Decimal(str(lot.remaining_quantity))

        return open_lots
