"""
PaperTrading Views & Controller Endpoints.
Provides the interactive slide-out order drawer, real-time margin estimation,
and HTMX order placement actions.
"""
from decimal import Decimal
import json

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST

from apps.instruments.models import ExchangeListing
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
from apps.trading.models import TradeJournal, TradeJournalStatus
from services.paper_trading.coach import PaperTradingBehavioralCoach
from services.paper_trading.engine import PaperTradingExecutionEngine
from services.paper_trading.tax_calculator import IndianTaxCalculator
from services.recommendations.evaluator import RecommendationEvaluator


@login_required
@require_GET
def order_drawer_view(request, symbol: str):
    """
    Renders the slide-out order placement drawer pre-filled with live quotes,
    wallet balances, and 1-click quantitative recommendation presets.
    """
    listing = get_object_or_404(
        ExchangeListing.objects.select_related("instrument", "exchange"),
        symbol__iexact=symbol,
    )
    account, _ = PaperAccount.objects.get_or_create(user=request.user)

    current_price = PaperTradingExecutionEngine.get_latest_price(listing)

    # Fetch quantitative swing & investor recommendation targets
    try:
        rec_data = RecommendationEvaluator.evaluate(listing=listing)
        new_inv = rec_data.get("new_investor", {})
    except Exception:
        new_inv = {}

    # Check if user already holds an open paper position in this stock
    existing_position = PaperPosition.objects.filter(
        account=account, listing=listing
    ).first()

    default_side = request.GET.get("side", OrderSide.BUY).upper()
    if default_side not in (OrderSide.BUY, OrderSide.SELL):
        default_side = OrderSide.BUY

    context = {
        "listing": listing,
        "account": account,
        "current_price": current_price,
        "rec": new_inv,
        "existing_position": existing_position,
        "default_side": default_side,
    }
    return render(request, "paper_trading/partials/order_drawer.html", context)


@login_required
@require_POST
def place_order_view(request):
    """
    HTMX endpoint for executing a paper trade order.
    Validates form data, passes through the matching engine, and returns confirmation.
    """
    symbol = request.POST.get("symbol", "").strip()
    listing = get_object_or_404(ExchangeListing, symbol__iexact=symbol)
    account, _ = PaperAccount.objects.get_or_create(user=request.user)

    order_side = request.POST.get("order_side", OrderSide.BUY).upper()
    product_type = request.POST.get("product_type", ProductType.CNC).upper()
    order_type = request.POST.get("order_type", OrderType.MARKET).upper()

    try:
        quantity = int(request.POST.get("quantity", 1))
        if quantity <= 0:
            raise ValueError
    except ValueError:
        return render(
            request,
            "paper_trading/partials/order_result.html",
            {"success": False, "error_message": "Quantity must be a positive integer."},
        )

    limit_price = None
    if order_type in (OrderType.LIMIT, OrderType.SL_LIMIT):
        try:
            limit_val = request.POST.get("limit_price", "").strip()
            if limit_val:
                limit_price = Decimal(limit_val)
        except Exception:
            return render(
                request,
                "paper_trading/partials/order_result.html",
                {"success": False, "error_message": "Invalid limit price."},
            )

    target_price = None
    target_val = request.POST.get("target_price", "").strip()
    if target_val:
        try:
            target_price = Decimal(target_val)
        except Exception:
            pass

    stop_loss_price = None
    sl_val = request.POST.get("stop_loss_price", "").strip()
    if sl_val:
        try:
            stop_loss_price = Decimal(sl_val)
        except Exception:
            pass

    notes = request.POST.get("notes", "").strip()

    try:
        order = PaperTradingExecutionEngine.place_order(
            account=account,
            listing=listing,
            order_side=order_side,
            product_type=product_type,
            order_type=order_type,
            quantity=quantity,
            limit_price=limit_price,
            target_price=target_price,
            stop_loss_price=stop_loss_price,
            notes=notes,
        )
    except Exception as e:
        return render(
            request,
            "paper_trading/partials/order_result.html",
            {"success": False, "error_message": str(e)},
        )

    account.refresh_from_db()
    trade = order.trades.first() if order.status == OrderStatus.FILLED else None

    context = {
        "success": order.status != OrderStatus.REJECTED,
        "order": order,
        "trade": trade,
        "account": account,
        "error_message": order.rejection_reason if order.status == OrderStatus.REJECTED else "",
    }
    return render(request, "paper_trading/partials/order_result.html", context)


@login_required
@require_GET
def estimate_charges_api(request):
    """
    JSON API returning live calculated turnover, required margin, and statutory charges.
    """
    try:
        quantity = int(request.GET.get("quantity", 1))
        price = Decimal(request.GET.get("price", "100.00"))
        side = request.GET.get("side", "BUY").upper()
        product_type = request.GET.get("product_type", "CNC").upper()

        taxes = IndianTaxCalculator.calculate(quantity, price, side, product_type)
        required_margin = PaperTradingExecutionEngine.calculate_required_margin(quantity, price, side, product_type)

        return JsonResponse({
            "status": "success",
            "turnover": float(taxes.turnover),
            "required_margin": float(required_margin),
            "brokerage": float(taxes.brokerage),
            "stt": float(taxes.stt),
            "exchange_charges": float(taxes.exchange_charges),
            "gst": float(taxes.gst),
            "sebi_charges": float(taxes.sebi_charges),
            "stamp_duty": float(taxes.stamp_duty),
            "total_charges": float(taxes.total_charges),
        })
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)


@login_required
def terminal_view(request):
    """
    Paper Trading Terminal Dashboard.
    Displays virtual account balances, open positions, active orders, tradebook, and performance analytics.
    """
    account, _ = PaperAccount.objects.get_or_create(user=request.user)

    # Evaluate pending orders and stop-loss / target brackets against latest quotes
    PaperTradingExecutionEngine.evaluate_pending_orders_and_brackets(account=account)
    account.refresh_from_db()

    # Positions with updated MTM
    positions = list(account.positions.select_related("listing__instrument", "listing__exchange").all())
    for pos in positions:
        latest_price = PaperTradingExecutionEngine.get_latest_price(pos.listing)
        pos.recalculate_pnl(latest_price)

    # Pending orders
    pending_orders = account.orders.filter(status=OrderStatus.PENDING).select_related(
        "listing__instrument", "listing__exchange"
    ).order_by("-created_at")

    # Tradebook records
    trades = account.trades.select_related(
        "listing__instrument", "listing__exchange"
    ).order_by("-executed_at")

    # Analytics calculation
    total_trades_count = trades.count()
    closed_trades = [t for t in trades if t.net_realized_pnl is not None]
    closed_count = len(closed_trades)
    winning_trades = [t for t in closed_trades if t.net_realized_pnl > Decimal("0.00")]
    losing_trades = [t for t in closed_trades if t.net_realized_pnl < Decimal("0.00")]

    win_count = len(winning_trades)
    loss_count = len(losing_trades)
    win_rate = round(Decimal(str(win_count / closed_count * 100)), 1) if closed_count > 0 else Decimal("0.0")
    loss_rate = round(Decimal("100.0") - win_rate, 1) if closed_count > 0 else Decimal("0.0")

    total_gross_gain = sum((t.net_realized_pnl for t in winning_trades), Decimal("0.00"))
    total_gross_loss = abs(sum((t.net_realized_pnl for t in losing_trades), Decimal("0.00")))
    profit_factor = (
        round((total_gross_gain / total_gross_loss), 2)
        if total_gross_loss > Decimal("0.00")
        else (round(total_gross_gain, 2) if total_gross_gain > Decimal("0.00") else Decimal("0.0"))
    )

    total_charges_paid = sum((t.total_charges for t in trades), Decimal("0.00"))

    # AI Behavioral Coaching & Discipline Audit (Open-Papertrade inspired)
    coach_report = PaperTradingBehavioralCoach.audit_account(account)

    context = {
        "page_title": "Paper Trading Terminal",
        "active_nav": "paper_trading",
        "account": account,
        "positions": positions,
        "pending_orders": pending_orders,
        "trades": trades,
        "coach": coach_report,
        "analytics": {
            "total_trades": total_trades_count,
            "closed_trades": closed_count,
            "win_count": win_count,
            "loss_count": loss_count,
            "win_rate": win_rate,
            "loss_rate": loss_rate,
            "profit_factor": profit_factor,
            "total_charges_paid": total_charges_paid,
        },
    }

    template_name = "paper_trading/partials/terminal_partial.html" if request.htmx else "paper_trading/terminal.html"
    return render(request, template_name, context)


@login_required
@require_POST
def cancel_order_view(request, order_id):
    """Cancels a pending limit or stop-loss order."""
    account, _ = PaperAccount.objects.get_or_create(user=request.user)
    order = get_object_or_404(PaperOrder, id=order_id, account=account)
    PaperTradingExecutionEngine.cancel_order(order)
    return terminal_view(request)


@login_required
@require_POST
def square_off_position_view(request, position_id):
    """Automatically squares off an open position at market price."""
    account, _ = PaperAccount.objects.get_or_create(user=request.user)
    position = get_object_or_404(PaperPosition, id=position_id, account=account)
    PaperTradingExecutionEngine.square_off_position(position)
    return terminal_view(request)


@login_required
@require_POST
def reset_account_view(request):
    """Resets the virtual paper trading account to initial or custom capital."""
    account, _ = PaperAccount.objects.get_or_create(user=request.user)
    try:
        capital_val = request.POST.get("capital", "1000000.00").strip()
        new_capital = Decimal(capital_val)
        if new_capital <= Decimal("0.00"):
            new_capital = Decimal("1000000.00")
    except Exception:
        new_capital = Decimal("1000000.00")

    account.reset_account(new_capital)
    return terminal_view(request)


@login_required
@require_POST
def export_to_journal_view(request, trade_id):
    """
    1-Click Bridge: Exports a closed paper trade into the immutable TradeJournal.
    Pre-populates execution prices, dates, R:R targets, and checklist verification.
    """
    account, _ = PaperAccount.objects.get_or_create(user=request.user)
    trade = get_object_or_404(PaperTrade, id=trade_id, account=account)

    if trade.net_realized_pnl is None:
        return render(
            request,
            "paper_trading/partials/terminal_partial.html",
            {"error_message": "Only closed trades with realized P&L can be exported to Trade Journal."},
        )

    if trade.journal_entry:
        return terminal_view(request)

    qty_dec = Decimal(str(trade.quantity))
    # Approximate entry price based on realized pnl and execution price
    if trade.trade_side == OrderSide.SELL:
        # Long closed: Net PnL = qty * (exec_price - entry_price) - charges
        entry_price = trade.execution_price - ((trade.net_realized_pnl + trade.total_charges) / qty_dec)
    else:
        # Short closed: Net PnL = qty * (entry_price - exec_price) - charges
        entry_price = trade.execution_price + ((trade.net_realized_pnl + trade.total_charges) / qty_dec)

    entry_price = max(Decimal("1.00"), round(entry_price, 2))
    entry_date = trade.order.created_at.date()
    exit_date = trade.executed_at.date()

    stop_loss = trade.order.stop_loss_price or round(entry_price * Decimal("0.95"), 2)
    target_price = trade.order.target_price or round(entry_price * Decimal("1.10"), 2)

    if trade.order.target_price and trade.execution_price >= trade.order.target_price:
        status = TradeJournalStatus.TARGET_HIT
    elif trade.order.stop_loss_price and trade.execution_price <= trade.order.stop_loss_price:
        status = TradeJournalStatus.STOPPED_OUT
    else:
        status = TradeJournalStatus.CLOSED

    ret_pct = round(((trade.execution_price - entry_price) / entry_price * Decimal("100.0")), 2)

    strategy_name = (
        trade.order.setup.get_strategy_display()
        if trade.order.setup
        else ("Delivery Swing" if trade.product_type == ProductType.CNC else "Intraday Momentum")
    )

    journal = TradeJournal.objects.create(
        user=request.user,
        listing=trade.listing,
        setup=trade.order.setup,
        strategy=strategy_name[:50],
        entry_date=entry_date,
        entry_price=entry_price,
        quantity=trade.quantity,
        stop_loss=stop_loss,
        target_price=target_price,
        exit_date=exit_date,
        exit_price=trade.execution_price,
        realised_pnl=trade.net_realized_pnl,
        realised_pnl_percent=ret_pct,
        status=status,
        entry_reason=trade.order.notes or "Simulated paper trade execution via KuberLens Terminal.",
        exit_reason="Position closed in paper trading terminal.",
        lessons_learned="Automated paper trade retrospective.",
        checklist_completed=True,
    )

    trade.journal_entry = journal
    trade.save(update_fields=["journal_entry"])

    return terminal_view(request)

