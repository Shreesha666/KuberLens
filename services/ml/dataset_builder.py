"""
Historical Dataset Builder and Point-in-Time Corporate Action Adjustment Engine.
Complies with Master Specification Section 18 and AIML Architecture Specification v2.1.

Extracts historical OHLCV candles, checks data quality (OHLC consistency, non-negative volume,
missing/duplicate sessions, suspicious jumps), applies verified split and bonus adjustments
strictly using point-in-time ex-dates from CorporateEvent, and computes deterministic
SHA-256 canonical content hashes for MLDatasetSnapshot records.
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
from django.conf import settings
from django.utils import timezone

from apps.instruments.models import ExchangeListing
from apps.market.models import HistoricalCandle
from apps.ml_engine.models import MLDatasetSnapshot
from apps.news.models import CorporateEvent
from services.calendar.exchange_calendar import ExchangeCalendar

logger = logging.getLogger(__name__)


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
                    # In Indian corporate announcements, "1:5 Split" indicates 1 share becomes 5 shares (N=5)
                    # "5:1 Split" also denotes 5 new shares for 1 old share (N=5)
                    # A split sub-divides shares, so new shares >= old shares
                    split_ratio = max(n1, n2) / min(n1, n2)
                    factor = round(1.0 / split_ratio, 6)
                    return factor, f"1:{int(split_ratio)} split (f={factor:.6f})"

            # Default fallback for unrecognized split: neutral factor
            logger.warning("Unrecognized split ratio format: '%s'. Applying neutral factor 1.0", combined_text)
            return 1.0, f"Unrecognized split: {combined_text} (f=1.000000)"

        elif "BONUS" in etype:
            # Ratio format: "A:B Bonus" means A new bonus shares for B held.
            # Post-bonus shares = B + A. Multiplier factor = B / (B + A).
            ratio_match = re.search(r"(\d+)\s*:\s*(\d+)", combined_text)
            if ratio_match:
                n1 = float(ratio_match.group(1))
                n2 = float(ratio_match.group(2))
                if n1 > 0 and n2 > 0:
                    # Usually formatted as "1:1" (1 new for 1 held), "3:1" (3 new for 1 held),
                    # "1:2" (1 new for 2 held), "1:4" (1 new for 4 held).
                    # A = new bonus shares, B = existing shares held
                    # In market convention "3:1 bonus" is 3 bonus for 1 held. "1:2 bonus" is 1 bonus for 2 held.
                    # If n1 >= n2, A=n1, B=n2. If n1 < n2, A=n1, B=n2.
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


class DatasetBuilder:
    """
    Orchestrates historical dataset construction, corporate action adjustments,
    data quality validation, canonical formatting, and reproducible snapshot persistence.
    """

    def __init__(
        self,
        start_date: date,
        end_date: date,
        exchange_code: str = "NSE",
        universe: str | list[str] = "nifty250",
        corporate_action_version: str = "corp-v1.0",
        feature_schema_version: str = "schema-v1.0",
        as_of_date: date | None = None,
    ):
        self.start_date = start_date
        self.end_date = end_date
        self.exchange_code = exchange_code.upper()
        self.universe_param = universe
        self.corporate_action_version = corporate_action_version
        self.feature_schema_version = feature_schema_version
        self.as_of_date = as_of_date or end_date

        self.adjuster = CorporateActionAdjuster()
        self.validator = DataQualityValidator()

    def get_expected_trading_sessions(self) -> list[date]:
        """
        Computes the complete sequence of exchange trading sessions
        between start_date and end_date using ExchangeCalendar.
        """
        sessions = []
        curr = self.start_date
        while curr <= self.end_date:
            if ExchangeCalendar.is_trading_day(curr):
                sessions.append(curr)
            curr += pd.Timedelta(days=1).to_pytimedelta()
        return sessions

    def resolve_universe(self) -> list[ExchangeListing]:
        """
        Resolves eligible stock universe listings.
        Supports:
          - 'nifty250': NIFTY LargeMidcap 250 constituents from seed list
          - 'all': All tradeable listings for the specified exchange
          - list[str]: Explicit list of ticker symbols
        """
        base_qs = ExchangeListing.objects.filter(
            exchange__code=self.exchange_code,
            is_tradeable=True,
        ).select_related("instrument", "exchange")

        if isinstance(self.universe_param, str):
            if self.universe_param.lower() == "nifty250":
                try:
                    from apps.instruments.management.commands.seed_nifty250 import NIFTY_250_STOCKS
                    symbols = [s["symbol"] for s in NIFTY_250_STOCKS]
                    listings = list(base_qs.filter(symbol__in=symbols).order_by("symbol"))
                    if not listings:
                        # Fallback if seed list not populated
                        listings = list(base_qs.order_by("symbol")[:250])
                    return listings
                except ImportError:
                    return list(base_qs.order_by("symbol")[:250])
            elif self.universe_param.lower() == "all":
                return list(base_qs.order_by("symbol"))
            else:
                symbols = [s.strip().upper() for s in self.universe_param.split(",") if s.strip()]
                return list(base_qs.filter(symbol__in=symbols).order_by("symbol"))
        elif isinstance(self.universe_param, (list, tuple, set)):
            symbols = [str(s).strip().upper() for s in self.universe_param]
            return list(base_qs.filter(symbol__in=symbols).order_by("symbol"))

        return list(base_qs.order_by("symbol")[:250])

    def extract_listing_data(
        self,
        listing: ExchangeListing,
        expected_sessions: list[date],
    ) -> tuple[pd.DataFrame, dict[str, Any]]:
        """
        Extracts, validates, and point-in-time adjusts candles for a single listing.
        Returns:
          - clean_df: DataFrame with raw and adjusted columns
          - audit_info: Dictionary detailing coverage, corporate actions, and quality issues
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

        # Retrieve corporate actions sliced strictly <= as_of_date
        corp_events = self.adjuster.get_adjustment_events_for_listing(listing, as_of_date=self.as_of_date)
        corp_ex_dates = {e["ex_date"] for e in corp_events}

        if not raw_records:
            audit = {
                "symbol": listing.symbol,
                "total_candles": 0,
                "clean_candles": 0,
                "quarantined_candles": len(quarantined_records),
                "missing_sessions": len(expected_sessions),
                "duplicate_sessions": len(duplicate_dates),
                "coverage_pct": 0.0,
                "corporate_actions_applied": corp_events,
                "suspicious_jumps": [],
                "quarantined_details": quarantined_records,
            }
            return pd.DataFrame(), audit

        # Deduplicate raw records keeping the last one if duplicates exist
        df_raw = pd.DataFrame(raw_records)
        df_raw = df_raw.drop_duplicates(subset=["session_date"], keep="last").sort_values("session_date")

        candle_dates = list(df_raw["session_date"].values)
        multipliers = self.adjuster.calculate_point_in_time_multipliers(corp_events, candle_dates)

        # Build clean columns: preserve raw execution prices alongside adjusted research prices
        df_clean = pd.DataFrame(index=df_raw.index)
        df_clean["symbol"] = str(listing.symbol)
        df_clean["isin"] = str(listing.instrument.isin) if (listing.instrument and listing.instrument.isin) else ""
        df_clean["session_date"] = df_raw["session_date"].astype(str)
        df_clean["open_raw"] = df_raw["open"].round(4)
        df_clean["high_raw"] = df_raw["high"].round(4)
        df_clean["low_raw"] = df_raw["low"].round(4)
        df_clean["close_raw"] = df_raw["close"].round(4)
        df_clean["volume_raw"] = df_raw["volume"].astype(int)

        # Calculate adjusted prices
        factors = [multipliers.get(d, 1.0) for d in candle_dates]
        df_clean["adjustment_factor"] = [round(f, 6) for f in factors]
        df_clean["open_adj"] = (df_clean["open_raw"] * df_clean["adjustment_factor"]).round(4)
        df_clean["high_adj"] = (df_clean["high_raw"] * df_clean["adjustment_factor"]).round(4)
        df_clean["low_adj"] = (df_clean["low_raw"] * df_clean["adjustment_factor"]).round(4)
        df_clean["close_adj"] = (df_clean["close_raw"] * df_clean["adjustment_factor"]).round(4)
        df_clean["volume_adj"] = (df_clean["volume_raw"] / df_clean["adjustment_factor"]).round().astype(int)
        df_clean["source_provider"] = df_raw["source_provider"]

        # Detect suspicious price jumps
        suspicious_jumps = self.validator.detect_suspicious_jumps(df_clean, corp_ex_dates)

        # Missing session dates
        missing_sessions = [d for d in expected_sessions if d not in seen_dates]
        coverage_pct = (len(seen_dates) / len(expected_sessions) * 100.0) if expected_sessions else 0.0

        audit = {
            "symbol": listing.symbol,
            "total_candles": len(raw_records) + len(quarantined_records),
            "clean_candles": len(df_clean),
            "quarantined_candles": len(quarantined_records),
            "missing_sessions": len(missing_sessions),
            "duplicate_sessions": len(duplicate_dates),
            "coverage_pct": round(coverage_pct, 2),
            "corporate_actions_applied": corp_events,
            "suspicious_jumps": suspicious_jumps,
            "quarantined_details": quarantined_records,
        }

        return df_clean, audit

    def build_canonical_dataframe(self) -> tuple[pd.DataFrame, dict[str, Any]]:
        """
        Builds the complete canonical dataframe across all universe listings.
        Returns:
          - canonical_df: DataFrame deterministically sorted by ['symbol', 'session_date']
          - summary_metadata: Provenance, coverage statistics, quality metrics, and hashes
        """
        listings = self.resolve_universe()
        expected_sessions = self.get_expected_trading_sessions()

        all_dfs = []
        listings_audit = {}
        total_quarantined = 0
        total_suspicious_jumps = 0
        active_listings_count = 0
        excluded_listings = {}

        for lst in listings:
            df_lst, audit = self.extract_listing_data(lst, expected_sessions)
            listings_audit[lst.symbol] = audit
            total_quarantined += audit["quarantined_candles"]
            total_suspicious_jumps += len(audit["suspicious_jumps"])

            if not df_lst.empty and len(df_lst) >= 10:
                all_dfs.append(df_lst)
                active_listings_count += 1
            else:
                excluded_listings[lst.symbol] = "Insufficient candle history (< 10 trading sessions)"

        if all_dfs:
            canonical_df = pd.concat(all_dfs, ignore_index=True)
            # Deterministic sorting
            canonical_df = canonical_df.sort_values(by=["symbol", "session_date"]).reset_index(drop=True)
        else:
            # Empty canonical DataFrame with exact schema
            canonical_df = pd.DataFrame(columns=[
                "symbol", "isin", "session_date",
                "open_raw", "high_raw", "low_raw", "close_raw", "volume_raw",
                "adjustment_factor",
                "open_adj", "high_adj", "low_adj", "close_adj", "volume_adj",
                "source_provider",
            ])

        # Calculate hashes
        content_hash = self.compute_canonical_hash(canonical_df)
        universe_hash = self.compute_universe_hash(listings)

        # Average coverage
        coverages = [a["coverage_pct"] for a in listings_audit.values()]
        avg_coverage = round(sum(coverages) / len(coverages), 2) if coverages else 0.0

        # Collect corporate actions across all listings
        all_actions = []
        for a in listings_audit.values():
            all_actions.extend(a["corporate_actions_applied"])

        summary_metadata = {
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "as_of_date": self.as_of_date.isoformat(),
            "exchange": self.exchange_code,
            "universe_type": str(self.universe_param),
            "universe_size": len(listings),
            "active_listings_with_data": active_listings_count,
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
        """
        Computes deterministic SHA-256 hash of the canonical CSV bytes.
        Sorting and fixed precision ensure 100% bit-for-bit reproducibility.
        """
        if df.empty:
            return hashlib.sha256(b"EMPTY_CANONICAL_DATASET").hexdigest()

        csv_bytes = df.to_csv(index=False, float_format="%.4f").encode("utf-8")
        return hashlib.sha256(csv_bytes).hexdigest()

    @staticmethod
    def compute_universe_hash(listings: list[ExchangeListing]) -> str:
        """
        Computes SHA-256 hash of sorted eligible universe ISINs and symbols.
        """
        canonical_idents = []
        for lst in sorted(listings, key=lambda x: x.symbol):
            isin = lst.instrument.isin if lst.instrument else ""
            canonical_idents.append(f"{lst.symbol}:{isin}")
        ident_bytes = ",".join(canonical_idents).encode("utf-8")
        return hashlib.sha256(ident_bytes).hexdigest()

    def save_snapshot(
        self,
        canonical_df: pd.DataFrame,
        snapshot_name: str,
        summary_metadata: dict[str, Any],
        dry_run: bool = False,
    ) -> MLDatasetSnapshot:
        """
        Persists canonical dataset to disk (CSV/Parquet) and creates an MLDatasetSnapshot row.
        """
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
