"""
PaperTrading Execution & Order Routing Engine.
Handles order lifecycle validation, pre-trade margin checks, realistic fill simulation
with dynamic bid-ask slippage, position MTM accounting, and automated stop-loss/target triggers.
"""
from decimal import Decimal, ROUND_HALF_UP
import logging
from typing import Optional

from django.db import transaction

from apps.instruments.models import ExchangeListing
from apps.market.models import HistoricalCandle, MarketQuote
from apps.paper_trading.models import (
    OrderSide,
    OrderStatus,
    OrderType,
    PaperAccount,
    PaperOrder,
    PaperPosition,
    PaperTrade,
    ProductType,
)
from services.paper_trading.tax_calculator import IndianTaxCalculator

logger = logging.getLogger(__name__)


class PaperTradingExecutionEngine:
    """
    Central execution, order matching, and account clearing engine for Paper Trading.
    """
    DEFAULT_SLIPPAGE_RATE = Decimal("0.0005")  # 0.05% bid-ask impact cost
    MIS_LEVERAGE = Decimal("5.0")              # 5x leverage for Intraday MIS

    @classmethod
    def get_latest_price(cls, listing: ExchangeListing) -> Decimal:
        """Fetches the most current market quote or historical close for an instrument."""
        quote = MarketQuote.objects.filter(listing=listing).order_by("-retrieved_at").first()
        if quote and quote.price and quote.price > Decimal("0.0"):
            return Decimal(str(quote.price))

        candle = HistoricalCandle.objects.filter(listing=listing).order_by("-timestamp").first()
        if candle and candle.close and candle.close > Decimal("0.0"):
            return Decimal(str(candle.close))

        return Decimal("100.00")

    @classmethod
    def calculate_required_margin(
        cls,
        quantity: int,
        price: Decimal,
        side: str,
        product_type: str,
    ) -> Decimal:
        """Calculates margin requirement based on product type leverage."""
        turnover = Decimal(str(quantity)) * price
        if product_type == ProductType.MIS:
            return (turnover / cls.MIS_LEVERAGE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        elif side == OrderSide.BUY:
            return turnover.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return Decimal("0.00")  # CNC Sell does not require cash margin, but requires holding shares

    @classmethod
    def place_order(
        cls,
        account: PaperAccount,
        listing: ExchangeListing,
        order_side: str,
        product_type: str = ProductType.CNC,
        order_type: str = OrderType.MARKET,
        quantity: int = 1,
        limit_price: Optional[Decimal] = None,
        trigger_price: Optional[Decimal] = None,
        target_price: Optional[Decimal] = None,
        stop_loss_price: Optional[Decimal] = None,
        setup=None,
        notes: str = "",
    ) -> PaperOrder:
        """
        Validates, persists, and routes an order through the simulated exchange matching engine.
        """
        if quantity <= 0:
            raise ValueError("Order quantity must be greater than zero.")

        current_market_price = cls.get_latest_price(listing)
        reference_price = limit_price if limit_price and limit_price > Decimal("0.0") else current_market_price
        required_margin = cls.calculate_required_margin(quantity, reference_price, order_side, product_type)

        # Pre-Trade Validation
        rejection_reason = ""
        # 1. CNC Sell validation: User cannot sell delivery shares they do not hold
        if product_type == ProductType.CNC and order_side == OrderSide.SELL:
            existing_pos = PaperPosition.objects.filter(
                account=account, listing=listing, product_type=ProductType.CNC
            ).first()
            if not existing_pos or existing_pos.quantity < quantity:
                avail_qty = existing_pos.quantity if existing_pos else 0
                rejection_reason = f"Insufficient CNC holdings to sell. Available: {avail_qty} shares."

        # 2. Margin availability check for Buy and MIS Short
        elif required_margin > account.available_margin:
            rejection_reason = (
                f"Insufficient funds. Required margin: ₹{required_margin:,.2f}, "
                f"Available cash: ₹{account.available_margin:,.2f}."
            )

        status = OrderStatus.REJECTED if rejection_reason else OrderStatus.PENDING

        order = PaperOrder.objects.create(
            account=account,
            listing=listing,
            order_side=order_side,
            product_type=product_type,
            order_type=order_type,
            quantity=quantity,
            limit_price=limit_price,
            trigger_price=trigger_price,
            target_price=target_price,
            stop_loss_price=stop_loss_price,
            status=status,
            rejection_reason=rejection_reason,
            setup=setup,
            notes=notes,
        )

        if status == OrderStatus.REJECTED:
            return order

        # Immediate Matching / Execution Routing
        if order_type == OrderType.MARKET:
            # Apply dynamic bid-ask slippage
            if order_side == OrderSide.BUY:
                exec_price = (current_market_price * (Decimal("1.0") + cls.DEFAULT_SLIPPAGE_RATE)).quantize(
                    Decimal("0.05"), rounding=ROUND_HALF_UP
                )
            else:
                exec_price = (current_market_price * (Decimal("1.0") - cls.DEFAULT_SLIPPAGE_RATE)).quantize(
                    Decimal("0.05"), rounding=ROUND_HALF_UP
                )
            cls._execute_fill(order, exec_price, quantity)

        elif order_type == OrderType.LIMIT:
            # Check if limit order is immediately marketable
            is_marketable = (
                (order_side == OrderSide.BUY and current_market_price <= limit_price)
                or (order_side == OrderSide.SELL and current_market_price >= limit_price)
            )
            if is_marketable:
                cls._execute_fill(order, limit_price, quantity)
            else:
                # Lock margin for pending limit orders
                if required_margin > Decimal("0.00"):
                    account.margin_utilized += required_margin
                    account.save(update_fields=["margin_utilized", "updated_at"])

        return order

    @classmethod
    @transaction.atomic
    def _execute_fill(
        cls,
        order: PaperOrder,
        fill_price: Decimal,
        fill_quantity: int,
    ) -> PaperTrade:
        """
        Executes order fill, generates tradebook entry, and updates position and wallet balances.
        """
        account = order.account
        listing = order.listing
        product = order.product_type
        side = order.order_side

        taxes = IndianTaxCalculator.calculate(fill_quantity, fill_price, side, product)
        trade_turnover = (Decimal(str(fill_quantity)) * fill_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        net_realized_pnl = None

        # Fetch or initialize position
        pos, created = PaperPosition.objects.get_or_create(
            account=account,
            listing=listing,
            product_type=product,
            defaults={
                "quantity": 0,
                "average_price": fill_price,
                "current_price": fill_price,
                "stop_loss": order.stop_loss_price,
                "target": order.target_price,
            },
        )

        if side == OrderSide.BUY:
            if pos.quantity >= 0:
                # Opening or adding to Long position
                total_cost = (Decimal(str(pos.quantity)) * pos.average_price) + trade_turnover
                new_qty = pos.quantity + fill_quantity
                pos.quantity = new_qty
                pos.average_price = (total_cost / Decimal(str(new_qty))).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
                pos.current_price = fill_price
                if order.stop_loss_price:
                    pos.stop_loss = order.stop_loss_price
                if order.target_price:
                    pos.target = order.target_price

                # Cash debit: Turnover + Statutory charges
                cash_debit = trade_turnover + taxes.total_charges
                account.cash_balance -= cash_debit

            else:
                # Covering short position (MIS)
                closed_qty = min(abs(pos.quantity), fill_quantity)
                # Short profit = closed_qty * (short_avg - buy_price) - charges
                gross_pnl = Decimal(str(closed_qty)) * (pos.average_price - fill_price)
                net_realized_pnl = gross_pnl - taxes.total_charges

                account.realized_pnl += net_realized_pnl
                account.cash_balance += (Decimal(str(closed_qty)) * pos.average_price) + net_realized_pnl

                remaining_qty = pos.quantity + fill_quantity
                pos.quantity = remaining_qty
                if remaining_qty == 0:
                    pos.delete()
                    pos = None

        elif side == OrderSide.SELL:
            if pos.quantity > 0:
                # Closing or reducing Long position
                closed_qty = min(pos.quantity, fill_quantity)
                # Long profit = closed_qty * (sell_price - buy_avg) - charges
                gross_pnl = Decimal(str(closed_qty)) * (fill_price - pos.average_price)
                net_realized_pnl = gross_pnl - taxes.total_charges

                account.realized_pnl += net_realized_pnl
                account.cash_balance += (trade_turnover - taxes.total_charges)

                remaining_qty = pos.quantity - fill_quantity
                pos.quantity = remaining_qty
                if remaining_qty == 0:
                    pos.delete()
                    pos = None

            else:
                # Opening or expanding Short position (MIS)
                new_qty = pos.quantity - fill_quantity
                total_value = (Decimal(str(abs(pos.quantity))) * pos.average_price) + trade_turnover
                pos.quantity = new_qty
                pos.average_price = (total_value / Decimal(str(abs(new_qty)))).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
                pos.current_price = fill_price
                if order.stop_loss_price:
                    pos.stop_loss = order.stop_loss_price
                if order.target_price:
                    pos.target = order.target_price

                account.cash_balance -= taxes.total_charges

        # Update and persist remaining position if not deleted
        if pos:
            pos.current_price = fill_price
            if pos.quantity > 0:
                pos.unrealized_pnl = round(Decimal(str(pos.quantity)) * (fill_price - pos.average_price), 2)
            elif pos.quantity < 0:
                pos.unrealized_pnl = round(Decimal(str(abs(pos.quantity))) * (pos.average_price - fill_price), 2)
            else:
                pos.unrealized_pnl = Decimal("0.00")
            pos.save()

        # Release any locked margin from pending state
        if order.order_type == OrderType.LIMIT:
            ref_price = order.limit_price or fill_price
            locked_margin = cls.calculate_required_margin(order.quantity, ref_price, side, product)
            account.margin_utilized = max(Decimal("0.00"), account.margin_utilized - locked_margin)

        account.save(update_fields=["cash_balance", "margin_utilized", "realized_pnl", "updated_at"])

        # Mark order as FILLED
        order.status = OrderStatus.FILLED
        order.filled_quantity = fill_quantity
        order.save(update_fields=["status", "filled_quantity", "updated_at"])

        # Create immutable tradebook entry
        trade = PaperTrade.objects.create(
            account=account,
            order=order,
            listing=listing,
            trade_side=side,
            product_type=product,
            execution_price=fill_price,
            quantity=fill_quantity,
            turnover=trade_turnover,
            brokerage=taxes.brokerage,
            stt=taxes.stt,
            exchange_charges=taxes.exchange_charges,
            gst=taxes.gst,
            sebi_charges=taxes.sebi_charges,
            stamp_duty=taxes.stamp_duty,
            total_charges=taxes.total_charges,
            net_realized_pnl=net_realized_pnl,
        )

        return trade

    @classmethod
    def cancel_order(cls, order: PaperOrder) -> bool:
        """Cancels a pending order and releases any reserved margin."""
        if order.status != OrderStatus.PENDING:
            return False

        account = order.account
        if order.order_type == OrderType.LIMIT:
            ref_price = order.limit_price or cls.get_latest_price(order.listing)
            locked_margin = cls.calculate_required_margin(order.quantity, ref_price, order.order_side, order.product_type)
            account.margin_utilized = max(Decimal("0.00"), account.margin_utilized - locked_margin)
            account.save(update_fields=["margin_utilized", "updated_at"])

        order.status = OrderStatus.CANCELLED
        order.rejection_reason = "Cancelled by user"
        order.save(update_fields=["status", "rejection_reason", "updated_at"])
        return True

    @classmethod
    def square_off_position(cls, position: PaperPosition) -> Optional[PaperOrder]:
        """Automatically places and executes an offsetting market order to exit a position."""
        if position.quantity == 0:
            return None

        side = OrderSide.SELL if position.quantity > 0 else OrderSide.BUY
        qty = abs(position.quantity)

        return cls.place_order(
            account=position.account,
            listing=position.listing,
            order_side=side,
            product_type=position.product_type,
            order_type=OrderType.MARKET,
            quantity=qty,
            notes="Position squared off",
        )

    @classmethod
    def evaluate_pending_orders_and_brackets(cls, account: Optional[PaperAccount] = None):
        """
        Background worker method to evaluate:
        1. Pending Limit & Stop-Loss orders against live market quotes.
        2. Automatic Stop-Loss and Target bracket triggers on open positions.
        """
        orders_qs = PaperOrder.objects.filter(status=OrderStatus.PENDING)
        if account:
            orders_qs = orders_qs.filter(account=account)

        for order in orders_qs:
            current_price = cls.get_latest_price(order.listing)

            if order.order_type == OrderType.LIMIT:
                if (order.order_side == OrderSide.BUY and current_price <= order.limit_price) or \
                   (order.order_side == OrderSide.SELL and current_price >= order.limit_price):
                    cls._execute_fill(order, order.limit_price, order.quantity)

            elif order.order_type in (OrderType.SL_LIMIT, OrderType.SL_MARKET):
                if order.trigger_price:
                    # SL Buy triggers when price rises to/above trigger
                    # SL Sell triggers when price drops to/below trigger
                    triggered = (
                        (order.order_side == OrderSide.BUY and current_price >= order.trigger_price)
                        or (order.order_side == OrderSide.SELL and current_price <= order.trigger_price)
                    )
                    if triggered:
                        exec_price = order.limit_price if order.order_type == OrderType.SL_LIMIT and order.limit_price else current_price
                        cls._execute_fill(order, exec_price, order.quantity)

        # Evaluate bracket stops and targets on open positions
        positions_qs = PaperPosition.objects.exclude(quantity=0)
        if account:
            positions_qs = positions_qs.filter(account=account)

        for pos in positions_qs:
            current_price = cls.get_latest_price(pos.listing)
            pos.recalculate_pnl(current_price)

            # Target Trigger
            if pos.target:
                if (pos.quantity > 0 and current_price >= pos.target) or (pos.quantity < 0 and current_price <= pos.target):
                    cls.square_off_position(pos)
                    continue

            # Stop-Loss Trigger
            if pos.stop_loss:
                if (pos.quantity > 0 and current_price <= pos.stop_loss) or (pos.quantity < 0 and current_price >= pos.stop_loss):
                    cls.square_off_position(pos)
                    continue
