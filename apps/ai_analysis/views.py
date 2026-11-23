"""
AI Stock Analysis Views.
Provides the interactive AI Research Hub and embeddable stock research partials.
"""
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, render
from django.views import View
from django.views.generic import TemplateView

from apps.ai_analysis.models import AIRole
from apps.core.mixins import HTMXResponseMixin
from apps.holdings.models import Holding
from apps.instruments.models import ExchangeListing
from apps.market.models import MarketQuote
from apps.portfolio.models import Portfolio
from services.ai.researcher import AIResearchService
from services.recommendations.evaluator import RecommendationEvaluator

POPULAR_RESEARCH_SYMBOLS = [
    "SWSOLAR",
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

        # Quick Picks: dynamically prioritize user's active holdings if available, then deduplicated liquid symbols
        quick_symbols = []
        if self.request.user.is_authenticated:
            try:
                user_holdings = list(
                    Holding.objects.filter(portfolio__user=self.request.user)
                    .values_list("listing__symbol", flat=True)
                    .distinct()[:5]
                )
                quick_symbols.extend(user_holdings)
            except Exception:
                pass

        for s in POPULAR_RESEARCH_SYMBOLS:
            if s not in quick_symbols:
                quick_symbols.append(s)
            if len(quick_symbols) >= 8:
                break

        context["popular_symbols"] = quick_symbols
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


class AIRecommendationsView(HTMXResponseMixin, TemplateView):
    """
    Dual-Perspective AI Recommendation Engine.
    Distinguishes actionable guidance for Existing Portfolio Holders vs New Prospective Investors.
    Strictly enforces capital preservation and flags invalid averaging-down attempts.
    """
    template_name = "ai_analysis/recommendations.html"
    partial_template_name = "ai_analysis/partials/recommendations_partial.html"
    active_nav = "ai_recommendations"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "AI Investment Recommendations"
        context["active_nav"] = "ai_recommendations"

        user = self.request.user if self.request.user.is_authenticated else None
        portfolio = None
        if user:
            portfolio = (
                Portfolio.objects.filter(user=user, is_default=True).first()
                or Portfolio.objects.filter(user=user).first()
            )
        if not portfolio:
            portfolio = Portfolio.objects.first()

        tab_filter = self.request.GET.get("tab", "all").strip().lower()
        search_query = self.request.GET.get("q", "").strip()
        action_filter = self.request.GET.get("action", "all").strip()

        holdings = []
        portfolio_total_value = Decimal("0.00")
        if portfolio:
            holdings = list(
                Holding.objects.filter(portfolio=portfolio, total_quantity__gt=0)
                .select_related("listing__instrument", "listing__exchange")
            )
            portfolio_total_value = sum((h.current_value for h in holdings), Decimal("0.00"))

        holding_evaluations = []
        for h in holdings:
            tech = h.listing.technical_snapshots.order_by("-timestamp").first()
            fund = h.listing.instrument.fundamental_snapshots.order_by("-created_at").first()
            quote = MarketQuote.objects.filter(listing=h.listing).order_by("-retrieved_at").first()
            evaluation = RecommendationEvaluator.evaluate(
                listing=h.listing,
                holding=h,
                technical=tech,
                fundamental=fund,
                portfolio_total_value=portfolio_total_value,
            )
            rec = evaluation["existing_holder"]

            action = rec["action"]
            if action == "PARTIAL PROFIT BOOKING":
                badge_class = "badge-soft-warning"
            elif action == "ADD / ACCUMULATE":
                badge_class = "badge-soft-success"
            elif action in ("REDUCE EXPOSURE", "EXIT"):
                badge_class = "badge-soft-danger"
            elif action == "HOLD / TIGHTEN STOP":
                badge_class = "badge-soft-info"
            else:
                badge_class = "badge bg-light text-secondary border"

            item = {
                "holding": h,
                "listing": h.listing,
                "quote": quote,
                "rec": rec,
                "tech": tech,
                "fund": fund,
                "badge_class": badge_class,
                "is_action_required": action not in ("HOLD", "HOLD / TIGHTEN STOP"),
            }
            holding_evaluations.append(item)

        held_listing_ids = {h.listing_id for h in holdings}
        prospective_listings = list(
            ExchangeListing.objects.filter(is_tradeable=True, exchange__code="NSE")
            .exclude(id__in=held_listing_ids)
            .select_related("instrument", "exchange")
            .order_by("symbol")[:30]
        )

        prospective_evaluations = []
        for listing in prospective_listings:
            tech = listing.technical_snapshots.order_by("-timestamp").first()
            fund = listing.instrument.fundamental_snapshots.order_by("-created_at").first()
            quote = MarketQuote.objects.filter(listing=listing).order_by("-retrieved_at").first()
            evaluation = RecommendationEvaluator.evaluate(
                listing=listing,
                holding=None,
                technical=tech,
                fundamental=fund,
            )
            rec = evaluation["new_investor"]
            status = rec["status"]
            if status == "FAVORABLE ENTRY":
                badge_class = "badge-soft-success"
            elif status == "WAIT FOR PULLBACK":
                badge_class = "badge-soft-info"
            else:
                badge_class = "badge-soft-warning"

            item = {
                "listing": listing,
                "quote": quote,
                "rec": rec,
                "tech": tech,
                "fund": fund,
                "badge_class": badge_class,
            }
            prospective_evaluations.append(item)

        prospective_evaluations.sort(
            key=lambda x: (
                0 if x["rec"]["status"] == "FAVORABLE ENTRY"
                else 1 if x["rec"]["status"] == "WAIT FOR PULLBACK"
                else 2
            )
        )

        total_holdings_analyzed = len(holding_evaluations)
        actions_required_count = sum(1 for h in holding_evaluations if h["is_action_required"])
        favorable_entries_count = sum(1 for p in prospective_evaluations if p["rec"]["status"] == "FAVORABLE ENTRY")
        capital_alerts_count = sum(
            1 for h in holding_evaluations
            if h["rec"]["warning"] or h["rec"]["action"] in ("EXIT", "REDUCE EXPOSURE")
        )

        filtered_holdings = holding_evaluations
        filtered_prospective = prospective_evaluations

        if search_query:
            sq = search_query.lower()
            filtered_holdings = [
                h for h in filtered_holdings
                if sq in h["listing"].symbol.lower()
                or sq in (h["listing"].instrument.display_name or "").lower()
                or sq in (h["listing"].instrument.sector or "").lower()
            ]
            filtered_prospective = [
                p for p in filtered_prospective
                if sq in p["listing"].symbol.lower()
                or sq in (p["listing"].instrument.display_name or "").lower()
                or sq in (p["listing"].instrument.sector or "").lower()
            ]

        if action_filter == "actions_required":
            filtered_holdings = [h for h in filtered_holdings if h["is_action_required"]]
        elif action_filter == "profit_booking":
            filtered_holdings = [h for h in filtered_holdings if h["rec"]["action"] == "PARTIAL PROFIT BOOKING"]
        elif action_filter == "accumulate":
            filtered_holdings = [h for h in filtered_holdings if h["rec"]["action"] == "ADD / ACCUMULATE"]
        elif action_filter == "reduce_exit":
            filtered_holdings = [h for h in filtered_holdings if h["rec"]["action"] in ("REDUCE EXPOSURE", "EXIT")]
        elif action_filter == "hold":
            filtered_holdings = [h for h in filtered_holdings if h["rec"]["action"] in ("HOLD", "HOLD / TIGHTEN STOP")]
        elif action_filter == "favorable":
            filtered_prospective = [p for p in filtered_prospective if p["rec"]["status"] == "FAVORABLE ENTRY"]
        elif action_filter == "pullback":
            filtered_prospective = [p for p in filtered_prospective if p["rec"]["status"] == "WAIT FOR PULLBACK"]

        context.update({
            "portfolio": portfolio,
            "portfolio_total_value": portfolio_total_value,
            "holdings_evaluations": filtered_holdings,
            "prospective_evaluations": filtered_prospective,
            "total_holdings_analyzed": total_holdings_analyzed,
            "actions_required_count": actions_required_count,
            "favorable_entries_count": favorable_entries_count,
            "capital_alerts_count": capital_alerts_count,
            "active_tab": tab_filter,
            "search_query": search_query,
            "action_filter": action_filter,
        })
        return context
