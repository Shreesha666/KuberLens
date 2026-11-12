"""
AI Stock Analysis Views.
Provides the interactive AI Research Hub and embeddable stock research partials.
"""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, render
from django.views import View
from django.views.generic import TemplateView

from apps.ai_analysis.models import AIRole
from apps.core.mixins import HTMXResponseMixin
from apps.instruments.models import ExchangeListing
from services.ai.researcher import AIResearchService

POPULAR_RESEARCH_SYMBOLS = [
    "RELIANCE",
    "TCS",
    "HDFCBANK",
    "INFY",
    "TATAMOTORS",
    "ICICIBANK",
    "LT",
    "ITC",
]


class AIResearchHubView(LoginRequiredMixin, HTMXResponseMixin, TemplateView):
    """
    Interactive AI Research Hub where users can consult Investor AI,
    Swing Trader AI, and Portfolio Risk Manager for any listed stock.
    """
    template_name = "ai_analysis/hub.html"
    partial_template_name = "ai_analysis/partials/hub_partial.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        symbol = self.request.GET.get("symbol", "RELIANCE").strip().upper()
        role = self.request.GET.get("role", AIRole.INVESTOR).strip().upper()
        force_refresh = self.request.GET.get("force", "false").lower() == "true"

        # Validate role
        if role not in AIRole.values:
            role = AIRole.INVESTOR

        # Lookup listing
        listing = ExchangeListing.objects.filter(symbol=symbol, is_tradeable=True).select_related(
            "instrument", "exchange"
        ).first()

        if not listing:
            # Fallback to any active listing
            listing = ExchangeListing.objects.filter(is_tradeable=True).select_related(
                "instrument", "exchange"
            ).first()
            if listing:
                symbol = listing.symbol

        analysis = None
        if listing:
            analysis = AIResearchService.analyze_stock(
                listing=listing,
                role=role,
                user=self.request.user,
                force_refresh=force_refresh,
            )

        context["active_nav"] = "ai_stock_research"
        context["listing"] = listing
        context["symbol"] = symbol
        context["selected_role"] = role
        context["roles"] = AIRole.choices
        context["analysis"] = analysis
        context["popular_symbols"] = POPULAR_RESEARCH_SYMBOLS
        return context


class AIStockDetailTabPartialView(LoginRequiredMixin, View):
    """
    HTMX endpoint for embedding AI research directly into the Stock Detail view tab.
    """
    def get(self, request, symbol: str, *args, **kwargs):
        symbol = symbol.strip().upper()
        role = request.GET.get("role", AIRole.INVESTOR).strip().upper()
        force_refresh = request.GET.get("force", "false").lower() == "true"

        if role not in AIRole.values:
            role = AIRole.INVESTOR

        listing = get_object_or_404(
            ExchangeListing.objects.select_related("instrument", "exchange"),
            symbol=symbol,
            is_tradeable=True,
        )

        analysis = AIResearchService.analyze_stock(
            listing=listing,
            role=role,
            user=request.user,
            force_refresh=force_refresh,
        )

        return render(
            request,
            "ai_analysis/partials/analysis_card.html",
            {
                "analysis": analysis,
                "listing": listing,
                "selected_role": role,
            },
        )
