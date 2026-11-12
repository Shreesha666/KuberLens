"""
Views for Stock Research, Global Autocomplete Search, and Detailed Analytics.
"""
import logging
from datetime import timedelta
from decimal import Decimal

from django.db.models import Avg, Max, Min, Q
from django.http import Http404, JsonResponse
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from apps.core.mixins import HTMXResponseMixin
from apps.fundamental_analysis.models import FundamentalSnapshot
from apps.instruments.models import ExchangeListing, Instrument
from apps.market.models import HistoricalCandle, MarketQuote
from apps.technical_analysis.models import TechnicalIndicatorSnapshot
from services.indicators.calculator import TechnicalIndicatorCalculator
from services.market_data.service import MarketDataService

logger = logging.getLogger(__name__)


class StockSearchView(View):
    """
    Fast autocomplete search endpoint for the persistent header search input.
    Supports search by NSE/BSE symbol, company name, display name, or ISIN.
    """
    def get(self, request, *args, **kwargs):
        query = request.GET.get("q", "").strip()
        if not query or len(query) < 1:
            if request.htmx:
                return JsonResponse({"results": []})
            return JsonResponse({"results": []})

        listings = (
            ExchangeListing.objects.filter(is_tradeable=True)
            .filter(
                Q(symbol__icontains=query)
                | Q(instrument__display_name__icontains=query)
                | Q(instrument__legal_name__icontains=query)
                | Q(instrument__isin__icontains=query)
            )
            .select_related("instrument", "exchange")
            .order_by("symbol")[:8]
        )

        results = [
            {
                "symbol": item.symbol,
                "exchange": item.exchange.code,
                "name": item.instrument.display_name,
                "legal_name": item.instrument.legal_name,
                "isin": item.instrument.isin,
                "sector": item.instrument.sector,
                "cap": item.instrument.market_cap_category,
                "url": f"/stocks/{item.symbol}/",
            }
            for item in listings
        ]

        if request.htmx:
            from django.template.loader import render_to_string
            html = render_to_string("stocks/partials/search_results_partial.html", {"results": results, "query": query}, request=request)
            from django.http import HttpResponse
            return HttpResponse(html)

        return JsonResponse({"results": results})


class StockListView(HTMXResponseMixin, ListView):
    """
    Stock directory overview page with sector, cap category, and exchange filters.
    """
    model = ExchangeListing
    template_name = "stocks/stock_list.html"
    partial_template_name = "stocks/partials/stock_list_partial.html"
    context_object_name = "listings"
    active_nav = "stock_analysis"
    paginate_by = 20

    def get_queryset(self):
        qs = (
            ExchangeListing.objects.filter(is_tradeable=True, is_primary=True)
            .select_related("instrument", "exchange")
            .order_by("symbol")
        )
        sector = self.request.GET.get("sector")
        cap = self.request.GET.get("cap")
        search = self.request.GET.get("search")

        if sector:
            qs = qs.filter(instrument__sector__iexact=sector)
        if cap:
            qs = qs.filter(instrument__market_cap_category__iexact=cap)
        if search:
            qs = qs.filter(
                Q(symbol__icontains=search)
                | Q(instrument__display_name__icontains=search)
                | Q(instrument__legal_name__icontains=search)
            )
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Stock Research & Intelligence"
        context["sectors"] = (
            Instrument.objects.filter(is_active=True)
            .values_list("sector", flat=True)
            .distinct()
            .order_by("sector")
        )
        context["selected_sector"] = self.request.GET.get("sector", "")
        context["selected_cap"] = self.request.GET.get("cap", "")
        context["search_term"] = self.request.GET.get("search", "")
        return context


class StockDetailView(HTMXResponseMixin, DetailView):
    """
    Comprehensive stock research profile view.
    Displays live/delayed quote with 2D provenance, interactive chart, technical indicators,
    and fundamental analysis scoring.
    """
    model = ExchangeListing
    template_name = "stocks/stock_detail.html"
    partial_template_name = "stocks/partials/stock_detail_partial.html"
    context_object_name = "listing"
    active_nav = "stock_analysis"

    def get_object(self, queryset=None):
        symbol = self.kwargs.get("symbol", "").upper()
        listing = (
            ExchangeListing.objects.filter(symbol=symbol, is_tradeable=True)
            .select_related("instrument", "exchange")
            .first()
        )
        if not listing:
            raise Http404(f"Instrument listing '{symbol}' not found.")
        return listing

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        listing = self.object
        context["page_title"] = f"{listing.symbol} - {listing.instrument.display_name}"

        # 1. Retrieve Current Quote (Live, Delayed, Cached, or Offline)
        try:
            quote = MarketDataService.get_quote(listing)
        except Exception as e:
            logger.warning("Could not fetch quote for %s: %s", listing.symbol, e)
            quote = None
        context["quote"] = quote

        # 2. Historical 52-Week Range & Candles
        one_year_ago = timezone.now() - timedelta(days=365)
        candles_qs = HistoricalCandle.objects.filter(
            listing=listing,
            interval="1d",
            timestamp__gte=one_year_ago,
        ).order_by("timestamp")

        candles = list(candles_qs)
        context["candle_count"] = len(candles)

        if candles:
            agg = candles_qs.aggregate(high_52w=Max("high"), low_52w=Min("low"))
            context["high_52w"] = agg.get("high_52w")
            context["low_52w"] = agg.get("low_52w")
        else:
            context["high_52w"] = None
            context["low_52w"] = None

        # 3. Technical Indicators Snapshot
        tech_snapshot = (
            TechnicalIndicatorSnapshot.objects.filter(listing=listing)
            .order_by("-timestamp")
            .first()
        )

        # On-the-fly indicator calculation if candles exist but snapshot is missing
        if not tech_snapshot and candles:
            try:
                snapshots = TechnicalIndicatorCalculator.compute_and_store_snapshots(listing, candles)
                if snapshots:
                    tech_snapshot = snapshots[-1]
            except Exception as e:
                logger.error("Failed to compute technical indicators on the fly: %s", e)

        context["technical"] = tech_snapshot

        # 4. Fundamental Analysis Snapshot
        fund_snapshot = (
            FundamentalSnapshot.objects.filter(instrument=listing.instrument)
            .order_by("-calculated_at")
            .first()
        )
        context["fundamental"] = fund_snapshot

        # 5. Peer Listings in same sector
        context["peers"] = (
            ExchangeListing.objects.filter(
                instrument__sector=listing.instrument.sector,
                is_primary=True,
                is_tradeable=True,
            )
            .exclude(id=listing.id)
            .select_related("instrument", "exchange")[:5]
        )

        return context


class StockChartDataView(View):
    """
    JSON API for interactive candlestick charting.
    Returns array of candles with SMA overlays.
    """
    def get(self, request, symbol, *args, **kwargs):
        listing = (
            ExchangeListing.objects.filter(symbol=symbol.upper(), is_tradeable=True)
            .select_related("exchange")
            .first()
        )
        if not listing:
            return JsonResponse({"error": "Listing not found"}, status=404)

        days = int(request.GET.get("days", 180))
        interval = request.GET.get("interval", "1d")
        start_date = timezone.now() - timedelta(days=days)

        candles = list(
            HistoricalCandle.objects.filter(
                listing=listing,
                interval=interval,
                timestamp__gte=start_date,
            ).order_by("timestamp")
        )

        # Pull technical snapshots for moving averages
        snapshots = {
            s.timestamp.date().isoformat(): s
            for s in TechnicalIndicatorSnapshot.objects.filter(
                listing=listing,
                interval=interval,
                timestamp__gte=start_date,
            )
        }

        data = []
        for c in candles:
            date_str = c.timestamp.date().isoformat()
            snap = snapshots.get(date_str)
            item = {
                "time": date_str,
                "open": float(c.open),
                "high": float(c.high),
                "low": float(c.low),
                "close": float(c.close),
                "volume": c.volume,
                "sma20": float(snap.sma_20) if snap and snap.sma_20 else None,
                "sma50": float(snap.sma_50) if snap and snap.sma_50 else None,
            }
            data.append(item)

        return JsonResponse({"symbol": listing.symbol, "exchange": listing.exchange.code, "candles": data})


class SectorAnalysisView(HTMXResponseMixin, TemplateView):
    """
    Sector & Industry Intelligence view.
    Aggregates market capitalization, 1-day performance, valuation multiples,
    and constituent stocks across all Indian stock market sectors.
    """
    template_name = "stocks/sector_analysis.html"
    partial_template_name = "stocks/partials/sector_analysis_partial.html"
    active_nav = "sector_analysis"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Sector Analysis & Industry Performance"

        selected_sector = self.request.GET.get("sector", "").strip()

        # Query all distinct sectors from instruments
        sector_names = list(
            Instrument.objects.exclude(sector="")
            .values_list("sector", flat=True)
            .distinct()
            .order_by("sector")
        )

        sectors_data = []
        for s in sector_names:
            insts = Instrument.objects.filter(sector=s, is_active=True)
            stock_count = insts.count()
            if stock_count == 0:
                continue

            inst_ids = list(insts.values_list("id", flat=True))
            quotes = list(
                MarketQuote.objects.filter(listing__instrument_id__in=inst_ids)
                .select_related("listing__instrument")
            )

            avg_chg = Decimal("0.00")
            advancers = 0
            decliners = 0
            if quotes:
                total_chg = sum(
                    (q.change_percent for q in quotes if q.change_percent is not None),
                    Decimal("0"),
                )
                avg_chg = round(total_chg / len(quotes), 2)
                advancers = sum(1 for q in quotes if q.change_percent and q.change_percent > 0)
                decliners = sum(1 for q in quotes if q.change_percent and q.change_percent < 0)

            fund = FundamentalSnapshot.objects.filter(instrument_id__in=inst_ids).aggregate(
                avg_pe=Avg("pe_ratio"),
                avg_pb=Avg("pb_ratio"),
                avg_roe=Avg("roe"),
            )

            large_count = insts.filter(market_cap_category="LARGE").count()
            mid_count = insts.filter(market_cap_category="MID").count()
            small_count = insts.filter(market_cap_category="SMALL").count()

            top_stock = max(
                quotes,
                key=lambda q: q.change_percent if q.change_percent is not None else Decimal("-999"),
                default=None,
            )
            worst_stock = min(
                quotes,
                key=lambda q: q.change_percent if q.change_percent is not None else Decimal("999"),
                default=None,
            )

            sectors_data.append({
                "name": s,
                "stock_count": stock_count,
                "large_count": large_count,
                "mid_count": mid_count,
                "small_count": small_count,
                "avg_change_percent": avg_chg,
                "advancers": advancers,
                "decliners": decliners,
                "unchanged": stock_count - advancers - decliners,
                "avg_pe": round(fund["avg_pe"], 2) if fund["avg_pe"] else None,
                "avg_pb": round(fund["avg_pb"], 2) if fund["avg_pb"] else None,
                "avg_roe": round(fund["avg_roe"], 2) if fund["avg_roe"] else None,
                "top_stock": top_stock,
                "worst_stock": worst_stock,
            })

        # Sort sectors by avg_change_percent descending (top gainers first)
        sectors_data.sort(key=lambda x: x["avg_change_percent"], reverse=True)

        context["sectors"] = sectors_data
        context["total_sectors"] = len(sectors_data)
        context["selected_sector"] = selected_sector

        # If a sector is selected, fetch constituent listings with quotes & snapshots
        constituent_stocks = []
        selected_sector_summary = None
        if selected_sector:
            selected_sector_summary = next(
                (sec for sec in sectors_data if sec["name"].lower() == selected_sector.lower()),
                None,
            )
            if selected_sector_summary:
                selected_sector = selected_sector_summary["name"]
                context["selected_sector"] = selected_sector

            listings = (
                ExchangeListing.objects.filter(
                    instrument__sector__iexact=selected_sector, is_tradeable=True
                )
                .select_related("instrument", "exchange")
                .order_by("symbol")
            )
            for listing_obj in listings:
                q = MarketQuote.objects.filter(listing=listing_obj).first()
                f = FundamentalSnapshot.objects.filter(instrument=listing_obj.instrument).first()
                t = (
                    TechnicalIndicatorSnapshot.objects.filter(listing=listing_obj)
                    .order_by("-timestamp")
                    .first()
                )
                constituent_stocks.append({
                    "symbol": listing_obj.symbol,
                    "company_name": listing_obj.instrument.display_name,
                    "market_cap_category": listing_obj.instrument.market_cap_category,
                    "quote": q,
                    "fundamental": f,
                    "technical": t,
                })

            constituent_stocks.sort(
                key=lambda x: (
                    x["quote"].change_percent
                    if x["quote"] and x["quote"].change_percent is not None
                    else Decimal("-999")
                ),
                reverse=True,
            )

        context["selected_sector_summary"] = selected_sector_summary
        context["constituent_stocks"] = constituent_stocks
        return context
