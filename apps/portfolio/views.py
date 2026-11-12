"""
Portfolio Management Views.
Handles aggregate portfolio valuation, asset allocation, sector exposure, and concentration risk.
"""
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from apps.core.mixins import HTMXResponseMixin
from apps.holdings.models import Holding
from apps.portfolio.models import Portfolio
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

        # Stock Concentration Check
        for h in holdings:
            if current_val > 0:
                pct = round((h.current_value / current_val * Decimal("100.0")), 1)
                h.allocation_percent = pct
                if pct >= Decimal("20.0"):
                    concentration_warnings.append(
                        f"High Stock Concentration: {h.listing.symbol} represents {pct}% of your equity portfolio."
                    )
            else:
                h.allocation_percent = Decimal("0.0")

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
