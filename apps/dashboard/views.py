from django.views.generic import TemplateView

from apps.core.mixins import HTMXResponseMixin


class DashboardView(HTMXResponseMixin, TemplateView):
    """
    Main platform dashboard landing page.
    Renders partial template on HTMX swap and full application shell on direct URL access.
    """
    template_name = "dashboard/dashboard.html"
    partial_template_name = "dashboard/partials/dashboard_partial.html"
    active_nav = "dashboard"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Executive Dashboard"
        context["summary_stats"] = {
            "portfolio_value": "₹0.00",
            "unrealised_pnl": "₹0.00",
            "day_pnl": "₹0.00",
            "active_setups_count": 0,
            "watchlist_count": 0,
        }
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
