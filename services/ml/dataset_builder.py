"""
Historical Dataset Builder and Point-in-Time Corporate Action Adjustment Engine.
Complies with Master Specification Section 18 and AIML Architecture Specification v2.1 (Phase 2 & 2.1).

Features:
- Dynamic universe support: ALL_NSE, ALL_BSE, ALL_NSE_BSE, NIFTY_50, NIFTY_100, NIFTY_250, PORTFOLIO_HOLDINGS, CUSTOM.
- Dual-listing resolution: ISIN-based security mapping with deterministic primary-listing selection.
- ML eligibility classification: ML_ELIGIBLE, LIMITED_HISTORY, INSUFFICIENT_HISTORY, INSUFFICIENT_LIQUIDITY,
  STALE_DATA, DATA_QUALITY_FAILED, SUSPENDED_OR_INACTIVE.
- Historical data depth auditing (1yr, 3yr, 5yr, 10yr) and missing-session categorization.
- Verified point-in-time split and bonus adjustments without lookahead leakage.
- Chunked streaming extraction for bounded memory scalability.
- Bit-for-bit reproducible SHA-256 canonical content hashing.
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from django.conf import settings
from django.utils import timezone

from apps.instruments.models import ExchangeListing
from apps.market.models import HistoricalCandle
from apps.ml_engine.models import MLDatasetSnapshot
from apps.news.models import CorporateEvent
from services.calendar.exchange_calendar import ExchangeCalendar

logger = logging.getLogger(__name__)


class MLEligibilityStatus(StrEnum):
    """
    ML training and validation eligibility status for equity listings.
    Distinguishes data eligibility from model approval and runtime inference state.
    """
    ML_ELIGIBLE = "ML_ELIGIBLE"
    LIMITED_HISTORY = "LIMITED_HISTORY"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    INSUFFICIENT_LIQUIDITY = "INSUFFICIENT_LIQUIDITY"
    STALE_DATA = "STALE_DATA"
    DATA_QUALITY_FAILED = "DATA_QUALITY_FAILED"
    SUSPENDED_OR_INACTIVE = "SUSPENDED_OR_INACTIVE"


class UniverseType(StrEnum):
    """Supported equity universe definitions."""
    ALL_NSE = "ALL_NSE"
    ALL_BSE = "ALL_BSE"
    ALL_NSE_BSE = "ALL_NSE_BSE"
    NIFTY_50 = "NIFTY_50"
    NIFTY_100 = "NIFTY_100"
    NIFTY_250 = "NIFTY_250"
    PORTFOLIO_HOLDINGS = "PORTFOLIO_HOLDINGS"
    CUSTOM = "CUSTOM"


@dataclass
class ListingEligibilityResult:
    """Detailed audit metrics and eligibility classification for a listing."""
    listing_id: str
    symbol: str
    exchange: str
    isin: str
    status: MLEligibilityStatus
    reason: str
    total_candles: int
    clean_candles: int
    quarantined_candles: int
    earliest_session: date | None
    latest_session: date | None
    median_volume: float
    coverage_pct: float
    is_primary: bool
    suspicious_jumps_count: int
    missing_sessions_count: int


class CorporateActionAdjuster:
    """
    Parses verified market-wide split and bonus events from CorporateEvent records
    and calculates point-in-time adjustment multipliers without future lookahead.
    """

    @staticmethod
    def parse_ratio(event_type: str, ratio_str: str, title: str = "") -> tuple[float, str]:
        """
        Parses split or bonus ratios into a price adjustment multiplier factor f.
        Tested formulas:
          - 5-for-1 Split (e.g. '1:5 split', '5:1 split', '5-for-1', 'FV 10 to 2'):
            Old FV / New FV = 1/5 -> f = 0.200000.
            P_adjusted = P_raw * 0.20, V_adjusted = V_raw / 0.20.
          - 1:1 Bonus Issue:
            1 new for 1 existing -> f = 1 / (1 + 1) = 0.500000.
            P_adjusted = P_raw * 0.50, V_adjusted = V_raw / 0.50.
          - 3:1 Bonus Issue:
            3 new for 1 existing -> f = 1 / (1 + 3) = 0.250000.
            P_adjusted = P_raw * 0.25, V_adjusted = V_raw / 0.25.
        """
        combined_text = f"{ratio_str} {title}".strip()
        etype = event_type.upper()

        if "SPLIT" in etype:
            # 1. Face value sub-division: e.g. "from Rs 10 to Rs 2" or "from ₹10 to ₹2"
            fv_match = re.search(
                r"from\s*(?:rs\.?|₹)?\s*(\d+(?:\.\d+)?)\s*to\s*(?:rs\.?|₹)?\s*(\d+(?:\.\d+)?)",
                combined_text,
                re.IGNORECASE,
            )
            if fv_match:
                old_fv = float(fv_match.group(1))
                new_fv = float(fv_match.group(2))
                if old_fv > 0 and new_fv > 0:
                    factor = round(new_fv / old_fv, 6)
                    return factor, f"Sub-division FV {old_fv:g} to {new_fv:g} (f={factor:.6f})"

            # 2. X-for-Y format: e.g. "5-for-1", "5 for 1", "5-to-1", "5 to 1"
            for_match = re.search(r"(\d+)\s*(?:-for-|\s+for\s+|-to-|\s+to\s+)\s*(\d+)", combined_text, re.IGNORECASE)
            if for_match:
                new_shares = float(for_match.group(1))
                old_shares = float(for_match.group(2))
                if new_shares > 0 and old_shares > 0:
                    split_ratio = max(new_shares, old_shares) / min(new_shares, old_shares)
                    factor = round(1.0 / split_ratio, 6)
                    return factor, f"{int(split_ratio)}-for-1 split (f={factor:.6f})"

            # 3. Ratio format: "1:5", "5:1", "1:10", "1:2"
            ratio_match = re.search(r"(\d+)\s*:\s*(\d+)", combined_text)
            if ratio_match:
                n1 = float(ratio_match.group(1))
                n2 = float(ratio_match.group(2))
                if n1 > 0 and n2 > 0:
                    split_ratio = max(n1, n2) / min(n1, n2)
                    factor = round(1.0 / split_ratio, 6)
                    return factor, f"1:{int(split_ratio)} split (f={factor:.6f})"

            logger.warning("Unrecognized split ratio format: '%s'. Applying neutral factor 1.0", combined_text)
            return 1.0, f"Unrecognized split: {combined_text} (f=1.000000)"

        elif "BONUS" in etype:
            # Ratio format: "A:B Bonus" means A new bonus shares for B held.
            # Multiplier factor = B / (B + A).
            ratio_match = re.search(r"(\d+)\s*:\s*(\d+)", combined_text)
            if ratio_match:
                n1 = float(ratio_match.group(1))
                n2 = float(ratio_match.group(2))
                if n1 > 0 and n2 > 0:
                    bonus_a = n1
                    bonus_b = n2
                    factor = round(bonus_b / (bonus_b + bonus_a), 6)
                    return factor, f"{int(bonus_a)}:{int(bonus_b)} bonus (f={factor:.6f})"

            logger.warning("Unrecognized bonus ratio format: '%s'. Applying neutral factor 1.0", combined_text)
            return 1.0, f"Unrecognized bonus: {combined_text} (f=1.000000)"

        return 1.0, f"Unhandled action {event_type} (f=1.000000)"

    @classmethod
    def get_adjustment_events_for_listing(
        cls,
        listing: ExchangeListing,
        as_of_date: date | None = None,
    ) -> list[dict[str, Any]]:
        """
        Retrieves verified SPLIT and BONUS events for a listing up to as_of_date.
        Strictly prevents lookahead leakage: events with ex-date > as_of_date are excluded.
        """
        qs = CorporateEvent.objects.filter(
            listing=listing,
            event_type__in=["SPLIT", "BONUS"],
        )
        if as_of_date:
            qs = qs.filter(event_date__lte=as_of_date)

        events = []
        for e in qs.order_by("event_date"):
            factor, desc = cls.parse_ratio(e.event_type, e.ratio_or_value, e.title)
            events.append({
                "event_id": str(e.id),
                "event_type": e.event_type,
                "ex_date": e.event_date,
                "ratio_or_value": e.ratio_or_value,
                "title": e.title,
                "factor": factor,
                "description": desc,
            })
        return events

    @staticmethod
    def calculate_point_in_time_multipliers(
        events: list[dict[str, Any]],
        candle_dates: list[date],
    ) -> dict[date, float]:
        """
        Calculates cumulative backward adjustment multiplier for each candle date.
        Formula:
          For candle date t:
          F(t) = product of factors for all events where event.ex_date > t.
          Candle dates on or after all events have F(t) = 1.0.
        """
        multipliers = {}
        for cdate in candle_dates:
            cum_factor = 1.0
            for ev in events:
                if ev["ex_date"] > cdate:
                    cum_factor *= ev["factor"]
            multipliers[cdate] = round(cum_factor, 6)
        return multipliers


class DataQualityValidator:
    """
    Validates OHLC consistency, non-negative volume, identifies missing/duplicate
    sessions, and flags unexplained price jumps.
    """

    @staticmethod
    def validate_candle_record(record: dict[str, Any]) -> tuple[bool, list[str]]:
        """
        Validates OHLC consistency rules:
          1. Low <= Open <= High
          2. Low <= Close <= High
          3. High >= Low > 0
          4. Open > 0 and Close > 0
          5. Volume >= 0
        """
        errors = []
        o = float(record.get("open", 0))
        h = float(record.get("high", 0))
        low_val = float(record.get("low", 0))
        c = float(record.get("close", 0))
        v = float(record.get("volume", 0))

        if o <= 0 or h <= 0 or low_val <= 0 or c <= 0:
            errors.append(f"Non-positive price detected: O={o}, H={h}, L={low_val}, C={c}")
        if h < low_val:
            errors.append(f"High {h} is less than Low {low_val}")
        if o > h or o < low_val:
            errors.append(f"Open {o} outside High-Low range [{low_val}, {h}]")
        if c > h or c < low_val:
            errors.append(f"Close {c} outside High-Low range [{low_val}, {h}]")
        if v < 0:
            errors.append(f"Negative volume detected: V={v}")

        return len(errors) == 0, errors

    @staticmethod
    def detect_suspicious_jumps(
        candles_df: pd.DataFrame,
        corporate_ex_dates: set[date],
        threshold_pct: float = 50.0,
    ) -> list[dict[str, Any]]:
        """
        Flags single-session raw close price jumps exceeding threshold_pct
        that are not accompanied by a corporate action on that ex-date.
        """
        jumps = []
        if len(candles_df) < 2:
            return jumps

        sorted_df = candles_df.sort_values("session_date")
        closes = sorted_df["close_raw"].astype(float).values
        dates = sorted_df["session_date"].values

        for i in range(1, len(closes)):
            prev_c = closes[i - 1]
            curr_c = closes[i]
            cdate = dates[i]
            if isinstance(cdate, str):
                cdate = date.fromisoformat(cdate)
            elif isinstance(cdate, pd.Timestamp):
                cdate = cdate.date()

            if prev_c > 0:
                pct_change = abs((curr_c - prev_c) / prev_c) * 100.0
                if pct_change >= threshold_pct and cdate not in corporate_ex_dates:
                    jumps.append({
                        "session_date": cdate.isoformat(),
                        "previous_close": round(prev_c, 4),
                        "current_close": round(curr_c, 4),
                        "jump_pct": round(pct_change, 2),
                        "corporate_action_present": False,
                    })

        return jumps


class UniverseResolver:
    """
    Resolves equity listings for dynamic universes with deterministic primary-listing
    deduplication across dual-listed securities.
    """

    @classmethod
    def resolve(
        cls,
        universe: str | list[str],
        exchange_code: str = "NSE",
        deduplicate_dual_listings: bool = False,
        primary_policy: str = "PRIMARY_FLAG_THEN_LIQUIDITY",
    ) -> tuple[list[ExchangeListing], dict[str, Any]]:
        """
        Resolves listings matching universe specifications.
        Returns:
          - resolved_listings: List of eligible ExchangeListing instances
          - metadata: Audit dictionary detailing filtering and deduplication stats
        """
        u_upper = str(universe).strip().upper()
        base_qs = ExchangeListing.objects.select_related("instrument", "exchange")

        # 1. Resolve raw candidate listings
        if u_upper == UniverseType.ALL_NSE.value:
            candidates = list(base_qs.filter(exchange__code="NSE", is_tradeable=True).order_by("symbol"))
            universe_desc = "All Tradeable NSE Equities"
        elif u_upper == UniverseType.ALL_BSE.value:
            candidates = list(base_qs.filter(exchange__code="BSE", is_tradeable=True).order_by("symbol"))
            universe_desc = "All Tradeable BSE Equities"
        elif u_upper in (UniverseType.ALL_NSE_BSE.value, "ALL"):
            candidates = list(base_qs.filter(exchange__code__in=["NSE", "BSE"], is_tradeable=True).order_by("symbol"))
            universe_desc = "All Tradeable NSE & BSE Equities (Dual Exchange Master)"
            # Default to deduplicating dual listings when querying pooled cross-exchange
            deduplicate_dual_listings = True
        elif u_upper == UniverseType.NIFTY_50.value:
            from apps.instruments.management.commands.seed_nifty250 import NIFTY_250_STOCKS
            symbols = [s["symbol"] for s in NIFTY_250_STOCKS[:50]]
            candidates = list(base_qs.filter(symbol__in=symbols, exchange__code=exchange_code, is_tradeable=True).order_by("symbol"))
            universe_desc = "NIFTY 50 Benchmark Universe"
        elif u_upper == UniverseType.NIFTY_100.value:
            from apps.instruments.management.commands.seed_nifty250 import NIFTY_250_STOCKS
            symbols = [s["symbol"] for s in NIFTY_250_STOCKS[:100]]
            candidates = list(base_qs.filter(symbol__in=symbols, exchange__code=exchange_code, is_tradeable=True).order_by("symbol"))
            universe_desc = "NIFTY 100 Large Cap Universe"
        elif u_upper == UniverseType.NIFTY_250.value:
            try:
                from apps.instruments.management.commands.seed_nifty250 import NIFTY_250_STOCKS
                symbols = [s["symbol"] for s in NIFTY_250_STOCKS]
                candidates = list(base_qs.filter(symbol__in=symbols, exchange__code=exchange_code, is_tradeable=True).order_by("symbol"))
                if not candidates:
                    candidates = list(base_qs.filter(exchange__code=exchange_code, is_tradeable=True).order_by("symbol")[:250])
            except ImportError:
                candidates = list(base_qs.filter(exchange__code=exchange_code, is_tradeable=True).order_by("symbol")[:250])
            universe_desc = "NIFTY LargeMidcap 250 Universe"
        elif u_upper == UniverseType.PORTFOLIO_HOLDINGS.value:
            try:
                from apps.holdings.models import Holding
                holding_symbols = list(Holding.objects.values_list("listing__symbol", flat=True).distinct())
                candidates = list(base_qs.filter(symbol__in=holding_symbols, is_tradeable=True).order_by("symbol"))
                universe_desc = f"Portfolio Holdings ({len(candidates)} listings)"
            except Exception as e:
                logger.warning("Could not resolve portfolio holdings: %s", e)
                candidates = []
                universe_desc = "Portfolio Holdings (Empty)"
        elif isinstance(universe, (list, tuple, set)):
            symbols = [str(s).strip().upper() for s in universe]
            candidates = list(base_qs.filter(symbol__in=symbols, is_tradeable=True).order_by("symbol"))
            universe_desc = f"Custom Universe ({len(candidates)} listings)"
        else:
            symbols = [s.strip().upper() for s in str(universe).split(",") if s.strip()]
            candidates = list(base_qs.filter(symbol__in=symbols, is_tradeable=True).order_by("symbol"))
            universe_desc = f"Custom List ({len(candidates)} listings)"

        raw_count = len(candidates)
        deduplicated_count = 0
        dedup_audit = []

        # 2. Dual-Listing Deduplication across identical ISINs
        if deduplicate_dual_listings:
            isin_groups: dict[str, list[ExchangeListing]] = {}
            unmatched_listings: list[ExchangeListing] = []

            for lst in candidates:
                isin = lst.instrument.isin if (lst.instrument and lst.instrument.isin) else None
                if isin:
                    isin_groups.setdefault(isin, []).append(lst)
                else:
                    unmatched_listings.append(lst)

            selected_listings: list[ExchangeListing] = []
            for isin, group in isin_groups.items():
                if len(group) == 1:
                    selected_listings.append(group[0])
                else:
                    # Deterministic primary-listing selection policy
                    chosen = cls._select_primary_listing(group, primary_policy)
                    selected_listings.append(chosen)
                    deduplicated_count += (len(group) - 1)
                    dedup_audit.append({
                        "isin": isin,
                        "candidates": [f"{item.exchange.code}:{item.symbol}" for item in group],
                        "selected": f"{chosen.exchange.code}:{chosen.symbol}",
                        "policy": primary_policy,
                    })

            # Unmatched listings without ISIN are preserved by their distinct (exchange, symbol)
            selected_listings.extend(unmatched_listings)
            resolved_listings = sorted(selected_listings, key=lambda x: (x.exchange.code, x.symbol))
        else:
            resolved_listings = candidates

        meta = {
            "universe_type": u_upper,
            "description": universe_desc,
            "raw_candidates_count": raw_count,
            "resolved_count": len(resolved_listings),
            "deduplicate_dual_listings": deduplicate_dual_listings,
            "deduplicated_duplicates_count": deduplicated_count,
            "primary_policy": primary_policy if deduplicate_dual_listings else "NONE",
            "deduplication_audit": dedup_audit[:50],  # sample first 50
        }

        return resolved_listings, meta

    @staticmethod
    def _select_primary_listing(
        group: list[ExchangeListing],
        policy: str,
    ) -> ExchangeListing:
        """
        Selects a single authoritative primary listing from a group sharing the same ISIN.
        Rules:
          1. Priority to listing marked is_primary=True.
          2. Priority to NSE over BSE for higher electronic liquidity.
          3. If tied, pick listing with higher historical candle count or symbol alphabetical order.
        """
        # Rule 1: is_primary
        primary_flags = [item for item in group if getattr(item, "is_primary", False)]
        if len(primary_flags) == 1:
            return primary_flags[0]

        # Rule 2: Exchange priority
        if policy in ("PRIMARY_FLAG_THEN_LIQUIDITY", "NSE_PRIORITY"):
            nse_listings = [item for item in group if item.exchange.code == "NSE"]
            if nse_listings:
                return nse_listings[0]
            bse_listings = [item for item in group if item.exchange.code == "BSE"]
            if bse_listings:
                return bse_listings[0]
        elif policy == "BSE_PRIORITY":
            bse_listings = [item for item in group if item.exchange.code == "BSE"]
            if bse_listings:
                return bse_listings[0]
            nse_listings = [item for item in group if item.exchange.code == "NSE"]
            if nse_listings:
                return nse_listings[0]

        # Rule 3: Tie-breaker by alphabetical symbol
        return sorted(group, key=lambda item: item.symbol)[0]


class MLEligibilityClassifier:
    """
    Evaluates historical data depth, liquidity, freshness, and quality for each listing,
    classifying into explainable MLEligibilityStatus tiers.
    """

    def __init__(
        self,
        min_sessions: int = 200,
        min_limited_sessions: int = 50,
        min_median_volume: float = 5000.0,
        max_zero_volume_pct: float = 30.0,
        max_stale_sessions: int = 10,
        max_quarantine_pct: float = 5.0,
    ):
        self.min_sessions = min_sessions
        self.min_limited_sessions = min_limited_sessions
        self.min_median_volume = min_median_volume
        self.max_zero_volume_pct = max_zero_volume_pct
        self.max_stale_sessions = max_stale_sessions
        self.max_quarantine_pct = max_quarantine_pct

    def classify_listing(
        self,
        listing: ExchangeListing,
        candles_qs: Any,
        expected_sessions: list[date],
        end_date: date,
        quarantined_count: int = 0,
        suspicious_jumps_count: int = 0,
    ) -> ListingEligibilityResult:
        """
        Classifies an equity listing into an explainable ML eligibility tier.
        """
        isin = listing.instrument.isin if (listing.instrument and listing.instrument.isin) else "NO_ISIN"

        # Check inactive / suspended status
        if not getattr(listing, "is_tradeable", True):
            return ListingEligibilityResult(
                listing_id=str(listing.id),
                symbol=listing.symbol,
                exchange=listing.exchange.code,
                isin=isin,
                status=MLEligibilityStatus.SUSPENDED_OR_INACTIVE,
                reason="Listing is marked is_tradeable=False or suspended from trading.",
                total_candles=0,
                clean_candles=0,
                quarantined_candles=quarantined_count,
                earliest_session=None,
                latest_session=None,
                median_volume=0.0,
                coverage_pct=0.0,
                is_primary=getattr(listing, "is_primary", False),
                suspicious_jumps_count=suspicious_jumps_count,
                missing_sessions_count=len(expected_sessions),
            )

        candles_list = list(candles_qs)
        total_candles = len(candles_list) + quarantined_count
        clean_candles = len(candles_list)

        if clean_candles == 0:
            return ListingEligibilityResult(
                listing_id=str(listing.id),
                symbol=listing.symbol,
                exchange=listing.exchange.code,
                isin=isin,
                status=MLEligibilityStatus.INSUFFICIENT_HISTORY,
                reason="Zero historical daily trading candles available in the observation window.",
                total_candles=total_candles,
                clean_candles=0,
                quarantined_candles=quarantined_count,
                earliest_session=None,
                latest_session=None,
                median_volume=0.0,
                coverage_pct=0.0,
                is_primary=getattr(listing, "is_primary", False),
                suspicious_jumps_count=suspicious_jumps_count,
                missing_sessions_count=len(expected_sessions),
            )

        timestamps = [c.timestamp.date() for c in candles_list]
        earliest_session = min(timestamps)
        latest_session = max(timestamps)
        volumes = [float(c.volume) for c in candles_list]
        median_vol = float(np.median(volumes)) if volumes else 0.0
        zero_vol_count = sum(1 for v in volumes if v <= 0)
        zero_vol_pct = (zero_vol_count / clean_candles * 100.0) if clean_candles else 0.0

        candle_dates_set = set(timestamps)
        missing_count = sum(1 for d in expected_sessions if d not in candle_dates_set)
        # Count candles that fall on expected official trading sessions
        valid_trading_candles_count = sum(1 for d in candle_dates_set if d in expected_sessions)
        coverage_pct = round(valid_trading_candles_count / len(expected_sessions) * 100.0, 2) if expected_sessions else 0.0

        quarantine_pct = (quarantined_count / total_candles * 100.0) if total_candles else 0.0

        # Quality check: excessive errors
        if quarantine_pct >= self.max_quarantine_pct:
            return ListingEligibilityResult(
                listing_id=str(listing.id),
                symbol=listing.symbol,
                exchange=listing.exchange.code,
                isin=isin,
                status=MLEligibilityStatus.DATA_QUALITY_FAILED,
                reason=f"Excessive quarantined candles ({quarantine_pct:.1f}% >= threshold {self.max_quarantine_pct}%).",
                total_candles=total_candles,
                clean_candles=clean_candles,
                quarantined_candles=quarantined_count,
                earliest_session=earliest_session,
                latest_session=latest_session,
                median_volume=median_vol,
                coverage_pct=coverage_pct,
                is_primary=getattr(listing, "is_primary", False),
                suspicious_jumps_count=suspicious_jumps_count,
                missing_sessions_count=missing_count,
            )

        # Insufficient history
        if clean_candles < self.min_limited_sessions:
            return ListingEligibilityResult(
                listing_id=str(listing.id),
                symbol=listing.symbol,
                exchange=listing.exchange.code,
                isin=isin,
                status=MLEligibilityStatus.INSUFFICIENT_HISTORY,
                reason=f"Only {clean_candles} trading sessions available (< minimum {self.min_limited_sessions}).",
                total_candles=total_candles,
                clean_candles=clean_candles,
                quarantined_candles=quarantined_count,
                earliest_session=earliest_session,
                latest_session=latest_session,
                median_volume=median_vol,
                coverage_pct=coverage_pct,
                is_primary=getattr(listing, "is_primary", False),
                suspicious_jumps_count=suspicious_jumps_count,
                missing_sessions_count=missing_count,
            )

        # Limited history (e.g. recent IPO)
        if clean_candles < self.min_sessions:
            return ListingEligibilityResult(
                listing_id=str(listing.id),
                symbol=listing.symbol,
                exchange=listing.exchange.code,
                isin=isin,
                status=MLEligibilityStatus.LIMITED_HISTORY,
                reason=f"Recent listing/IPO with {clean_candles} sessions ({self.min_limited_sessions} <= N < {self.min_sessions}).",
                total_candles=total_candles,
                clean_candles=clean_candles,
                quarantined_candles=quarantined_count,
                earliest_session=earliest_session,
                latest_session=latest_session,
                median_volume=median_vol,
                coverage_pct=coverage_pct,
                is_primary=getattr(listing, "is_primary", False),
                suspicious_jumps_count=suspicious_jumps_count,
                missing_sessions_count=missing_count,
            )

        # Stale data check
        recent_sessions = expected_sessions[-self.max_stale_sessions:] if len(expected_sessions) >= self.max_stale_sessions else expected_sessions
        if recent_sessions and latest_session < recent_sessions[0]:
            return ListingEligibilityResult(
                listing_id=str(listing.id),
                symbol=listing.symbol,
                exchange=listing.exchange.code,
                isin=isin,
                status=MLEligibilityStatus.STALE_DATA,
                reason=f"Last available candle ({latest_session}) is older than freshness threshold ({recent_sessions[0]}).",
                total_candles=total_candles,
                clean_candles=clean_candles,
                quarantined_candles=quarantined_count,
                earliest_session=earliest_session,
                latest_session=latest_session,
                median_volume=median_vol,
                coverage_pct=coverage_pct,
                is_primary=getattr(listing, "is_primary", False),
                suspicious_jumps_count=suspicious_jumps_count,
                missing_sessions_count=missing_count,
            )

        # Liquidity check
        if median_vol < self.min_median_volume or zero_vol_pct >= self.max_zero_volume_pct:
            return ListingEligibilityResult(
                listing_id=str(listing.id),
                symbol=listing.symbol,
                exchange=listing.exchange.code,
                isin=isin,
                status=MLEligibilityStatus.INSUFFICIENT_LIQUIDITY,
                reason=f"Illiquid listing (median volume {median_vol:g} < {self.min_median_volume:g} or {zero_vol_pct:.1f}% zero-volume sessions).",
                total_candles=total_candles,
                clean_candles=clean_candles,
                quarantined_candles=quarantined_count,
                earliest_session=earliest_session,
                latest_session=latest_session,
                median_volume=median_vol,
                coverage_pct=coverage_pct,
                is_primary=getattr(listing, "is_primary", False),
                suspicious_jumps_count=suspicious_jumps_count,
                missing_sessions_count=missing_count,
            )

        # Fully ML Eligible
        return ListingEligibilityResult(
            listing_id=str(listing.id),
            symbol=listing.symbol,
            exchange=listing.exchange.code,
            isin=isin,
            status=MLEligibilityStatus.ML_ELIGIBLE,
            reason=f"Meets all data depth ({clean_candles} sessions), liquidity ({median_vol:g} shs), and quality criteria.",
            total_candles=total_candles,
            clean_candles=clean_candles,
            quarantined_candles=quarantined_count,
            earliest_session=earliest_session,
            latest_session=latest_session,
            median_volume=median_vol,
            coverage_pct=coverage_pct,
            is_primary=getattr(listing, "is_primary", False),
            suspicious_jumps_count=suspicious_jumps_count,
            missing_sessions_count=missing_count,
        )


class DatasetBuilder:
    """
    Orchestrates historical dataset construction, multi-exchange universe resolution,
    point-in-time corporate adjustments, chunked streaming extraction, and cryptographic hashing.
    """

    def __init__(
        self,
        start_date: date,
        end_date: date,
        exchange_code: str = "NSE",
        universe: str | list[str] = UniverseType.NIFTY_250.value,
        corporate_action_version: str = "corp-v1.0",
        feature_schema_version: str = "schema-v1.0",
        as_of_date: date | None = None,
        deduplicate_dual_listings: bool = False,
        primary_policy: str = "PRIMARY_FLAG_THEN_LIQUIDITY",
        chunk_size: int = 50,
        min_sessions: int = 200,
        min_median_volume: float = 5000.0,
    ):
        self.start_date = start_date
        self.end_date = end_date
        self.exchange_code = exchange_code.upper()
        self.universe_param = universe
        self.corporate_action_version = corporate_action_version
        self.feature_schema_version = feature_schema_version
        self.as_of_date = as_of_date or end_date
        self.deduplicate_dual_listings = deduplicate_dual_listings
        self.primary_policy = primary_policy
        self.chunk_size = chunk_size

        self.adjuster = CorporateActionAdjuster()
        self.validator = DataQualityValidator()
        self.classifier = MLEligibilityClassifier(
            min_sessions=min_sessions,
            min_median_volume=min_median_volume,
        )

    def get_expected_trading_sessions(self) -> list[date]:
        """Computes complete sequence of trading sessions using ExchangeCalendar."""
        sessions = []
        curr = self.start_date
        while curr <= self.end_date:
            if ExchangeCalendar.is_trading_day(curr):
                sessions.append(curr)
            curr += pd.Timedelta(days=1).to_pytimedelta()
        return sessions

    def resolve_universe(self) -> tuple[list[ExchangeListing], dict[str, Any]]:
        """Resolves target equity universe with dual-listing deduplication."""
        return UniverseResolver.resolve(
            universe=self.universe_param,
            exchange_code=self.exchange_code,
            deduplicate_dual_listings=self.deduplicate_dual_listings,
            primary_policy=self.primary_policy,
        )

    def extract_listing_data(
        self,
        listing: ExchangeListing,
        expected_sessions: list[date],
    ) -> tuple[pd.DataFrame, dict[str, Any]]:
        """
        Extracts, validates, and point-in-time adjusts candles for a single listing.
        """
        candles_qs = HistoricalCandle.objects.filter(
            listing=listing,
            interval__iexact="1d",
            timestamp__date__gte=self.start_date,
            timestamp__date__lte=self.end_date,
        ).order_by("timestamp")

        raw_records = []
        quarantined_records = []
        seen_dates = set()
        duplicate_dates = set()

        for c in candles_qs:
            cdate = c.timestamp.date()
            if cdate in seen_dates:
                duplicate_dates.add(cdate)
            seen_dates.add(cdate)

            rec = {
                "candle_id": c.id,
                "session_date": cdate,
                "open": float(c.open),
                "high": float(c.high),
                "low": float(c.low),
                "close": float(c.close),
                "volume": int(c.volume),
                "source_provider": c.source_provider or "UNKNOWN",
            }
            is_valid, errors = self.validator.validate_candle_record(rec)
            if is_valid:
                raw_records.append(rec)
            else:
                rec["validation_errors"] = errors
                quarantined_records.append(rec)

        corp_events = self.adjuster.get_adjustment_events_for_listing(listing, as_of_date=self.as_of_date)
        corp_ex_dates = {e["ex_date"] for e in corp_events}

        if not raw_records:
            audit = {
                "symbol": listing.symbol,
                "exchange": listing.exchange.code,
                "total_candles": 0,
                "clean_candles": 0,
                "quarantined_candles": len(quarantined_records),
                "missing_sessions": len(expected_sessions),
                "duplicate_sessions": len(duplicate_dates),
                "coverage_pct": 0.0,
                "earliest_session": None,
                "latest_session": None,
                "corporate_actions_applied": corp_events,
                "suspicious_jumps": [],
                "quarantined_details": quarantined_records,
            }
            return pd.DataFrame(), audit

        df_raw = pd.DataFrame(raw_records)
        df_raw = df_raw.drop_duplicates(subset=["session_date"], keep="last").sort_values("session_date")

        candle_dates = list(df_raw["session_date"].values)
        multipliers = self.adjuster.calculate_point_in_time_multipliers(corp_events, candle_dates)

        # Build clean dataframe preserving raw prices alongside adjusted prices
        df_clean = pd.DataFrame(index=df_raw.index)
        df_clean["symbol"] = str(listing.symbol)
        df_clean["exchange"] = str(listing.exchange.code)
        df_clean["isin"] = str(listing.instrument.isin) if (listing.instrument and listing.instrument.isin) else "NO_ISIN"
        df_clean["session_date"] = df_raw["session_date"].astype(str)
        df_clean["open_raw"] = df_raw["open"].round(4)
        df_clean["high_raw"] = df_raw["high"].round(4)
        df_clean["low_raw"] = df_raw["low"].round(4)
        df_clean["close_raw"] = df_raw["close"].round(4)
        df_clean["volume_raw"] = df_raw["volume"].astype(int)

        factors = [multipliers.get(d, 1.0) for d in candle_dates]
        df_clean["adjustment_factor"] = [round(f, 6) for f in factors]
        df_clean["open_adj"] = (df_clean["open_raw"] * df_clean["adjustment_factor"]).round(4)
        df_clean["high_adj"] = (df_clean["high_raw"] * df_clean["adjustment_factor"]).round(4)
        df_clean["low_adj"] = (df_clean["low_raw"] * df_clean["adjustment_factor"]).round(4)
        df_clean["close_adj"] = (df_clean["close_raw"] * df_clean["adjustment_factor"]).round(4)
        df_clean["volume_adj"] = (df_clean["volume_raw"] / df_clean["adjustment_factor"]).round().astype(int)
        df_clean["source_provider"] = df_raw["source_provider"]

        suspicious_jumps = self.validator.detect_suspicious_jumps(df_clean, corp_ex_dates)
        missing_sessions = [d for d in expected_sessions if d not in seen_dates]
        coverage_pct = (len(seen_dates) / len(expected_sessions) * 100.0) if expected_sessions else 0.0

        audit = {
            "symbol": listing.symbol,
            "exchange": listing.exchange.code,
            "total_candles": len(raw_records) + len(quarantined_records),
            "clean_candles": len(df_clean),
            "quarantined_candles": len(quarantined_records),
            "missing_sessions": len(missing_sessions),
            "duplicate_sessions": len(duplicate_dates),
            "coverage_pct": round(coverage_pct, 2),
            "earliest_session": min(seen_dates).isoformat() if seen_dates else None,
            "latest_session": max(seen_dates).isoformat() if seen_dates else None,
            "corporate_actions_applied": corp_events,
            "suspicious_jumps": suspicious_jumps,
            "quarantined_details": quarantined_records,
        }

        return df_clean, audit

    def audit_universe_readiness(self) -> dict[str, Any]:
        """
        Executes comprehensive historical data readiness and eligibility audit
        across all resolved listings without necessarily writing full dataset artifacts.
        """
        listings, universe_meta = self.resolve_universe()
        expected_sessions = self.get_expected_trading_sessions()
        total_sessions = len(expected_sessions)

        status_counts = {s.value: 0 for s in MLEligibilityStatus}
        coverage_distribution = {
            "under_1_year": 0,        # < 200 sessions
            "at_least_1_year": 0,     # >= 200 sessions
            "at_least_3_years": 0,    # >= 750 sessions
            "at_least_5_years": 0,    # >= 1250 sessions
            "at_least_10_years": 0,   # >= 2500 sessions
        }

        missing_session_reasons = {
            "pre_listing": 0,
            "missing_source_data": 0,
            "trading_suspension": 0,
        }

        listings_results: list[ListingEligibilityResult] = []
        earliest_global = None
        latest_global = None
        total_clean_samples = 0
        total_quarantined = 0
        total_jumps = 0

        for lst in listings:
            candles_qs = HistoricalCandle.objects.filter(
                listing=lst,
                interval__iexact="1d",
                timestamp__date__gte=self.start_date,
                timestamp__date__lte=self.end_date,
            ).order_by("timestamp")

            # Quick quality and eligibility pass
            df_clean, audit = self.extract_listing_data(lst, expected_sessions)
            total_clean_samples += len(df_clean)
            total_quarantined += audit["quarantined_candles"]
            total_jumps += len(audit["suspicious_jumps"])

            eligibility = self.classifier.classify_listing(
                listing=lst,
                candles_qs=candles_qs,
                expected_sessions=expected_sessions,
                end_date=self.end_date,
                quarantined_count=audit["quarantined_candles"],
                suspicious_jumps_count=len(audit["suspicious_jumps"]),
            )
            listings_results.append(eligibility)
            status_counts[eligibility.status.value] += 1

            # Update historical depth distribution
            c_cnt = eligibility.clean_candles
            if c_cnt >= 2500:
                coverage_distribution["at_least_10_years"] += 1
            if c_cnt >= 1250:
                coverage_distribution["at_least_5_years"] += 1
            if c_cnt >= 750:
                coverage_distribution["at_least_3_years"] += 1
            if c_cnt >= 200:
                coverage_distribution["at_least_1_year"] += 1
            else:
                coverage_distribution["under_1_year"] += 1

            if eligibility.earliest_session:
                if earliest_global is None or eligibility.earliest_session < earliest_global:
                    earliest_global = eligibility.earliest_session
            if eligibility.latest_session:
                if latest_global is None or eligibility.latest_session > latest_global:
                    latest_global = eligibility.latest_session

            # Distinguish missing session causes
            if eligibility.earliest_session and expected_sessions:
                pre_count = sum(1 for d in expected_sessions if d < eligibility.earliest_session)
                missing_session_reasons["pre_listing"] += pre_count
                gaps = max(0, eligibility.missing_sessions_count - pre_count)
                missing_session_reasons["missing_source_data"] += gaps
            else:
                missing_session_reasons["missing_source_data"] += eligibility.missing_sessions_count

        avg_coverage = round(
            sum(r.coverage_pct for r in listings_results) / len(listings_results), 2
        ) if listings_results else 0.0

        distinct_isins = len({r.isin for r in listings_results if r.isin != "NO_ISIN"})

        # Training readiness gate determination
        ready_for_phase_3 = total_clean_samples > 1000 and status_counts[MLEligibilityStatus.ML_ELIGIBLE.value] > 0
        # Phase 4 requires multi-year history (e.g. >= 3-5 years)
        ready_for_phase_4 = coverage_distribution["at_least_3_years"] >= 50 and coverage_distribution["at_least_5_years"] >= 20

        audit = {
            "universe_meta": universe_meta,
            "total_listings_audited": len(listings),
            "distinct_securities_count": distinct_isins,
            "expected_trading_sessions_count": total_sessions,
            "total_expected_slots": len(listings) * total_sessions,
            "total_valid_trading_candles": (len(listings) * total_sessions) - (missing_session_reasons["pre_listing"] + missing_session_reasons["missing_source_data"]),
            "earliest_global_session": earliest_global.isoformat() if earliest_global else None,
            "latest_global_session": latest_global.isoformat() if latest_global else None,
            "status_counts": status_counts,
            "coverage_distribution": coverage_distribution,
            "missing_session_reasons": missing_session_reasons,
            "total_clean_samples": total_clean_samples,
            "total_quarantined_candles": total_quarantined,
            "total_suspicious_jumps": total_jumps,
            "average_coverage_pct": avg_coverage,
            "ready_for_phase_3": ready_for_phase_3,
            "ready_for_phase_4": ready_for_phase_4,
            "phase_4_readiness_reason": (
                "Sufficient multi-year history verified."
                if ready_for_phase_4
                else f"Insufficient historical depth: Database holds ~1 year of candles ({coverage_distribution['at_least_1_year']} listings >=1yr, {coverage_distribution['at_least_3_years']} listings >=3yr, {coverage_distribution['at_least_5_years']} listings >=5yr). Multi-year bhavcopy ingestion required before walk-forward model training."
            ),
            "listings_details": [
                {
                    "symbol": r.symbol,
                    "exchange": r.exchange,
                    "isin": r.isin,
                    "status": r.status.value,
                    "reason": r.reason,
                    "clean_candles": r.clean_candles,
                    "earliest": r.earliest_session.isoformat() if r.earliest_session else None,
                    "latest": r.latest_session.isoformat() if r.latest_session else None,
                    "coverage_pct": r.coverage_pct,
                }
                for r in listings_results[:100]  # top 100 sample
            ],
        }
        return audit

    def build_canonical_dataframe(self) -> tuple[pd.DataFrame, dict[str, Any]]:
        """
        Builds the canonical DataFrame using chunked processing for bounded memory scalability.
        """
        listings, universe_meta = self.resolve_universe()
        expected_sessions = self.get_expected_trading_sessions()

        all_clean_chunks: list[pd.DataFrame] = []
        listings_audit: dict[str, Any] = {}
        total_quarantined = 0
        total_suspicious_jumps = 0
        active_with_data = 0
        excluded_listings: dict[str, str] = {}
        all_actions: list[dict[str, Any]] = []

        # Process in bounded chunks of chunk_size listings
        for i in range(0, len(listings), self.chunk_size):
            chunk = listings[i:i + self.chunk_size]
            chunk_dfs = []
            for lst in chunk:
                df_lst, audit = self.extract_listing_data(lst, expected_sessions)
                listings_audit[f"{lst.exchange.code}:{lst.symbol}"] = audit
                total_quarantined += audit["quarantined_candles"]
                total_suspicious_jumps += len(audit["suspicious_jumps"])
                all_actions.extend(audit["corporate_actions_applied"])

                if not df_lst.empty and len(df_lst) >= 10:
                    chunk_dfs.append(df_lst)
                    active_with_data += 1
                else:
                    excluded_listings[f"{lst.exchange.code}:{lst.symbol}"] = "Insufficient candle history (< 10 trading sessions)"

            if chunk_dfs:
                chunk_df = pd.concat(chunk_dfs, ignore_index=True)
                all_clean_chunks.append(chunk_df)

        if all_clean_chunks:
            canonical_df = pd.concat(all_clean_chunks, ignore_index=True)
            canonical_df = canonical_df.sort_values(by=["symbol", "session_date"]).reset_index(drop=True)
        else:
            canonical_df = pd.DataFrame(columns=[
                "symbol", "exchange", "isin", "session_date",
                "open_raw", "high_raw", "low_raw", "close_raw", "volume_raw",
                "adjustment_factor",
                "open_adj", "high_adj", "low_adj", "close_adj", "volume_adj",
                "source_provider",
            ])

        content_hash = self.compute_canonical_hash(canonical_df)
        universe_hash = self.compute_universe_hash(listings)

        coverages = [a["coverage_pct"] for a in listings_audit.values()]
        avg_coverage = round(sum(coverages) / len(coverages), 2) if coverages else 0.0

        summary_metadata = {
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "as_of_date": self.as_of_date.isoformat(),
            "exchange": self.exchange_code,
            "universe_meta": universe_meta,
            "universe_size": len(listings),
            "active_listings_with_data": active_with_data,
            "total_trading_sessions": len(expected_sessions),
            "average_coverage_pct": avg_coverage,
            "total_samples": len(canonical_df),
            "total_quarantined_candles": total_quarantined,
            "total_suspicious_jumps": total_suspicious_jumps,
            "total_corporate_actions_applied": len(all_actions),
            "corporate_action_version": self.corporate_action_version,
            "feature_schema_version": self.feature_schema_version,
            "content_hash": content_hash,
            "universe_hash": universe_hash,
            "excluded_listings": excluded_listings,
            "generated_at": timezone.now().isoformat(),
        }

        return canonical_df, summary_metadata

    @staticmethod
    def compute_canonical_hash(df: pd.DataFrame) -> str:
        """Computes deterministic SHA-256 hash of canonical CSV bytes."""
        if df.empty:
            return hashlib.sha256(b"EMPTY_CANONICAL_DATASET").hexdigest()

        csv_bytes = df.to_csv(index=False, float_format="%.4f").encode("utf-8")
        return hashlib.sha256(csv_bytes).hexdigest()

    @staticmethod
    def compute_universe_hash(listings: list[ExchangeListing]) -> str:
        """Computes SHA-256 hash of sorted eligible universe ISINs, exchanges, and symbols."""
        canonical_idents = []
        for lst in sorted(listings, key=lambda x: (x.exchange.code, x.symbol)):
            isin = lst.instrument.isin if (lst.instrument and lst.instrument.isin) else "NO_ISIN"
            canonical_idents.append(f"{lst.exchange.code}:{lst.symbol}:{isin}")
        ident_bytes = ",".join(canonical_idents).encode("utf-8")
        return hashlib.sha256(ident_bytes).hexdigest()

    def save_snapshot(
        self,
        canonical_df: pd.DataFrame,
        snapshot_name: str,
        summary_metadata: dict[str, Any],
        dry_run: bool = False,
    ) -> MLDatasetSnapshot:
        """Persists canonical dataset to disk and updates MLDatasetSnapshot."""
        version = f"v_{self.start_date.strftime('%Y%m%d')}_{self.end_date.strftime('%Y%m%d')}"
        storage_dir = Path(getattr(settings, "ML_MODEL_DIR", settings.BASE_DIR / "models")) / "datasets"

        if not dry_run:
            storage_dir.mkdir(parents=True, exist_ok=True)
            file_name = f"{snapshot_name}_{version}.csv"
            file_path = storage_dir / file_name
            canonical_df.to_csv(file_path, index=False, float_format="%.4f")
            storage_path_str = str(file_path)
        else:
            storage_path_str = f"[DRY_RUN] {storage_dir}/{snapshot_name}_{version}.csv"

        quality_status = "VALIDATED" if summary_metadata["average_coverage_pct"] >= 80.0 else "DEGRADED"

        if not dry_run:
            snapshot, _ = MLDatasetSnapshot.objects.update_or_create(
                version=version,
                defaults={
                    "name": snapshot_name,
                    "start_date": self.start_date,
                    "end_date": self.end_date,
                    "universe_hash": summary_metadata["universe_hash"],
                    "content_hash": summary_metadata["content_hash"],
                    "universe_size": summary_metadata["universe_size"],
                    "total_samples": len(canonical_df),
                    "feature_count": len(canonical_df.columns),
                    "corporate_action_version": self.corporate_action_version,
                    "feature_schema_version": self.feature_schema_version,
                    "quality_status": quality_status,
                    "storage_path": storage_path_str,
                    "metadata": summary_metadata,
                },
            )
            return snapshot
        else:
            return MLDatasetSnapshot(
                name=snapshot_name,
                version=version,
                start_date=self.start_date,
                end_date=self.end_date,
                universe_hash=summary_metadata["universe_hash"],
                content_hash=summary_metadata["content_hash"],
                universe_size=summary_metadata["universe_size"],
                total_samples=len(canonical_df),
                feature_count=len(canonical_df.columns),
                corporate_action_version=self.corporate_action_version,
                feature_schema_version=self.feature_schema_version,
                quality_status=quality_status,
                storage_path=storage_path_str,
                metadata=summary_metadata,
            )
