import logging
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import TemplateView

from apps.core.mixins import HTMXResponseMixin
from apps.instruments.models import ExchangeListing
from apps.trading.models import (
    SwingStrategyType,
    TradeJournal,
    TradeJournalStatus,
    TradeSetup,
)
from services.risk.calculator import RiskCalculator
from services.trading.scanner import SwingScanner

logger = logging.getLogger(__name__)


class SwingScannerView(LoginRequiredMixin, HTMXResponseMixin, TemplateView):
    """
    Interactive Swing Trading Scanner Hub.
    Surfaces quantitative 1-8 week trade setups with dynamic position sizing,
    risk/reward filters, and one-click execution logging to the Trade Journal.
    """
    template_name = "trading/scanner.html"
    partial_template_name = "trading/partials/scanner_partial.html"
    active_nav = "swing_trading"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Swing Trading Hub & Quantitative Scanner"

        # Read query parameters
        strat_filter = self.request.GET.get("strategy", "ALL")
        cap_filter = self.request.GET.get("market_cap", "ALL")
        min_rr_str = self.request.GET.get("min_rr", "1.5")

        try:
            min_rr = Decimal(min_rr_str)
        except Exception:
            min_rr = Decimal("1.5")

        # Position Sizing Parameters
        cap_str = self.request.GET.get("capital", "500000")
        risk_pct_str = self.request.GET.get("risk_pct", "1.5")

        try:
            trading_capital = Decimal(cap_str)
        except Exception:
            trading_capital = Decimal("500000.00")

        try:
            risk_pct = Decimal(risk_pct_str)
        except Exception:
            risk_pct = Decimal("1.50")

        # Execute scan
        raw_setups = SwingScanner.scan_universe(
            strategy_filter=strat_filter,
            market_cap_filter=cap_filter,
            min_rr=min_rr,
            save_setups=True,
        )

        # Attach computed position sizing for the user's specific capital settings
        annotated_setups = []
        for s in raw_setups:
            try:
                sizing = RiskCalculator.calculate_position_size(
                    trading_capital=trading_capital,
                    risk_percentage=risk_pct,
                    entry_price=s["entry_max"],
                    stop_loss=s["stop_loss"],
                )
            except Exception:
                sizing = None

            s["sizing"] = sizing
            annotated_setups.append(s)

        # Paginate results (12 setups per page)
        page_number = self.request.GET.get("page", 1)
        paginator = Paginator(annotated_setups, 12)
        page_obj = paginator.get_page(page_number)

        context["page_obj"] = page_obj
        context["setups"] = page_obj.object_list
        context["setups_count"] = len(annotated_setups)
        context["page_range"] = paginator.get_elided_page_range(
            number=page_obj.number, on_each_side=2, on_ends=1
        )
        context["strategy_choices"] = SwingStrategyType.choices
        context["selected_strategy"] = strat_filter
        context["selected_cap"] = cap_filter
        context["selected_min_rr"] = str(min_rr)
        context["trading_capital"] = str(trading_capital)
        context["risk_pct"] = str(risk_pct)

        return context


class PositionSizerCalculateView(LoginRequiredMixin, View):
    """
    HTMX endpoint for dynamic real-time position sizing calculations.
    """
    def get(self, request, *args, **kwargs):
        cap_str = request.GET.get("capital", "500000")
        risk_str = request.GET.get("risk_pct", "1.5")
        entry_str = request.GET.get("entry", "0")
        sl_str = request.GET.get("stop_loss", "0")
        target_str = request.GET.get("target", "0")

        try:
            capital = Decimal(cap_str)
            risk_pct = Decimal(risk_str)
            entry = Decimal(entry_str)
            sl = Decimal(sl_str)
            target = Decimal(target_str) if target_str and target_str != "0" else None
        except Exception as e:
            return HttpResponseBadRequest(f"Invalid numeric input: {e}")

        try:
            sizing = RiskCalculator.calculate_position_size(
                trading_capital=capital,
                risk_percentage=risk_pct,
                entry_price=entry,
                stop_loss=sl,
            )
            rr = None
            if target and target > entry:
                rr = RiskCalculator.calculate_risk_reward(entry, sl, target)

            context = {
                "sizing": sizing,
                "risk_reward": rr,
                "target": target,
            }
            return render(request, "trading/partials/position_sizer_result.html", context)
        except ValueError as e:
            return HttpResponse(
                f'<div class="alert alert-warning py-2 mb-0 small"><i class="bi bi-exclamation-triangle me-1"></i> {e}</div>'
            )


class TradeJournalListView(LoginRequiredMixin, HTMXResponseMixin, TemplateView):
    """
    Comprehensive Swing Trade Execution Journal.
    Displays open positions, closed performance metrics, pre-trade execution checklist,
    and post-trade lessons learned.
    """
    template_name = "trading/journal.html"
    partial_template_name = "trading/partials/journal_partial.html"
    active_nav = "trade_journal"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Swing Trading Journal & Performance Tracker"

        user = self.request.user
        open_trades = TradeJournal.objects.filter(
            user=user, status=TradeJournalStatus.OPEN
        ).select_related("listing__instrument")

        closed_trades = TradeJournal.objects.filter(
            user=user
        ).exclude(status=TradeJournalStatus.OPEN).select_related("listing__instrument")

        # Performance KPIs
        total_closed = closed_trades.count()
        winning_trades = closed_trades.filter(realised_pnl__gt=Decimal("0.0")).count()
        losing_trades = closed_trades.filter(realised_pnl__lt=Decimal("0.0")).count()

        win_rate = round((winning_trades / total_closed * 100.0), 1) if total_closed > 0 else Decimal("0.0")

        total_realised_pnl = sum((t.realised_pnl or Decimal("0.0")) for t in closed_trades)
        total_open_risk = sum(t.total_risk for t in open_trades)
        total_open_capital = sum(t.total_invested for t in open_trades)

        # Pre-fill data if user came from a specific TradeSetup or Stock
        setup_id = self.request.GET.get("setup_id")
        prefill_setup = None
        if setup_id:
            prefill_setup = TradeSetup.objects.filter(id=setup_id).select_related("listing").first()

        context["open_trades"] = open_trades
        context["closed_trades"] = closed_trades
        context["total_closed"] = total_closed
        context["winning_trades"] = winning_trades
        context["losing_trades"] = losing_trades
        context["win_rate"] = win_rate
        context["total_realised_pnl"] = total_realised_pnl
        context["total_open_risk"] = total_open_risk
        context["total_open_capital"] = total_open_capital
        context["prefill_setup"] = prefill_setup
        context["strategy_choices"] = SwingStrategyType.choices

        return context


class TradeJournalCreateView(LoginRequiredMixin, View):
    """
    Logs a new swing trade into the Trade Journal.
    Enforces the Pre-Trade Execution Checklist before recording.
    """
    def post(self, request, *args, **kwargs):
        symbol = request.POST.get("symbol", "").strip().upper()
        strategy = request.POST.get("strategy", "").strip()
        entry_date = request.POST.get("entry_date")
        entry_price_str = request.POST.get("entry_price")
        quantity_str = request.POST.get("quantity")
        stop_loss_str = request.POST.get("stop_loss")
        target_price_str = request.POST.get("target_price")
        entry_reason = request.POST.get("entry_reason", "").strip()
        setup_id = request.POST.get("setup_id")

        # Checklist inputs
        chk_rules = request.POST.get("chk_rules") == "on"
        chk_risk = request.POST.get("chk_risk") == "on"
        chk_earnings = request.POST.get("chk_earnings") == "on"

        if not (chk_rules and chk_risk and chk_earnings):
            messages.error(
                request,
                "Pre-Trade Execution Checklist incomplete! You must verify strategy rules, risk sizing, and event calendar before taking this trade."
            )
            return redirect("trading:journal")

        listing = ExchangeListing.objects.filter(symbol=symbol, is_primary=True).first()
        if not listing:
            messages.error(request, f"Could not find primary exchange listing for symbol '{symbol}'.")
            return redirect("trading:journal")

        try:
            entry_p = Decimal(entry_price_str)
            qty = int(quantity_str)
            sl = Decimal(stop_loss_str)
            target = Decimal(target_price_str)
        except Exception as e:
            messages.error(request, f"Invalid numeric parameters: {e}")
            return redirect("trading:journal")

        if sl >= entry_p:
            messages.error(request, f"Invalid stop loss: ₹{sl:.2f} must be lower than entry price ₹{entry_p:.2f}.")
            return redirect("trading:journal")

        if target <= entry_p:
            messages.error(request, f"Invalid target price: ₹{target:.2f} must be higher than entry price ₹{entry_p:.2f}.")
            return redirect("trading:journal")

        setup_obj = None
        if setup_id:
            setup_obj = TradeSetup.objects.filter(id=setup_id).first()

        TradeJournal.objects.create(
            user=request.user,
            listing=listing,
            setup=setup_obj,
            strategy=strategy or "Discretionary Swing",
            entry_date=entry_date,
            entry_price=entry_p,
            quantity=qty,
            stop_loss=sl,
            target_price=target,
            entry_reason=entry_reason,
            checklist_completed=True,
            status=TradeJournalStatus.OPEN,
        )

        messages.success(request, f"Successfully logged {qty} shares of {symbol} in Trade Journal.")
        return redirect("trading:journal")


class TradeJournalCloseView(LoginRequiredMixin, View):
    """
    Closes an open trade and calculates net realised P&L and lessons learned.
    """
    def post(self, request, pk, *args, **kwargs):
        trade = get_object_or_404(TradeJournal, pk=pk, user=request.user)
        exit_date = request.POST.get("exit_date")
        exit_price_str = request.POST.get("exit_price")
        exit_reason = request.POST.get("exit_reason", "").strip()
        lessons_learned = request.POST.get("lessons_learned", "").strip()

        try:
            exit_price = Decimal(exit_price_str)
        except Exception as e:
            messages.error(request, f"Invalid exit price: {e}")
            return redirect("trading:journal")

        trade.close_trade(
            exit_date=exit_date,
            exit_price=exit_price,
            exit_reason=exit_reason,
            lessons_learned=lessons_learned,
        )

        pnl_sign = "+" if trade.realised_pnl >= 0 else ""
        messages.success(
            request,
            f"Closed trade for {trade.listing.symbol}. Realised P&L: {pnl_sign}₹{trade.realised_pnl:,.2f} ({trade.realised_pnl_percent:.2f}%)."
        )
        return redirect("trading:journal")


class TradeJournalDeleteView(LoginRequiredMixin, View):
    """
    Deletes a journal entry.
    """
    def post(self, request, pk, *args, **kwargs):
        trade = get_object_or_404(TradeJournal, pk=pk, user=request.user)
        sym = trade.listing.symbol
        trade.delete()
        messages.success(request, f"Deleted journal entry for {sym}.")
        return redirect("trading:journal")
