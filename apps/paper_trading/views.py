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
    ProductType,
)
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
