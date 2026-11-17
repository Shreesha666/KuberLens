"""
Alert Views.
Allows users to create, manage, toggle, and test price, technical, and portfolio alerts.
"""
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import TemplateView

from apps.alerts.models import AlertRule, AlertType
from apps.core.mixins import HTMXResponseMixin
from apps.instruments.models import ExchangeListing
from services.alerts.evaluator import AlertEvaluator


class AlertListView(LoginRequiredMixin, HTMXResponseMixin, TemplateView):
    """
    Alert Management Dashboard showing user's active, triggered, and paused alert rules.
    """
    template_name = "alerts/list.html"
    partial_template_name = "alerts/partials/list_partial.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        alerts = AlertRule.objects.filter(user=user).select_related(
            "listing__instrument", "listing__exchange"
        ).order_by("-created_at")

        from apps.market.models import MarketQuote

        # All tradeable listings with latest quote price for auto-populate and search
        listings = list(
            ExchangeListing.objects.filter(is_tradeable=True)
            .select_related("instrument", "exchange")
            .order_by("symbol")
        )

        listing_ids = [item.id for item in listings]
        quotes_map = {}
        for q in MarketQuote.objects.filter(listing_id__in=listing_ids).order_by("listing_id", "-retrieved_at"):
            if q.listing_id not in quotes_map:
                quotes_map[q.listing_id] = q

        for item in listings:
            q_obj = quotes_map.get(item.id)
            item.current_price = float(q_obj.price) if q_obj else None
            item.search_label = f"{item.symbol} — {item.instrument.display_name}" + (f" (₹{item.current_price:,.2f})" if item.current_price else "")

        # Enrich alert objects with live pricing, distance/proximity, and stats
        alerts_list = list(alerts)
        active_count = 0
        triggered_count = 0
        paused_count = 0

        for a in alerts_list:
            if a.is_active:
                active_count += 1
            else:
                paused_count += 1
            if a.trigger_count > 0:
                triggered_count += 1

            if a.listing_id and a.listing_id in quotes_map:
                q = quotes_map[a.listing_id]
                a.current_price = float(q.price)
                if a.target_value and a.current_price > 0:
                    target_val = float(a.target_value)
                    a.diff_amount = target_val - a.current_price
                    a.diff_pct = (a.diff_amount / a.current_price) * 100.0
            else:
                a.current_price = None
                a.diff_amount = None
                a.diff_pct = None

        context["alerts"] = alerts_list
        context["active_count"] = active_count
        context["triggered_count"] = triggered_count
        context["paused_count"] = paused_count
        context["total_count"] = len(alerts_list)

        # Categorized Alert Conditions for intuitive selection
        alert_groups = [
            {
                "group": "Price & Breakout Alerts",
                "types": [
                    (AlertType.PRICE_ABOVE, "Price Crosses Above (Target ₹)"),
                    (AlertType.PRICE_BELOW, "Price Crosses Below (Stop ₹)"),
                    (AlertType.PERCENT_MOVE, "Daily % Movement (>= ±%)"),
                    (AlertType.BREAKOUT_52W_HIGH, "52-Week High Breakout"),
                    (AlertType.BREAKDOWN_52W_LOW, "52-Week Low Breakdown"),
                ],
            },
            {
                "group": "Technical Indicators & Signals",
                "types": [
                    (AlertType.RSI_OVERSOLD, "RSI Oversold (<= Threshold, e.g. 30)"),
                    (AlertType.RSI_OVERBOUGHT, "RSI Overbought (>= Threshold, e.g. 70)"),
                    (AlertType.MACD_BULLISH_CROSS, "MACD Bullish Crossover (MACD > Signal)"),
                    (AlertType.MACD_BEARISH_CROSS, "MACD Bearish Crossover (MACD < Signal)"),
                    (AlertType.SMA_CROSSOVER, "Moving Average: 20 SMA Crosses Above 50 SMA"),
                    (AlertType.SMA_BEARISH_CROSS, "Moving Average: 20 SMA Crosses Below 50 SMA"),
                    (AlertType.GOLDEN_CROSS, "Golden Cross: 50 SMA Crosses Above 200 SMA"),
                    (AlertType.DEATH_CROSS, "Death Cross: 50 SMA Crosses Below 200 SMA"),
                    (AlertType.VOLUME_SPIKE, "Volume Surge (> Multiplier × 20-Day Avg)"),
                    (AlertType.BOLLINGER_UPPER_BREAK, "Price Touches Upper Bollinger Band"),
                    (AlertType.BOLLINGER_LOWER_BREAK, "Price Touches Lower Bollinger Band"),
                ],
            },
            {
                "group": "Portfolio & Risk Guardrails",
                "types": [
                    (AlertType.PORTFOLIO_STOP_LOSS, "Holding Stop-Loss Hit (Exit Trigger)"),
                    (AlertType.PORTFOLIO_TARGET, "Holding Profit Target Hit (Take Profit)"),
                    (AlertType.PORTFOLIO_DRAWDOWN, "Portfolio Drawdown Alert"),
                    (AlertType.CONCENTRATION_THRESHOLD, "Holding Concentration Exceeds Threshold (> %)"),
                ],
            },
        ]

        context["active_nav"] = "alerts_notifications"
        context["alerts"] = alerts
        context["alert_types"] = AlertType.choices
        context["alert_groups"] = alert_groups
        context["listings"] = listings
        return context


class AlertCreateView(LoginRequiredMixin, View):
    """
    Creates a new user alert rule.
    """
    def post(self, request, *args, **kwargs):
        user = request.user
        symbol = request.POST.get("symbol", "").strip().upper()
        alert_type = request.POST.get("alert_type", "").strip()
        target_str = request.POST.get("target_value", "0").strip()
        notes = request.POST.get("notes", "").strip()
        market_hours_only = request.POST.get("is_market_hours_only") == "on"

        try:
            target_value = Decimal(target_str)
        except Exception:
            target_value = Decimal("0")

        listing = None
        if symbol:
            listing = ExchangeListing.objects.filter(symbol=symbol, is_tradeable=True).first()

        if alert_type in AlertType.values:
            AlertRule.objects.create(
                user=user,
                listing=listing,
                alert_type=alert_type,
                target_value=target_value,
                notes=notes,
                is_market_hours_only=market_hours_only,
            )
            messages.success(request, f"Alert created for {symbol or 'Portfolio'}.")

        if request.htmx:
            return redirect("alerts:list")
        return redirect("alerts:list")


class AlertToggleActiveView(LoginRequiredMixin, View):
    """
    Toggles alert active/paused status.
    """
    def post(self, request, pk: int, *args, **kwargs):
        alert = get_object_or_404(AlertRule, pk=pk, user=request.user)
        alert.is_active = not alert.is_active
        alert.save(update_fields=["is_active"])
        status_label = "activated" if alert.is_active else "paused"
        messages.info(request, f"Alert {alert.id} {status_label}.")
        return redirect("alerts:list")


class AlertDeleteView(LoginRequiredMixin, View):
    """
    Deletes an alert rule.
    """
    def post(self, request, pk: int, *args, **kwargs):
        alert = get_object_or_404(AlertRule, pk=pk, user=request.user)
        alert.delete()
        messages.success(request, "Alert deleted successfully.")
        return redirect("alerts:list")


class AlertUpdateView(LoginRequiredMixin, View):
    """
    Updates an existing user alert rule.
    """
    def post(self, request, pk, *args, **kwargs):
        alert = get_object_or_404(AlertRule, pk=pk, user=request.user)
        alert_type = request.POST.get("alert_type", alert.alert_type).strip()
        target_str = request.POST.get("target_value", str(alert.target_value)).strip()
        notes = request.POST.get("notes", alert.notes).strip()
        market_hours_only = request.POST.get("is_market_hours_only") == "on"

        try:
            target_value = Decimal(target_str)
        except Exception:
            target_value = alert.target_value

        if alert_type in AlertType.values:
            alert.alert_type = alert_type
        alert.target_value = target_value
        alert.notes = notes
        alert.is_market_hours_only = market_hours_only
        alert.save(update_fields=["alert_type", "target_value", "notes", "is_market_hours_only"])

        messages.success(request, f"Updated alert rule for {alert.listing.symbol if alert.listing else 'Portfolio'}.")
        return redirect("alerts:list")


class AlertRunEvaluationView(LoginRequiredMixin, View):
    """
    Manually triggers evaluation of all user's active alerts and dispatches notifications.
    """
    def post(self, request, *args, **kwargs):
        triggered_count = AlertEvaluator.evaluate_all_active_alerts(
            user=request.user,
            check_market_hours=False,
        )
        if triggered_count > 0:
            messages.success(request, f"Alert check complete: {triggered_count} alert(s) triggered!")
        else:
            messages.info(request, "Alert check complete: All conditions currently normal (0 triggers).")
        return redirect("alerts:list")


class AlertStockTargetsView(LoginRequiredMixin, View):
    """
    JSON endpoint providing live ATR Stop Loss, Target 1, Target 2, and momentum
    timelines from the New Prospective Investor engine for 1-click alert presets.
    """
    def get(self, request, symbol: str, *args, **kwargs):
        sym = symbol.strip().upper()
        listing = ExchangeListing.objects.filter(symbol=sym, is_tradeable=True).first()
        if not listing:
            return JsonResponse({"error": "Listing not found"}, status=404)

        from apps.market.models import MarketQuote
        from services.recommendations.evaluator import RecommendationEvaluator

        quote = MarketQuote.objects.filter(listing=listing).first()
        ltp = float(quote.price) if quote else None

        rec = RecommendationEvaluator.evaluate(listing, quote=quote)
        new_inv = rec.get("new_investor", {})

        return JsonResponse({
            "symbol": listing.symbol,
            "name": listing.instrument.display_name,
            "ltp": ltp,
            "stop_loss": new_inv.get("stop_loss_value"),
            "stop_loss_label": new_inv.get("stop_loss"),
            "stop_loss_rationale": new_inv.get("stop_loss_rationale"),
            "target_1": new_inv.get("target_1_value"),
            "target_1_pct": new_inv.get("target_1_pct"),
            "target_1_eta": new_inv.get("target_1_eta"),
            "target_2": new_inv.get("target_2_value"),
            "target_2_pct": new_inv.get("target_2_pct"),
            "target_2_eta": new_inv.get("target_2_eta"),
        })
