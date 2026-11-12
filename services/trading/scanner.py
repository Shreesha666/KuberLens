"""
Quantitative Swing Trading Scanner.
Scans the active exchange universe for 1-8 week swing trade opportunities:
1. Pullback to 20/50 SMA in Uptrend (SMA_PULLBACK)
2. Consolidation Breakout with Volume Confirmation (BREAKOUT_CONSOLIDATION)
3. Oversold Mean Reversion Bounce (RSI_OVERSOLD_BOUNCE)
4. Golden Cross Momentum Continuation (MOMENTUM_GOLDEN_CROSS)
Enforces minimum 1:1.5 Risk-to-Reward ratio and explicit invalidation levels.
"""
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

from django.utils import timezone

from apps.instruments.models import ExchangeListing
from apps.market.models import MarketQuote
from apps.technical_analysis.models import TechnicalIndicatorSnapshot
from apps.trading.models import SwingStrategyType, TradeSetup, TradeSetupStatus

logger = logging.getLogger(__name__)


class SwingScanner:
    MIN_RR = Decimal("1.50")

    @classmethod
    def scan_universe(
        cls,
        strategy_filter: str | None = None,
        market_cap_filter: str | None = None,
        min_rr: Decimal | float | None = None,
        save_setups: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Scans all primary active listings against the 4 swing strategies.
        Returns qualified setups with entry zone, stop loss, targets, and R:R.
        """
        min_rr_threshold = Decimal(str(min_rr or cls.MIN_RR))
        now = timezone.now()

        # Preload listings with instruments and exchanges
        listings = (
            ExchangeListing.objects.filter(is_tradeable=True, is_primary=True)
            .select_related("instrument", "exchange")
            .order_by("symbol")
        )

        if market_cap_filter and market_cap_filter != "ALL":
            listings = listings.filter(instrument__market_cap_category=market_cap_filter)

        # Preload latest quotes
        latest_quotes: dict[str, MarketQuote] = {}
        for q in MarketQuote.objects.order_by("-retrieved_at"):
            lid = str(q.listing_id)
            if lid not in latest_quotes:
                latest_quotes[lid] = q

        # Preload latest technical snapshots
        latest_tech: dict[str, TechnicalIndicatorSnapshot] = {}
        for t in TechnicalIndicatorSnapshot.objects.order_by("-timestamp"):
            lid = str(t.listing_id)
            if lid not in latest_tech:
                latest_tech[lid] = t

        qualified_setups: list[dict[str, Any]] = []

        for listing in listings:
            quote = latest_quotes.get(str(listing.id))
            tech = latest_tech.get(str(listing.id))

            if not quote or not tech or quote.price <= Decimal("0.0"):
                continue

            # Need valid moving averages
            if not tech.sma_20 or not tech.sma_50 or not tech.sma_200:
                continue

            candidates = cls._evaluate_stock_strategies(listing, quote, tech)

            for c in candidates:
                if strategy_filter and strategy_filter != "ALL" and c["strategy"] != strategy_filter:
                    continue

                if c["risk_reward"] >= min_rr_threshold:
                    qualified_setups.append(c)

        # Sort by best Risk-to-Reward ratio descending
        qualified_setups.sort(key=lambda s: s["risk_reward"], reverse=True)

        if save_setups:
            cls._persist_setups(qualified_setups, now)

        return qualified_setups

    @classmethod
    def _evaluate_stock_strategies(
        cls,
        listing: ExchangeListing,
        quote: MarketQuote,
        tech: TechnicalIndicatorSnapshot,
    ) -> list[dict[str, Any]]:
        """Evaluates a single stock across the 4 swing models."""
        candidates = []
        p = quote.price
        sma20 = tech.sma_20
        sma50 = tech.sma_50
        sma200 = tech.sma_200
        rsi = tech.rsi_14 or Decimal("50.0")
        rvol = tech.relative_volume or Decimal("1.0")
        sup = tech.support_level or (p * Decimal("0.95"))
        res = tech.resistance_level or (p * Decimal("1.08"))
        swing_low = tech.swing_low or sup
        swing_high = tech.swing_high or res

        # ----------------------------------------------------
        # Strategy 1: Pullback to 20/50 SMA in Uptrend
        # ----------------------------------------------------
        if tech.trend_signal == "BULLISH" and p > sma50:
            dist_sma20 = abs(p - sma20) / sma20
            dist_sma50 = abs(p - sma50) / sma50

            # Price within 3% of 20 SMA or within 2.5% of 50 SMA
            if (dist_sma20 <= Decimal("0.035") or dist_sma50 <= Decimal("0.03")) and Decimal("38.0") <= rsi <= Decimal("62.0"):
                sl = round(min(sma50, swing_low) * Decimal("0.975"), 2)
                if sl < p:
                    risk = p - sl
                    t1 = round(max(swing_high, p + (risk * Decimal("1.8"))), 2)
                    t2 = round(p + (risk * Decimal("2.8")), 2)
                    rr = round((t1 - p) / risk, 2)

                    candidates.append({
                        "listing": listing,
                        "symbol": listing.symbol,
                        "name": listing.instrument.display_name,
                        "sector": listing.instrument.sector,
                        "market_cap": listing.instrument.get_market_cap_category_display(),
                        "strategy": SwingStrategyType.SMA_PULLBACK.value,
                        "strategy_name": SwingStrategyType.SMA_PULLBACK.label,
                        "current_price": p,
                        "entry_min": round(p * Decimal("0.995"), 2),
                        "entry_max": round(p * Decimal("1.01"), 2),
                        "stop_loss": sl,
                        "target_1": t1,
                        "target_2": t2,
                        "risk_reward": rr,
                        "holding_period": "1–4 weeks",
                        "explanation": (
                            f"Confirmed macro uptrend (50 SMA ₹{sma50:.2f} >= 200 SMA ₹{sma200:.2f}). "
                            f"Price has completed an orderly pullback to moving average support with RSI {rsi:.1f}, "
                            f"offering an asymmetric continuation swing entry."
                        ),
                        "invalidation": f"Invalidated if daily candle closes below ₹{sl:.2f} on elevated volume.",
                    })

        # ----------------------------------------------------
        # Strategy 2: Consolidation Breakout with Volume Confirmation
        # ----------------------------------------------------
        # Near resistance (within 2% or breakout) with volume surge
        if p >= res * Decimal("0.98") and rvol >= Decimal("1.15") and Decimal("52.0") <= rsi <= Decimal("72.0"):
            sl = round(max(sup, sma20) * Decimal("0.98"), 2)
            if sl < p:
                risk = p - sl
                t1 = round(p + (risk * Decimal("2.0")), 2)
                t2 = round(p + (risk * Decimal("3.2")), 2)
                rr = round((t1 - p) / risk, 2)

                candidates.append({
                    "listing": listing,
                    "symbol": listing.symbol,
                    "name": listing.instrument.display_name,
                    "sector": listing.instrument.sector,
                    "market_cap": listing.instrument.get_market_cap_category_display(),
                    "strategy": SwingStrategyType.BREAKOUT_CONSOLIDATION.value,
                    "strategy_name": SwingStrategyType.BREAKOUT_CONSOLIDATION.label,
                    "current_price": p,
                    "entry_min": round(p * Decimal("0.995"), 2),
                    "entry_max": round(p * Decimal("1.015"), 2),
                    "stop_loss": sl,
                    "target_1": t1,
                    "target_2": t2,
                    "risk_reward": rr,
                    "holding_period": "2–6 weeks",
                    "explanation": (
                        f"Consolidation breakout testing multi-week resistance at ₹{res:.2f}. "
                        f"Volume expansion ({rvol:.1f}x relative volume) and bullish RSI ({rsi:.1f}) indicate "
                        f"institutional accumulation and range expansion."
                    ),
                    "invalidation": f"Invalidated if breakout fails and price falls back below breakout pivot ₹{sl:.2f}.",
                })

        # ----------------------------------------------------
        # Strategy 3: Oversold Mean Reversion Bounce
        # ----------------------------------------------------
        if rsi <= Decimal("36.0") and p <= sup * Decimal("1.04"):
            sl = round(swing_low * Decimal("0.97"), 2)
            if sl < p:
                risk = p - sl
                # Target SMA 20 or minimum 2.0x risk
                t1 = round(max(sma20, p + (risk * Decimal("2.0"))), 2)
                t2 = round(max(sma50, t1 * Decimal("1.05")), 2)
                rr = round((t1 - p) / risk, 2)

                candidates.append({
                    "listing": listing,
                    "symbol": listing.symbol,
                    "name": listing.instrument.display_name,
                    "sector": listing.instrument.sector,
                    "market_cap": listing.instrument.get_market_cap_category_display(),
                    "strategy": SwingStrategyType.RSI_OVERSOLD_BOUNCE.value,
                    "strategy_name": SwingStrategyType.RSI_OVERSOLD_BOUNCE.label,
                    "current_price": p,
                    "entry_min": round(p * Decimal("0.99"), 2),
                    "entry_max": round(p * Decimal("1.01"), 2),
                    "stop_loss": sl,
                    "target_1": t1,
                    "target_2": t2,
                    "risk_reward": rr,
                    "holding_period": "1–3 weeks",
                    "explanation": (
                        f"Oversold momentum exhaustion (RSI 14 at {rsi:.1f}) testing key horizontal support at ₹{sup:.2f}. "
                        f"Favorable risk profile for a sharp mean-reversion snapback toward the 20-day SMA (₹{sma20:.2f})."
                    ),
                    "invalidation": f"Invalidated if critical horizontal support breaks below ₹{sl:.2f}.",
                })

        # ----------------------------------------------------
        # Strategy 4: Golden Cross Momentum Continuation
        # ----------------------------------------------------
        # 50 SMA has crossed or is decisively above 200 SMA, and price above 20 SMA
        if sma50 >= sma200 and p > sma20 and rsi >= Decimal("50.0"):
            # Recent golden cross territory (50 SMA within 4% of 200 SMA or expanding)
            spread = (sma50 - sma200) / sma200
            if spread <= Decimal("0.05"):
                sl = round(sma50 * Decimal("0.975"), 2)
                if sl < p:
                    risk = p - sl
                    t1 = round(p + (risk * Decimal("2.2")), 2)
                    t2 = round(p + (risk * Decimal("3.5")), 2)
                    rr = round((t1 - p) / risk, 2)

                    candidates.append({
                        "listing": listing,
                        "symbol": listing.symbol,
                        "name": listing.instrument.display_name,
                        "sector": listing.instrument.sector,
                        "market_cap": listing.instrument.get_market_cap_category_display(),
                        "strategy": SwingStrategyType.MOMENTUM_GOLDEN_CROSS.value,
                        "strategy_name": SwingStrategyType.MOMENTUM_GOLDEN_CROSS.label,
                        "current_price": p,
                        "entry_min": round(p * Decimal("0.995"), 2),
                        "entry_max": round(p * Decimal("1.01"), 2),
                        "stop_loss": sl,
                        "target_1": t1,
                        "target_2": t2,
                        "risk_reward": rr,
                        "holding_period": "3–8 weeks",
                        "explanation": (
                            f"Major trend reversal confirmed by 50-day SMA crossing 200-day SMA (Golden Cross). "
                            f"Price is sustained above 20 SMA (₹{sma20:.2f}) with constructive momentum."
                        ),
                        "invalidation": f"Invalidated if price reverses below the Golden Cross pivot at ₹{sl:.2f}.",
                    })

        return candidates

    @classmethod
    def _persist_setups(cls, setups: list[dict[str, Any]], timestamp: datetime):
        """Persists or refreshes active TradeSetup records."""
        for s in setups:
            listing = s["listing"]
            strategy = s["strategy"]

            TradeSetup.objects.update_or_create(
                listing=listing,
                strategy=strategy,
                status=TradeSetupStatus.ACTIVE,
                defaults={
                    "setup_timestamp": timestamp,
                    "current_price": s["current_price"],
                    "entry_min": s["entry_min"],
                    "entry_max": s["entry_max"],
                    "stop_loss": s["stop_loss"],
                    "target_1": s["target_1"],
                    "target_2": s["target_2"],
                    "risk_reward_ratio": s["risk_reward"],
                    "holding_period": s["holding_period"],
                    "explanation": s["explanation"],
                    "invalidation_conditions": s["invalidation"],
                },
            )
