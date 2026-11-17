from decimal import Decimal

from django.views.generic import TemplateView

from apps.core.mixins import HTMXResponseMixin
from apps.holdings.models import Holding
from apps.market.models import MarketQuote
from apps.portfolio.models import Portfolio
from apps.trading.models import TradeSetup
from apps.watchlists.models import Watchlist


class DashboardView(HTMXResponseMixin, TemplateView):
    """
    Main platform dashboard landing page.
    Renders partial template on HTMX swap and full application shell on direct URL access.
    Aggregates real-time portfolio metrics, active swing setups, and market indices.
    """
    template_name = "dashboard/dashboard.html"
    partial_template_name = "dashboard/partials/dashboard_partial.html"
    active_nav = "dashboard"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Executive Dashboard"

        # Determine target user / portfolio
        user = self.request.user if self.request.user.is_authenticated else None
        portfolio = None
        if user:
            portfolio = (
                Portfolio.objects.filter(user=user, is_default=True).first()
                or Portfolio.objects.filter(user=user).first()
            )
        if not portfolio:
            portfolio = Portfolio.objects.first()

        from services.calendar.exchange_calendar import ExchangeCalendar
        from services.market_data.service import MarketDataService

        is_market_open = ExchangeCalendar.is_market_open()
        if portfolio and is_market_open:
            try:
                MarketDataService.sync_portfolio_quotes(portfolio=portfolio, max_age_seconds=15)
            except Exception:
                pass

        holdings = []
        if portfolio:
            holdings = list(
                Holding.objects.filter(portfolio=portfolio, total_quantity__gt=0)
                .select_related("listing__instrument")
            )

        total_invested = sum((h.invested_amount for h in holdings), Decimal("0.00"))
        current_val = sum((h.current_value for h in holdings), Decimal("0.00"))
        unrealised = current_val - total_invested
        total_return_pct = (
            round((unrealised / total_invested * 100), 2)
            if total_invested > 0
            else Decimal("0.00")
        )

        # Day P&L calculation from latest quotes
        day_pnl = Decimal("0.00")
        for h in holdings:
            quote = MarketQuote.objects.filter(listing=h.listing).order_by("-retrieved_at").first()
            if quote and getattr(quote, "change", None) is not None:
                day_pnl += Decimal(str(quote.change)) * h.total_quantity
        day_pnl_pct = (
            round((day_pnl / current_val * 100), 2)
            if current_val > 0
            else Decimal("0.00")
        )

        from apps.ipo.models import IPOMaster, IPOStatus

        active_setups_count = TradeSetup.objects.filter(status="ACTIVE").count()
        recent_setups = list(
            TradeSetup.objects.filter(status="ACTIVE")
            .select_related("listing__instrument")
            .order_by("-risk_reward_ratio", "-created_at")[:5]
        )
        active_ipos = list(
            IPOMaster.objects.filter(status__in=[IPOStatus.LIVE, IPOStatus.UPCOMING])
            .order_by("open_date")[:4]
        )

        watchlist_count = (
            Watchlist.objects.filter(user=user).count()
            if user
            else Watchlist.objects.count()
        )

        context["summary_stats"] = {
            "portfolio_value": current_val,
            "invested_capital": total_invested,
            "unrealised_pnl": unrealised,
            "total_return_pct": total_return_pct,
            "day_pnl": day_pnl,
            "day_pnl_pct": day_pnl_pct,
            "active_setups_count": active_setups_count,
            "active_ipos_count": IPOMaster.objects.filter(status=IPOStatus.LIVE).count(),
            "watchlist_count": watchlist_count,
            "holdings_count": len(holdings),
        }
        context["recent_setups"] = recent_setups
        context["active_ipos"] = active_ipos
        context["is_market_open"] = is_market_open
        context["auto_refresh_interval"] = 15 if is_market_open else 0
        context["top_holdings"] = sorted(
            holdings, key=lambda x: x.current_value, reverse=True
        )[:5]
        return context


class MarketOverviewView(HTMXResponseMixin, TemplateView):
    template_name = "dashboard/market_overview.html"
    partial_template_name = "dashboard/partials/market_overview_partial.html"
    active_nav = "market_overview"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Market Overview"
        return context


class ModulePlaceholderView(HTMXResponseMixin, TemplateView):
    """
    Generic placeholder view for Phase 2+ modules, preserving architecture
    integrity and dynamic navigation without premature feature implementation.
    """
    template_name = "dashboard/module_placeholder.html"
    partial_template_name = "dashboard/partials/module_placeholder_partial.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        module_name = self.kwargs.get("module_name", "Module")
        context["module_name"] = module_name.replace("_", " ").title()
        context["page_title"] = context["module_name"]
        context["active_nav"] = module_name
        return context
