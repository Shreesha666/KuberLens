"""
Holdings & Transaction Views.
Provides positions summary, detailed FIFO lot inspection, transaction history,
and dual-perspective recommendations.
"""
import logging
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import DetailView, ListView, TemplateView

from apps.core.mixins import HTMXResponseMixin
from apps.fundamental_analysis.models import FundamentalSnapshot
from apps.holdings.models import (
    Holding,
    HoldingTransaction,
    LotAllocation,
    TransactionType,
)
from apps.instruments.models import ExchangeListing
from apps.market.models import MarketQuote
from apps.portfolio.models import Portfolio
from apps.technical_analysis.models import TechnicalIndicatorSnapshot
from services.market_data.service import MarketDataService
from services.portfolio.accounting import FIFOAccountingEngine
from services.recommendations.evaluator import RecommendationEvaluator

logger = logging.getLogger(__name__)


class HoldingListView(LoginRequiredMixin, HTMXResponseMixin, ListView):
    """
    Overview list of user's active holdings with profit & loss metrics.
    """
    model = Holding
    template_name = "holdings/holding_list.html"
    partial_template_name = "holdings/partials/holding_list_partial.html"
    context_object_name = "holdings"
    active_nav = "my_holdings"

    def get_portfolio(self):
        portfolio, _ = Portfolio.objects.get_or_create(
            user=self.request.user,
            is_default=True,
            defaults={"name": "Main Portfolio"},
        )
        return portfolio

    def get_queryset(self):
        portfolio = self.get_portfolio()
        # Reconcile all holdings
        holdings = list(
            Holding.objects.filter(portfolio=portfolio, total_quantity__gt=0)
            .select_related("listing__instrument", "listing__exchange")
            .order_by("listing__symbol")
        )
        for h in holdings:
            FIFOAccountingEngine.reconcile_holding(portfolio, h.listing)

        return (
            Holding.objects.filter(portfolio=portfolio, total_quantity__gt=0)
            .select_related("listing__instrument", "listing__exchange")
            .order_by("listing__symbol")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        portfolio = self.get_portfolio()
        context["portfolio"] = portfolio
        context["page_title"] = "My Holdings & Positions"

        holdings = list(context["holdings"])
        total_val = sum((h.current_value for h in holdings), Decimal("0.00"))
        total_inv = sum((h.invested_amount for h in holdings), Decimal("0.00"))
        total_unreal = total_val - total_inv
        total_realised = sum((h.realised_pnl for h in holdings), Decimal("0.00"))

        for h in holdings:
            h.portfolio_weight = (
                round((h.current_value / total_val * Decimal("100.0")), 1)
                if total_val > Decimal("0.00")
                else Decimal("0.0")
            )

        context["total_invested"] = total_inv
        context["total_current_value"] = total_val
        context["total_unrealised_pnl"] = total_unreal
        context["total_realised_pnl"] = total_realised
        return context


class HoldingDetailView(LoginRequiredMixin, HTMXResponseMixin, DetailView):
    """
    Detailed holding breakdown for a specific stock:
    Open FIFO lots, complete transaction ledger, realized P&L slices, and recommendations.
    """
    model = Holding
    template_name = "holdings/holding_detail.html"
    partial_template_name = "holdings/partials/holding_detail_partial.html"
    context_object_name = "holding"
    active_nav = "my_holdings"

    def get_portfolio(self):
        portfolio, _ = Portfolio.objects.get_or_create(
            user=self.request.user,
            is_default=True,
            defaults={"name": "Main Portfolio"},
        )
        return portfolio

    def get_object(self, queryset=None):
        portfolio = self.get_portfolio()
        symbol = self.kwargs.get("symbol", "").upper()
        listing = get_object_or_404(ExchangeListing, symbol=symbol, is_tradeable=True)

        holding = FIFOAccountingEngine.reconcile_holding(portfolio, listing)
        return holding

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        holding = self.object
        portfolio = holding.portfolio
        listing = holding.listing

        context["page_title"] = f"Holding: {listing.symbol} - {listing.instrument.display_name}"

        # 1. Open FIFO Lots
        context["open_lots"] = FIFOAccountingEngine.get_open_lots(portfolio, listing)

        # 2. Transaction Ledger History
        context["transactions"] = (
            HoldingTransaction.objects.filter(portfolio=portfolio, listing=listing)
            .order_by("-executed_at", "-created_at")
        )

        # 3. Lot Allocations (Closed Sells)
        context["lot_allocations"] = (
            LotAllocation.objects.filter(sell_transaction__portfolio=portfolio, sell_transaction__listing=listing)
            .select_related("sell_transaction", "buy_transaction")
            .order_by("-allocated_at")
        )

        # 4. Total Portfolio Value for Allocation Sizing
        total_portfolio_val = (
            Holding.objects.filter(portfolio=portfolio, total_quantity__gt=0)
            .aggregate(Sum("current_value"))
            .get("current_value__sum")
            or Decimal("0.00")
        )

        # 5. Dual Recommendations (Existing Holder vs New Investor)
        technical = TechnicalIndicatorSnapshot.objects.filter(listing=listing).order_by("-timestamp").first()
        fundamental = FundamentalSnapshot.objects.filter(instrument=listing.instrument).order_by("-calculated_at").first()

        recommendations = RecommendationEvaluator.evaluate(
            listing=listing,
            holding=holding,
            technical=technical,
            fundamental=fundamental,
            portfolio_total_value=total_portfolio_val,
        )
        context["recommendations"] = recommendations
        context["technical"] = technical
        context["fundamental"] = fundamental
        return context


class HoldingTransactionCreateView(LoginRequiredMixin, HTMXResponseMixin, TemplateView):
    """
    Logs manual Buy, Sell, Dividend, Bonus, or Split transactions.
    Supports single stock additions, full FIFO reconciliation, and automatic position updates.
    """
    template_name = "holdings/add_transaction.html"
    partial_template_name = "holdings/partials/add_transaction_partial.html"
    active_nav = "my_holdings"

    def get_portfolio(self):
        portfolio, _ = Portfolio.objects.get_or_create(
            user=self.request.user,
            is_default=True,
            defaults={"name": "Main Portfolio", "currency": "INR"},
        )
        return portfolio

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        portfolio = self.get_portfolio()
        context["portfolio"] = portfolio
        context["page_title"] = "Add Investment / Record Transaction"

        listings = list(
            ExchangeListing.objects.filter(is_tradeable=True)
            .select_related("instrument", "exchange")
            .order_by("symbol")
        )

        listing_ids = [item.id for item in listings]
        quotes_by_listing = {}
        for q in MarketQuote.objects.filter(listing_id__in=listing_ids).order_by("listing_id", "-retrieved_at"):
            if q.listing_id not in quotes_by_listing:
                quotes_by_listing[q.listing_id] = q

        for item in listings:
            q_obj = quotes_by_listing.get(item.id)
            item.latest_quote_price = float(q_obj.price) if q_obj else None

        context["listings"] = listings

        requested_symbol = (
            self.request.POST.get("symbol")
            or self.request.GET.get("symbol")
            or ""
        ).strip().upper()

        selected_listing = None
        prefill_price = None
        current_holding = None

        if requested_symbol:
            for item in listings:
                if item.symbol == requested_symbol:
                    selected_listing = item
                    break

            if selected_listing:
                current_holding = Holding.objects.filter(portfolio=portfolio, listing=selected_listing).first()
                if selected_listing.latest_quote_price:
                    prefill_price = selected_listing.latest_quote_price
                else:
                    try:
                        quote_res = MarketDataService.get_quote(selected_listing)
                        prefill_price = float(quote_res.price) if quote_res else None
                    except Exception:
                        prefill_price = None

        context["selected_symbol"] = requested_symbol
        context["selected_listing"] = selected_listing
        context["current_holding"] = current_holding
        context["prefill_price"] = prefill_price
        context["transaction_types"] = [
            (TransactionType.BUY, "BUY (Add Position / Lot)"),
            (TransactionType.SELL, "SELL (FIFO Relinquish)"),
            (TransactionType.DIVIDEND, "DIVIDEND (Cash Income)"),
            (TransactionType.BONUS, "BONUS (Proportional 0-Cost)"),
            (TransactionType.SPLIT, "STOCK SPLIT (Ratio)"),
            (TransactionType.COST_ADJUSTMENT, "COST ADJUSTMENT"),
        ]
        context["default_executed_at"] = timezone.now().strftime("%Y-%m-%dT%H:%M")
        return context

    def post(self, request, *args, **kwargs):
        portfolio = self.get_portfolio()
        symbol = request.POST.get("symbol", "").strip().upper()
        if not symbol:
            messages.error(request, "Please select an instrument / stock symbol.")
            return self.get(request, *args, **kwargs)

        listing = ExchangeListing.objects.filter(symbol=symbol, is_tradeable=True).first()
        if not listing:
            messages.error(request, f"Listing with symbol '{symbol}' was not found or is not tradeable.")
            return self.get(request, *args, **kwargs)

        tx_type = request.POST.get("transaction_type", TransactionType.BUY)
        try:
            qty = int(request.POST.get("quantity", 0) or 0)
        except (ValueError, TypeError):
            qty = 0

        if tx_type in (TransactionType.BUY, TransactionType.SELL) and qty <= 0:
            messages.error(request, "Quantity must be a positive integer greater than 0.")
            return self.get(request, *args, **kwargs)

        try:
            price_val = Decimal(str(request.POST.get("price", "0.00") or "0.00"))
        except Exception:
            price_val = Decimal("0.00")

        if tx_type == TransactionType.BUY and price_val <= Decimal("0.00"):
            messages.error(request, "Executed price must be greater than zero for Buy transactions.")
            return self.get(request, *args, **kwargs)

        try:
            brokerage_val = Decimal(str(request.POST.get("brokerage", "0.00") or "0.00"))
        except Exception:
            brokerage_val = Decimal("0.00")

        try:
            taxes_val = Decimal(str(request.POST.get("statutory_taxes", "0.00") or "0.00"))
        except Exception:
            taxes_val = Decimal("0.00")

        date_str = request.POST.get("executed_at")
        notes = request.POST.get("notes", "").strip()

        if date_str:
            try:
                from datetime import datetime
                executed_at = datetime.fromisoformat(date_str)
                if timezone.is_naive(executed_at):
                    executed_at = timezone.make_aware(executed_at, timezone.get_current_timezone())
            except Exception:
                executed_at = timezone.now()
        else:
            executed_at = timezone.now()

        # If it's a SELL, check if user has enough shares
        if tx_type == TransactionType.SELL:
            existing_holding = Holding.objects.filter(portfolio=portfolio, listing=listing).first()
            if not existing_holding or existing_holding.total_quantity < qty:
                owned = existing_holding.total_quantity if existing_holding else 0
                messages.error(
                    request,
                    f"Cannot sell {qty} shares of {listing.symbol}. You currently own {owned} shares.",
                )
                return self.get(request, *args, **kwargs)

        # Create immutable transaction
        tx = HoldingTransaction.objects.create(
            portfolio=portfolio,
            listing=listing,
            transaction_type=tx_type,
            quantity=qty,
            price=price_val,
            brokerage=brokerage_val,
            statutory_taxes=taxes_val,
            executed_at=executed_at,
            notes=notes,
        )

        # Reconcile holding immediately using FIFO
        FIFOAccountingEngine.reconcile_holding(
            portfolio,
            listing,
            current_price=price_val if tx_type == TransactionType.BUY else None,
        )
        messages.success(
            request,
            f"Successfully recorded {tx.get_transaction_type_display()} transaction for {listing.symbol} ({qty} shares @ ₹{price_val:,.2f}).",
        )

        redirect_url = reverse("holdings:detail", kwargs={"symbol": listing.symbol})
        if request.htmx:
            resp = HttpResponseRedirect(redirect_url)
            resp["HX-Redirect"] = redirect_url
            return resp

        return redirect(redirect_url)
