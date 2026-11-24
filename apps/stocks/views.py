"""
Views for Stock Research, Global Autocomplete Search, and Detailed Analytics.
"""
import datetime
import logging
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Avg, Max, Min, Sum
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView
import pandas as pd

from apps.core.mixins import HTMXResponseMixin
from apps.fundamental_analysis.models import FundamentalSnapshot
from apps.holdings.models import Holding
from apps.instruments.models import ExchangeListing, Instrument
from apps.market.models import HistoricalCandle, MarketQuote
from apps.ml_engine.models import (
    MarketRegimeType,
    MLPrediction,
    MLShadowEvaluationRecord,
    ShadowCaptureMode,
)
from apps.portfolio.models import Portfolio
from apps.stocks.search import smart_stock_search
from apps.technical_analysis.models import TechnicalIndicatorSnapshot
from services.indicators.calculator import TechnicalIndicatorCalculator
from services.logos import CompanyLogoService
from services.market_data.service import MarketDataService
from services.ml.engine import MarketRegimeClassifier, StockMLRanker
from services.ml.features import FeaturePipeline
from services.ml.risk_engine import (
    MarketRegimeClassification,
    MLRiskVetoEngine,
    RiskVetoAssessment,
    RiskVetoLevel,
)
from services.ml.shadow_service import ShadowEvaluationService
from services.recommendations.evaluator import RecommendationEvaluator

logger = logging.getLogger(__name__)


class StockSearchView(View):
    """
    Fast autocomplete search endpoint for the persistent header search input.
    Supports search by NSE/BSE symbol, company name, display name, or ISIN.
    """
    def get(self, request, *args, **kwargs):
        query = request.GET.get("q", "").strip() or request.GET.get("symbol", "").strip()
        context_mode = request.GET.get("context", "").strip()
        role = request.GET.get("role", "INVESTOR").strip()
        target_id = request.GET.get("target_id", "search-results").strip()

        if not query or len(query) < 1:
            if request.htmx:
                return HttpResponse("")
            return JsonResponse({"results": []})

        listings = smart_stock_search(query, limit=8)

        # Batch fetch latest quotes for listings in search results
        listing_ids = [item.id for item in listings]
        quotes_by_listing = {}
        for quote in MarketQuote.objects.filter(listing_id__in=listing_ids).order_by("listing_id", "-retrieved_at"):
            if quote.listing_id not in quotes_by_listing:
                quotes_by_listing[quote.listing_id] = quote

        results = [
            {
                "symbol": item.symbol,
                "exchange": item.exchange.code,
                "name": item.instrument.display_name,
                "legal_name": item.instrument.legal_name,
                "isin": item.instrument.isin,
                "sector": item.instrument.sector,
                "cap": item.instrument.market_cap_category,
                "url": (
                    f"/research/ai/?symbol={item.symbol}&role={role}"
                    if context_mode == "ai_hub"
                    else f"/stocks/{item.symbol}/"
                ),
                "price": float(quotes_by_listing[item.id].price) if item.id in quotes_by_listing else None,
                "change": float(quotes_by_listing[item.id].change) if item.id in quotes_by_listing else None,
                "change_percent": float(quotes_by_listing[item.id].change_percent) if item.id in quotes_by_listing else None,
            }
            for item in listings
        ]

        if request.htmx:
            from django.template.loader import render_to_string
            html = render_to_string(
                "stocks/partials/search_results_partial.html",
                {
                    "results": results,
                    "query": query,
                    "target_id": target_id,
                    "context_mode": context_mode,
                },
                request=request,
            )
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
            matching = smart_stock_search(search, limit=50)
            matching_ids = [m.id for m in matching]
            if matching_ids:
                from django.db.models import Case, When
                preserved_order = Case(*[When(pk=pk, then=pos) for pos, pk in enumerate(matching_ids)])
                qs = qs.filter(id__in=matching_ids).order_by(preserved_order)
            else:
                qs = qs.none()
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
            from services.market_data.auto_ingest import AutoIngestionService
            listing = AutoIngestionService.get_or_create_listing(symbol)

        if not listing:
            raise Http404(f"Instrument listing '{symbol}' not found.")
        return listing

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        listing = self.object
        context["page_title"] = f"{listing.symbol} - {listing.instrument.display_name}"

        from services.calendar.exchange_calendar import ExchangeCalendar
        context["is_market_open"] = ExchangeCalendar.is_market_open()
        context["market_session_status"] = ExchangeCalendar.get_session_status()

        # 1. Retrieve Current Quote (Live, Delayed, Cached, or Offline)
        try:
            quote = MarketDataService.get_quote(listing)
        except Exception as e:
            logger.warning("Could not fetch quote for %s: %s", listing.symbol, e)
            quote = None
        if not quote:
            quote = MarketQuote.objects.filter(listing=listing).order_by("-retrieved_at").first()
        context["quote"] = quote

        # 2. Historical 52-Week Range & Candles
        one_year_ago = timezone.now() - timedelta(days=365)
        candles_qs = HistoricalCandle.objects.filter(
            listing=listing,
            interval="1d",
            timestamp__gte=one_year_ago,
        ).order_by("timestamp")

        candles = list(candles_qs)

        # Auto-fetch if candles are empty
        if not candles:
            try:
                end_d = timezone.now().date()
                start_d = end_d - timedelta(days=365)
                candles = MarketDataService.get_historical_candles(
                    listing, start_date=start_d, end_date=end_d, interval="1d", fetch_if_missing=True
                )
                candles_qs = HistoricalCandle.objects.filter(
                    listing=listing,
                    interval="1d",
                    timestamp__gte=one_year_ago,
                ).order_by("timestamp")
            except Exception as e:
                logger.warning("Could not auto-fetch candles for %s: %s", listing.symbol, e)

        context["candle_count"] = len(candles)

        latest_candle = candles[-1] if candles else None
        if latest_candle:
            context["latest_eod_session"] = latest_candle.timestamp.date()
            context["latest_eod_close"] = latest_candle.close
            context["candle_source_provider"] = latest_candle.source_provider
            context["candle_data_as_of"] = latest_candle.timestamp
        else:
            context["latest_eod_session"] = None
            context["latest_eod_close"] = None
            context["candle_source_provider"] = None
            context["candle_data_as_of"] = None

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
        if not fund_snapshot:
            try:
                import yfinance as yf

                from services.fundamentals.analyzer import FundamentalAnalyzer

                t = yf.Ticker(f"{listing.symbol}.NS")
                info = getattr(t, "info", None) or {}
                div_yield = info.get("dividendYield")
                if div_yield is not None:
                    div_yield = (div_yield * 100) if div_yield < 1.0 else div_yield
                elif info.get("trailingAnnualDividendYield") is not None:
                    ty = info.get("trailingAnnualDividendYield")
                    div_yield = (ty * 100) if ty < 1.0 else ty

                raw_data = {
                    "pe_ratio": info.get("trailingPE") or info.get("forwardPE"),
                    "pb_ratio": info.get("priceToBook"),
                    "dividend_yield": div_yield,
                    "roe": (info.get("returnOnEquity") * 100) if info.get("returnOnEquity") else None,
                    "roce": (info.get("returnOnAssets") * 100) if info.get("returnOnAssets") else None,
                    "debt_to_equity": info.get("debtToEquity"),
                    "current_ratio": info.get("currentRatio"),
                    "revenue_growth_yoy": (info.get("revenueGrowth") * 100) if info.get("revenueGrowth") else None,
                    "operating_margin": (info.get("operatingMargins") * 100) if info.get("operatingMargins") else None,
                    "net_margin": (info.get("profitMargins") * 100) if info.get("profitMargins") else None,
                }
                if any(v is not None for v in raw_data.values()):
                    fund_snapshot = FundamentalAnalyzer.evaluate_instrument(listing.instrument, raw_data)
            except Exception as e:
                logger.warning("Could not auto-fetch fundamentals for %s: %s", listing.symbol, e)

        context["fundamental"] = fund_snapshot

        # Fetch / sync official trailing annual dividend rate and yield from Yahoo Finance
        dividend_amount = getattr(fund_snapshot, "dividend_rate", None)
        dividend_yield = getattr(fund_snapshot, "dividend_yield", None)

        if dividend_amount is None:
            try:
                from services.fundamentals.analyzer import FundamentalAnalyzer
                d_rate, d_yield = FundamentalAnalyzer.sync_dividend_from_yahoo(listing.symbol, listing.instrument)
                if d_rate is not None:
                    dividend_amount = d_rate
                if d_yield is not None:
                    dividend_yield = d_yield
            except Exception as e:
                logger.debug("Could not fetch Yahoo dividend for %s: %s", listing.symbol, e)

        # Fallback to calculation if dividend_yield exists but rate is missing
        if dividend_amount is None and dividend_yield and quote and quote.price:
            try:
                dividend_amount = round(
                    (Decimal(str(quote.price)) * Decimal(str(dividend_yield))) / Decimal("100.0"), 2
                )
            except Exception:
                dividend_amount = None

        context["dividend_amount"] = dividend_amount
        context["dividend_yield"] = dividend_yield

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

        # 6. Dual-Perspective Recommendation Framework (Existing Holder vs New Investor)
        user = self.request.user if self.request.user.is_authenticated else None
        portfolio = None
        if user:
            portfolio = (
                Portfolio.objects.filter(user=user, is_default=True).first()
                or Portfolio.objects.filter(user=user).first()
            )
        if not portfolio:
            portfolio = Portfolio.objects.first()

        holding = None
        total_portfolio_val = Decimal("0.00")
        if portfolio:
            holding = Holding.objects.filter(
                portfolio=portfolio,
                listing=listing,
                total_quantity__gt=0,
            ).first()
            total_portfolio_val = (
                Holding.objects.filter(portfolio=portfolio, total_quantity__gt=0)
                .aggregate(Sum("current_value"))
                .get("current_value__sum")
                or Decimal("0.00")
            )

        recommendations = RecommendationEvaluator.evaluate(
            listing=listing,
            holding=holding,
            technical=tech_snapshot,
            fundamental=fund_snapshot,
            portfolio_total_value=total_portfolio_val,
            quote=quote,
        )
        context["recommendations"] = recommendations
        context["holding"] = holding

        # Position allocation percentage within user portfolio
        holding_allocation_pct = Decimal("0.00")
        if holding and total_portfolio_val > 0 and holding.current_value:
            try:
                holding_allocation_pct = round(
                    (holding.current_value / total_portfolio_val) * Decimal("100.0"), 2
                )
            except Exception:
                pass
        context["holding_allocation_pct"] = holding_allocation_pct

        # 7. 5-Year Dividend History & Payout Analytics
        try:
            from services.fundamentals.analyzer import FundamentalAnalyzer

            cur_p = quote.price if quote and quote.price else None
            div_history_5y, div_summary_5y = FundamentalAnalyzer.get_five_year_dividend_history(
                symbol=listing.symbol, current_price=cur_p
            )
        except Exception as e:
            logger.warning("Could not fetch 5-year dividend history for %s: %s", listing.symbol, e)
            div_history_5y, div_summary_5y = [], {}

        context["dividend_history_5y"] = div_history_5y
        context["dividend_summary_5y"] = div_summary_5y

        # 8. Machine Learning Market Regime & Point-in-Time Statistical Predictions
        ml_prediction = None
        regime_info = None
        try:
            if len(candles) >= 20:
                ml_prediction = (
                    MLPrediction.objects.filter(listing=listing)
                    .select_related("model_record")
                    .order_by("-prediction_timestamp")
                    .first()
                )
                if not ml_prediction or (latest_candle and ml_prediction.as_of_session < latest_candle.timestamp.date()):
                    ml_prediction = StockMLRanker.evaluate_and_predict(listing)
                regime_info = MarketRegimeClassifier.classify_regime(candles)
        except Exception as e:
            logger.warning("Could not compute ML prediction for %s: %s", listing.symbol, e)

        context["ml_prediction"] = ml_prediction
        context["regime_info"] = regime_info

        # 9. Stock-Level Risk Intelligence & Multi-Factor Risk Veto
        risk_assessment = None
        try:
            if len(candles) >= 20:
                df_records = [{
                    "session_date": str(c.timestamp.date()),
                    "close_adj": float(c.close),
                    "high_adj": float(c.high),
                    "low_adj": float(c.low),
                    "open_adj": float(c.open),
                    "volume_adj": float(c.volume),
                } for c in candles]
                df_candles = pd.DataFrame(df_records)
                fp = FeaturePipeline(warmup_sessions=min(20, len(candles) - 1))
                df_feat = fp.compute_stock_features(df_candles)
                if not df_feat.empty:
                    last_row = df_feat.iloc[-1].to_dict()
                    last_row["symbol"] = listing.symbol
                    risk_assessment = MLRiskVetoEngine().assess_setup(last_row)

            if not risk_assessment:
                risk_assessment = RiskVetoAssessment(
                    symbol=listing.symbol,
                    session_date=str(latest_candle.timestamp.date()) if latest_candle else str(timezone.now().date()),
                    regime=MarketRegimeClassification.SIDEWAYS_CONSOLIDATION,
                    risk_level=RiskVetoLevel.INSUFFICIENT_DATA,
                    is_vetoed=True,
                    risk_score=100.0,
                    veto_reasons=["Insufficient historical session candles (< 20 sessions) to evaluate risk."],
                    metrics={},
                )
        except Exception as e:
            logger.warning("Could not assess risk for %s: %s", listing.symbol, e)
            risk_assessment = RiskVetoAssessment(
                symbol=listing.symbol,
                session_date=str(timezone.now().date()),
                regime=MarketRegimeClassification.SIDEWAYS_CONSOLIDATION,
                risk_level=RiskVetoLevel.INSUFFICIENT_DATA,
                is_vetoed=True,
                risk_score=100.0,
                veto_reasons=[f"Risk assessment calculation error: {e}"],
                metrics={},
            )

        context["risk_assessment"] = risk_assessment

        # 10. Forward Shadow Evaluation Records
        shadow_records = list(
            MLShadowEvaluationRecord.objects.filter(listing=listing)
            .order_by("-session_date")[:10]
        )
        context["shadow_records"] = shadow_records
        context["shadow_count"] = MLShadowEvaluationRecord.objects.filter(listing=listing).count()

        return context


class StockChartDataView(View):
    """
    JSON API for interactive candlestick charting using TradingView Lightweight Charts.
    Returns OHLCV candles, volume, technical indicators (SMA, EMA, Bollinger, RSI, MACD),
    and institutional trade levels (Stop Loss, Targets).
    """
    def get(self, request, symbol, *args, **kwargs):
        listing = (
            ExchangeListing.objects.filter(symbol=symbol.upper(), is_tradeable=True)
            .select_related("exchange", "instrument")
            .first()
        )
        if not listing:
            return JsonResponse({"error": "Listing not found"}, status=404)

        days = int(request.GET.get("days", 180))
        interval = request.GET.get("interval", "1d")

        query = HistoricalCandle.objects.filter(listing=listing, interval=interval)
        if 0 < days < 1800:
            latest_c = query.order_by("-timestamp").first()
            ref_now = latest_c.timestamp if latest_c else timezone.now()
            effective_days = max(days, 14) if days <= 7 else days
            start_date = ref_now - timedelta(days=effective_days)
            query = query.filter(timestamp__gte=start_date)
        else:
            start_date = None

        candles = list(query.order_by("timestamp"))

        # Auto-backfill if candles are missing
        if not candles:
            try:
                end_d = timezone.now().date()
                fetch_days = max(days, 180)
                start_d = end_d - timedelta(days=fetch_days)
                candles = MarketDataService.get_historical_candles(
                    listing, start_date=start_d, end_date=end_d, interval=interval, fetch_if_missing=True
                )
                if start_date:
                    candles = [c for c in candles if c.timestamp >= start_date]
            except Exception as e:
                logger.warning("Could not backfill candles for %s: %s", listing.symbol, e)

        # Deduplicate candles by session date to prevent duplicate timestamp errors in lightweight-charts
        candles_by_date = {}
        for c in candles:
            candles_by_date[c.timestamp.date()] = c
        candles = [candles_by_date[d] for d in sorted(candles_by_date.keys())]

        # Pull technical snapshots for moving averages and indicators
        snap_query = TechnicalIndicatorSnapshot.objects.filter(listing=listing, interval=interval)
        if start_date:
            snap_query = snap_query.filter(timestamp__gte=start_date)

        snapshots = {s.timestamp.date().isoformat(): s for s in snap_query}

        # If snapshots are empty or sparse, trigger on-the-fly calculation
        if len(snapshots) < len(candles) * 0.5 and len(candles) > 0:
            try:
                computed = TechnicalIndicatorCalculator.compute_and_store_snapshots(listing, candles)
                snapshots = {s.timestamp.date().isoformat(): s for s in computed}
            except Exception as e:
                logger.warning("Could not compute technical indicators on the fly: %s", e)

        # Precompute advanced overlays: SuperTrend, Parabolic SAR, and Fibonacci
        all_highs = [float(c.high) for c in candles]
        all_lows = [float(c.low) for c in candles]
        all_closes = [float(c.close) for c in candles]
        st_vals, st_dirs = TechnicalIndicatorCalculator.calculate_supertrend(all_highs, all_lows, all_closes)
        sar_vals, sar_longs = TechnicalIndicatorCalculator.calculate_parabolic_sar(all_highs, all_lows, all_closes)
        fib_levels = TechnicalIndicatorCalculator.calculate_fibonacci_levels(all_highs, all_lows)

        data = []
        cum_pv = 0.0
        cum_vol = 0
        for idx, c in enumerate(candles):
            date_str = c.timestamp.date().isoformat()
            snap = snapshots.get(date_str)
            vol = int(c.volume)
            typ_price = float(c.high + c.low + c.close) / 3.0
            cum_pv += typ_price * vol
            cum_vol += vol
            vwap = round(cum_pv / cum_vol, 2) if cum_vol > 0 else float(c.close)

            item = {
                "time": date_str,
                "open": float(c.open),
                "high": float(c.high),
                "low": float(c.low),
                "close": float(c.close),
                "volume": vol,
                "sma20": float(snap.sma_20) if snap and snap.sma_20 is not None else None,
                "sma50": float(snap.sma_50) if snap and snap.sma_50 is not None else None,
                "sma200": float(snap.sma_200) if snap and snap.sma_200 is not None else None,
                "ema9": float(snap.ema_9) if snap and snap.ema_9 is not None else None,
                "ema20": float(snap.ema_20) if snap and snap.ema_20 is not None else None,
                "ema50": float(snap.ema_50) if snap and snap.ema_50 is not None else None,
                "vwap": vwap,
                "supertrend": st_vals[idx] if idx < len(st_vals) else None,
                "supertrend_dir": st_dirs[idx] if idx < len(st_dirs) else None,
                "sar": sar_vals[idx] if idx < len(sar_vals) else None,
                "sar_is_long": sar_longs[idx] if idx < len(sar_longs) else None,
                "bb_upper": float(snap.bollinger_upper) if snap and snap.bollinger_upper is not None else None,
                "bb_middle": float(snap.bollinger_middle) if snap and snap.bollinger_middle is not None else None,
                "bb_lower": float(snap.bollinger_lower) if snap and snap.bollinger_lower is not None else None,
                "support": float(snap.support_level) if snap and snap.support_level is not None else None,
                "resistance": float(snap.resistance_level) if snap and snap.resistance_level is not None else None,
                "rsi14": float(snap.rsi_14) if snap and snap.rsi_14 is not None else None,
                "stoch_k": float(snap.stoch_rsi_k) if snap and snap.stoch_rsi_k is not None else None,
                "stoch_d": float(snap.stoch_rsi_d) if snap and snap.stoch_rsi_d is not None else None,
                "atr14": float(snap.atr_14) if snap and snap.atr_14 is not None else None,
                "macd_line": float(snap.macd_line) if snap and snap.macd_line is not None else None,
                "macd_signal": float(snap.macd_signal) if snap and snap.macd_signal is not None else None,
                "macd_hist": float(snap.macd_histogram) if snap and snap.macd_histogram is not None else None,
            }
            data.append(item)

        # Compute multi-factor levels overlay for chart visual annotations
        tech_snap = (
            TechnicalIndicatorSnapshot.objects.filter(listing=listing)
            .order_by("-timestamp")
            .first()
        )
        fund_snap = (
            FundamentalSnapshot.objects.filter(instrument=listing.instrument)
            .order_by("-calculated_at")
            .first()
        )
        rec = RecommendationEvaluator.evaluate(
            listing=listing,
            technical=tech_snap,
            fundamental=fund_snap,
        )
        latest_quote = listing.quotes.first()
        levels = {
            "entry_price": float(latest_quote.price) if latest_quote else None,
            "stop_loss": rec["new_investor"]["stop_loss_value"],
            "target_1": rec["new_investor"]["target_1_value"],
            "target_2": rec["new_investor"]["target_2_value"],
            "status": rec["new_investor"]["status"],
            "confluence_score": rec["new_investor"]["confluence_score"],
        }

        # Corporate Action Markers removed per user request for clean price chart
        markers = []

        return JsonResponse({
            "symbol": listing.symbol,
            "exchange": listing.exchange.code,
            "candles": data,
            "levels": levels,
            "fibonacci": fib_levels,
            "markers": markers,
        })


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


class StockLogoProxyView(View):
    """
    High-performance vector logo proxy endpoint.
    Retrieves and caches SVG logos from Shareperks and vector CDNs with automatic offline monogram fallback.
    Sets aggressive browser cache headers (7 days) for instant subsequent renders.
    """
    def get(self, request, symbol: str, *args, **kwargs):
        content, content_type = CompanyLogoService.get_logo(symbol)
        response = HttpResponse(content, content_type=content_type)
        response["Cache-Control"] = "public, max-age=604800, stale-while-revalidate=86400"
        return response


class StockQuotePartialView(View):
    """
    Dedicated lightweight endpoint for 15-second background auto-refresh of live market price.
    Renders only the quote ticker banner to avoid reloading charts, indicators, or full page.
    """
    def get(self, request, symbol: str, *args, **kwargs):
        symbol = symbol.upper()
        listing = (
            ExchangeListing.objects.filter(symbol=symbol, is_tradeable=True)
            .select_related("instrument", "exchange")
            .first()
        )
        if not listing:
            from services.market_data.auto_ingest import AutoIngestionService
            listing = AutoIngestionService.get_or_create_listing(symbol)

        if not listing:
            raise Http404(f"Listing '{symbol}' not found.")

        from services.calendar.exchange_calendar import ExchangeCalendar
        is_market_open = ExchangeCalendar.is_market_open()

        try:
            quote = MarketDataService.get_quote(listing, force_refresh=True)
        except Exception as e:
            logger.warning("Could not fetch fresh quote for %s: %s", symbol, e)
            quote = None
        if not quote:
            quote = MarketQuote.objects.filter(listing=listing).order_by("-retrieved_at").first()

        context = {
            "listing": listing,
            "quote": quote,
            "is_market_open": is_market_open,
        }
        from django.template.loader import render_to_string
        return HttpResponse(
            render_to_string("stocks/partials/stock_quote_partial.html", context, request=request)
        )


class StockShadowRunView(View):
    """
    On-demand single-stock shadow evaluation trigger.
    Evaluates candidate setups and matures pending horizons for the requested stock.
    Returns the updated stocks/partials/stock_shadow_pane_partial.html partial for HTMX.
    """
    def post(self, request, symbol: str, *args, **kwargs):
        symbol = symbol.upper()
        listing = get_object_or_404(
            ExchangeListing.objects.select_related("instrument", "exchange"),
            symbol=symbol,
            is_tradeable=True,
            is_primary=True,
        )

        service = ShadowEvaluationService()
        message = ""
        try:
            raw_candles = list(
                HistoricalCandle.objects.filter(listing=listing)
                .order_by("timestamp")
            )
            # Deduplicate by session date keeping the most recent candle for that session
            candles_by_date = {}
            for c in raw_candles:
                candles_by_date[c.timestamp.date()] = c
            candles = [candles_by_date[d] for d in sorted(candles_by_date.keys())]

            if len(candles) >= 20:
                df_records = [{
                    "session_date": str(c.timestamp.date()),
                    "close_adj": float(c.close),
                    "high_adj": float(c.high),
                    "low_adj": float(c.low),
                    "open_adj": float(c.open),
                    "volume_adj": float(c.volume),
                } for c in candles]
                df_candles = pd.DataFrame(df_records)
                fp = FeaturePipeline(warmup_sessions=min(20, len(candles) - 1))
                df_feat = fp.compute_stock_features(df_candles)

                candidates = []
                for _, row in df_feat.iterrows():
                    d = row.to_dict()
                    d["symbol"] = listing.symbol
                    p_sma = d.get("price_to_sma200")
                    rsi = d.get("rsi_14")
                    stoch_k = d.get("stoch_rsi_k")
                    if p_sma is not None and rsi is not None and stoch_k is not None:
                        if p_sma > 0.0 and 35.0 <= rsi <= 50.0 and stoch_k < 25.0:
                            candidates.append(d)

                recorded = 0
                if candidates:
                    df_c = pd.DataFrame(candidates)
                    records = service.record_session_candidates(
                        df_c,
                        source_provider="AUTHENTIC_EOD",
                        capture_mode=ShadowCaptureMode.FORWARD_CAPTURED,
                        force=True,
                    )
                    recorded = len(records)

                price_df = pd.DataFrame([{
                    "symbol": listing.symbol,
                    "session_date": str(c.timestamp.date()),
                    "open_adj": float(c.open),
                    "close_adj": float(c.close),
                    "open_raw": float(c.open),
                    "close_raw": float(c.close),
                } for c in candles])
                matured = service.mature_pending_evaluations(price_df)

                if recorded > 0 or matured > 0:
                    message = f"Shadow evaluation completed: {recorded} new setup(s) logged, {matured} horizon(s) matured."
                else:
                    message = f"Shadow evaluation checked {len(candles)} sessions: 0 setups met the pullback criteria (RSI 35–50 above SMA-200)."
            else:
                message = f"Insufficient session candles ({len(candles)} < 20) to compute shadow indicators."
        except Exception as e:
            logger.exception("Error running on-demand shadow evaluation for %s: %s", symbol, e)
            message = f"Evaluation executed with notice: {e}"

        shadow_records = list(
            MLShadowEvaluationRecord.objects.filter(listing=listing)
            .order_by("-session_date")[:10]
        )
        total_count = MLShadowEvaluationRecord.objects.filter(listing=listing).count()

        context = {
            "listing": listing,
            "shadow_records": shadow_records,
            "shadow_count": total_count,
            "execution_message": message,
        }
        return render(request, "stocks/partials/stock_shadow_pane_partial.html", context)


class StockSyncEODView(View):
    """
    On-demand single-stock EOD market data synchronization.
    Fetches the latest completed daily candles from exchange providers (YAHOO / JUGAAD)
    up to the latest trading session, upserts them with provenance tracking,
    and refreshes the stock detail view.
    """
    def post(self, request, symbol: str, *args, **kwargs):
        symbol = symbol.upper()
        listing = get_object_or_404(
            ExchangeListing.objects.select_related("instrument", "exchange"),
            symbol=symbol,
            is_tradeable=True,
            is_primary=True,
        )

        from datetime import datetime, timedelta
        from services.calendar.exchange_calendar import ExchangeCalendar
        from services.market_data.historical_pipeline import HistoricalDataIngestionPipeline

        now_ist = datetime.now(ExchangeCalendar.IST)
        latest_trading_day = (
            now_ist.date()
            if now_ist.time() >= ExchangeCalendar.MARKET_CLOSE_TIME
            else ExchangeCalendar.get_last_trading_day(now_ist.date())
        )

        latest_candle = HistoricalCandle.objects.filter(listing=listing).order_by("-timestamp").first()
        start_date = (
            latest_candle.timestamp.date() - timedelta(days=7)
            if latest_candle
            else (latest_trading_day - timedelta(days=365))
        )

        sync_msg = ""
        try:
            pipeline = HistoricalDataIngestionPipeline(
                provider_code="YAHOO",
                verify_against_calendar=True,
            )
            checkpoint = pipeline.ingest_listing_history(
                listing=listing,
                start_date=start_date,
                end_date=latest_trading_day,
                interval="1d",
            )
            if checkpoint.status == "SUCCESS":
                sync_msg = f"Synced {checkpoint.total_candles_ingested} candle(s) through {checkpoint.last_ingested_date or latest_trading_day}."
            else:
                sync_msg = f"Sync status: {checkpoint.error_message or 'Up to date'}"
        except Exception as e:
            logger.warning("YAHOO sync failed for %s: %s; trying JUGAAD fallback", symbol, e)
            try:
                pipeline_fb = HistoricalDataIngestionPipeline(
                    provider_code="JUGAAD",
                    verify_against_calendar=True,
                )
                checkpoint_fb = pipeline_fb.ingest_listing_history(
                    listing=listing,
                    start_date=start_date,
                    end_date=latest_trading_day,
                    interval="1d",
                )
                sync_msg = f"Synced via JUGAAD: {checkpoint_fb.total_candles_ingested} candle(s)."
            except Exception as exc:
                logger.error("All providers failed to sync EOD for %s: %s", symbol, exc)
                sync_msg = f"Sync notice: {e}"

        # If HTMX request, delegate to StockDetailView
        if request.headers.get("HX-Request") == "true" or getattr(request, "htmx", False):
            detail_view = StockDetailView()
            detail_view.setup(request, symbol=symbol, *args, **kwargs)
            detail_view.object = listing
            context = detail_view.get_context_data(object=listing)
            context["sync_message"] = sync_msg
            return render(request, "stocks/partials/stock_detail_partial.html", context)

        return redirect("stocks:stock_detail", symbol=symbol)


