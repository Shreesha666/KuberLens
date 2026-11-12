"""
Alert Views.
Allows users to create, manage, toggle, and test price, technical, and portfolio alerts.
"""
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
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

        # Top listings for quick dropdown
        popular_listings = ExchangeListing.objects.filter(
            is_tradeable=True, is_primary=True
        ).select_related("instrument")[:40]

        context["active_nav"] = "alerts_notifications"
        context["alerts"] = alerts
        context["alert_types"] = AlertType.choices
        context["popular_listings"] = popular_listings
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
