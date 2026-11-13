"""
Portfolio Management Views.
Handles aggregate portfolio valuation, asset allocation, sector exposure, and concentration risk.
"""
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from apps.core.mixins import HTMXResponseMixin
from apps.holdings.models import Holding
from apps.instruments.models import ExchangeListing
from apps.market.models import MarketQuote
from apps.portfolio.models import (
    ConvictionLevel,
    InvestmentHorizon,
    InvestmentJournalEntry,
    InvestmentJournalStatus,
    Portfolio,
)
from services.portfolio.accounting import FIFOAccountingEngine


class PortfolioOverviewView(LoginRequiredMixin, HTMXResponseMixin, TemplateView):
    """
    Executive summary of user's portfolio: net worth, unrealized/realized P&L,
    sector allocation breakdown, and concentration risk warnings.
    """
    template_name = "portfolio/overview.html"
    partial_template_name = "portfolio/partials/overview_partial.html"
    active_nav = "portfolio_overview"

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
        context["page_title"] = f"Portfolio Overview - {portfolio.name}"

        # Fetch active holdings
        holdings = list(
            Holding.objects.filter(portfolio=portfolio, total_quantity__gt=0)
            .select_related("listing__instrument", "listing__exchange")
            .order_by("-current_value")
        )

        # Refresh pricing for active holdings
        for h in holdings:
            FIFOAccountingEngine.reconcile_holding(portfolio, h.listing)

        # Reload after reconciliation
        holdings = list(
            Holding.objects.filter(portfolio=portfolio, total_quantity__gt=0)
            .select_related("listing__instrument", "listing__exchange")
            .order_by("-current_value")
        )
        context["holdings"] = holdings

        total_invested = sum((h.invested_amount for h in holdings), Decimal("0.00"))
        current_val = sum((h.current_value for h in holdings), Decimal("0.00"))
        unrealised = current_val - total_invested
        realised = sum((h.realised_pnl for h in holdings), Decimal("0.00"))
        dividends = sum((h.dividend_earned for h in holdings), Decimal("0.00"))

        total_net_worth = current_val + portfolio.cash_balance
        unrealised_pct = (
            (unrealised / total_invested * Decimal("100.0"))
            if total_invested > Decimal("0.00")
            else Decimal("0.00")
        )

        context["total_invested"] = total_invested
        context["current_value"] = current_val
        context["unrealised_pnl"] = unrealised
        context["unrealised_pnl_percent"] = unrealised_pct
        context["realised_pnl"] = realised
        context["dividend_total"] = dividends
        context["total_net_worth"] = total_net_worth

        # Sector Exposure Breakdown
        sectors: dict[str, Decimal] = {}
        for h in holdings:
            sec = h.listing.instrument.sector or "Other"
            sectors[sec] = sectors.get(sec, Decimal("0.00")) + h.current_value

        sector_breakdown = []
        concentration_warnings = []

        for sec, val in sorted(sectors.items(), key=lambda x: x[1], reverse=True):
            pct = round((val / current_val * Decimal("100.0")), 1) if current_val > 0 else Decimal("0.0")
            sector_breakdown.append({"sector": sec, "value": val, "percent": pct})
            if pct >= Decimal("35.0"):
                concentration_warnings.append(f"High Sector Concentration: {sec} represents {pct}% of your holdings.")

        context["sector_breakdown"] = sector_breakdown

        # Fetch latest market quotes for day change calculations
        listing_ids = [h.listing_id for h in holdings]
        quotes_dict = {}
        for q in MarketQuote.objects.filter(listing_id__in=listing_ids).order_by("retrieved_at"):
            quotes_dict[q.listing_id] = q

        total_day_pnl = Decimal("0.00")
        gainers_count = 0
        losers_count = 0

        # Stock Concentration Check & Enrichment
        for h in holdings:
            quote = quotes_dict.get(h.listing_id)
            if quote and quote.change is not None:
                h.day_change = quote.change
                h.day_change_percent = quote.change_percent or Decimal("0.00")
                h.day_pnl = Decimal(str(h.total_quantity)) * quote.change
            else:
                h.day_change = Decimal("0.00")
                h.day_change_percent = Decimal("0.00")
                h.day_pnl = Decimal("0.00")
            total_day_pnl += h.day_pnl

            if h.unrealised_pnl > Decimal("0.00"):
                gainers_count += 1
            elif h.unrealised_pnl < Decimal("0.00"):
                losers_count += 1

            if current_val > 0:
                pct = round((h.current_value / current_val * Decimal("100.0")), 1)
                h.allocation_percent = pct
                if pct >= Decimal("20.0"):
                    concentration_warnings.append(
                        f"High Stock Concentration: {h.listing.symbol} represents {pct}% of your equity portfolio."
                    )
            else:
                h.allocation_percent = Decimal("0.0")

        context["total_day_pnl"] = total_day_pnl
        prev_equity_val = current_val - total_day_pnl
        context["day_pnl_percent"] = (
            (total_day_pnl / prev_equity_val * Decimal("100.0"))
            if prev_equity_val > Decimal("0.00")
            else Decimal("0.00")
        )
        context["gainers_count"] = gainers_count
        context["losers_count"] = losers_count
        context["concentration_warnings"] = concentration_warnings
        return context


class PortfolioImportView(LoginRequiredMixin, HTMXResponseMixin, TemplateView):
    """
    UI interface for importing stock holdings via CSV file upload or direct text paste.
    Supports broker exports (Zerodha Kite, Groww, Upstox, or standard CSV format).
    """
    template_name = "portfolio/import_holdings.html"
    partial_template_name = "portfolio/partials/import_holdings_partial.html"
    active_nav = "portfolio_overview"

    def get_portfolio(self):
        portfolio, _ = Portfolio.objects.get_or_create(
            user=self.request.user,
            is_default=True,
            defaults={"name": "My Equity Portfolio", "currency": "INR"},
        )
        return portfolio

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["portfolio"] = self.get_portfolio()
        context["page_title"] = "Import Holdings - CSV & Broker Export"
        return context

    def post(self, request, *args, **kwargs):
        from django.contrib import messages
        from django.http import HttpResponseRedirect
        from django.shortcuts import redirect
        from django.urls import reverse

        from services.portfolio.importer import PortfolioCSVImporter

        portfolio = self.get_portfolio()
        csv_text = request.POST.get("csv_text", "").strip()
        clear_existing = request.POST.get("clear_existing") == "on"

        # Check uploaded file
        if "csv_file" in request.FILES:
            uploaded = request.FILES["csv_file"]
            try:
                csv_text = uploaded.read().decode("utf-8", errors="replace").strip()
            except Exception as e:
                messages.error(request, f"Failed to read uploaded file: {e}")
                return self.get(request, *args, **kwargs)

        if not csv_text:
            messages.error(request, "Please provide CSV data by uploading a file or pasting rows into the text area.")
            return self.get(request, *args, **kwargs)

        try:
            result = PortfolioCSVImporter.parse_and_import(
                portfolio=portfolio,
                content=csv_text,
                clear_existing=clear_existing,
            )
            count = result["imported_count"]
            tot_inv = result["total_invested"]
            messages.success(
                request,
                f"Successfully imported {count} holdings (Total Capital: ₹{tot_inv:,.2f}) into '{portfolio.name}'.",
            )
        except Exception as e:
            messages.error(request, f"Import error: {e}")
            return self.get(request, *args, **kwargs)

        redirect_url = reverse("portfolio:overview")
        if request.htmx:
            resp = HttpResponseRedirect(redirect_url)
            resp["HX-Redirect"] = redirect_url
            return resp
        return redirect(redirect_url)


class InvestmentJournalListView(HTMXResponseMixin, TemplateView):
    """
    Long-term investor thesis journal.
    Tracks conviction level, economic moats, quarterly earnings updates,
    and long-term fair value price targets.
    """
    template_name = "portfolio/investment_journal.html"
    partial_template_name = "portfolio/partials/investment_journal_partial.html"
    active_nav = "investment_journal"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Investment Journal & Long-Term Theses"

        user = self.request.user if self.request.user.is_authenticated else None
        entries_qs = InvestmentJournalEntry.objects.all().select_related("listing__instrument", "user")
        if user:
            entries_qs = entries_qs.filter(user=user)

        # Filters
        conviction_filter = self.request.GET.get("conviction", "").strip()
        status_filter = self.request.GET.get("status", "").strip()
        search_query = self.request.GET.get("q", "").strip()

        if conviction_filter:
            entries_qs = entries_qs.filter(conviction=conviction_filter)
        if status_filter:
            entries_qs = entries_qs.filter(status=status_filter)
        if search_query:
            entries_qs = entries_qs.filter(
                Q(listing__symbol__icontains=search_query)
                | Q(title__icontains=search_query)
                | Q(listing__instrument__display_name__icontains=search_query)
            )

        entries_list = []
        for entry in entries_qs:
            quote = MarketQuote.objects.filter(listing=entry.listing).first()
            upside_pct = None
            if entry.target_price and quote and quote.price and quote.price > 0:
                upside_pct = round(((entry.target_price - quote.price) / quote.price) * Decimal("100.0"), 2)

            entries_list.append({
                "entry": entry,
                "quote": quote,
                "upside_pct": upside_pct,
            })

        total_theses = len(entries_list)
        high_conviction = sum(1 for e in entries_list if e["entry"].conviction == ConvictionLevel.HIGH)
        active_theses = sum(1 for e in entries_list if e["entry"].status == InvestmentJournalStatus.ACTIVE)

        # Listings for "+ New Thesis" dropdown
        tradeable_listings = (
            ExchangeListing.objects.filter(is_tradeable=True)
            .select_related("instrument")
            .order_by("symbol")
        )

        context["theses"] = entries_list
        context["total_theses"] = total_theses
        context["high_conviction_count"] = high_conviction
        context["active_theses_count"] = active_theses
        context["tradeable_listings"] = tradeable_listings
        context["conviction_choices"] = ConvictionLevel.choices
        context["horizon_choices"] = InvestmentHorizon.choices
        context["status_choices"] = InvestmentJournalStatus.choices
        context["active_conviction"] = conviction_filter
        context["active_status"] = status_filter
        context["search_query"] = search_query
        return context


class InvestmentJournalCreateView(View):
    """Handles creation of a new long-term investment thesis."""
    def post(self, request, *args, **kwargs):
        user = request.user if request.user.is_authenticated else None
        if not user:
            from django.contrib.auth import get_user_model
            user = get_user_model().objects.filter(is_superuser=True).first() or get_user_model().objects.first()

        portfolio = Portfolio.objects.filter(user=user, is_default=True).first() or Portfolio.objects.filter(user=user).first()
        symbol = request.POST.get("symbol", "").strip()
        title = request.POST.get("title", "").strip()
        narrative = request.POST.get("thesis_narrative", "").strip()
        moat = request.POST.get("moat_description", "").strip()
        conviction = request.POST.get("conviction", ConvictionLevel.HIGH)
        horizon = request.POST.get("horizon", InvestmentHorizon.MEDIUM)
        target_str = request.POST.get("target_price", "").strip()
        key_risks = request.POST.get("key_risks", "").strip()
        catalysts = request.POST.get("catalysts", "").strip()

        listing = ExchangeListing.objects.filter(symbol__iexact=symbol).first()
        if not listing or not title or not narrative:
            messages.error(request, "Symbol, Title, and Thesis Narrative are required.")
            redirect_url = reverse("portfolio:investment_journal")
            return redirect(redirect_url)

        target_price = None
        if target_str:
            try:
                target_price = Decimal(target_str)
            except Exception:
                target_price = None

        InvestmentJournalEntry.objects.create(
            user=user,
            portfolio=portfolio,
            listing=listing,
            title=title,
            thesis_narrative=narrative,
            moat_description=moat,
            conviction=conviction,
            horizon=horizon,
            target_price=target_price,
            key_risks=key_risks,
            catalysts=catalysts,
            status=InvestmentJournalStatus.ACTIVE,
        )
        messages.success(request, f"Investment thesis for {listing.symbol} saved successfully.")
        redirect_url = reverse("portfolio:investment_journal")
        if request.htmx:
            resp = HttpResponseRedirect(redirect_url)
            resp["HX-Redirect"] = redirect_url
            return resp
        return redirect(redirect_url)


class InvestmentJournalDeleteView(View):
    """Deletes an investment journal thesis entry."""
    def post(self, request, pk, *args, **kwargs):
        entry = get_object_or_404(InvestmentJournalEntry, pk=pk)
        symbol = entry.listing.symbol
        entry.delete()
        messages.info(request, f"Investment thesis for {symbol} removed.")
        redirect_url = reverse("portfolio:investment_journal")
        if request.htmx:
            resp = HttpResponseRedirect(redirect_url)
            resp["HX-Redirect"] = redirect_url
            return resp
        return redirect(redirect_url)
