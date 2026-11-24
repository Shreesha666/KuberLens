"""
Feature Engineering Pipeline for KuberLens AI/ML.
Complies with AIML Architecture Specification v2.1 and Master Specification Section 18.
Strictly point-in-time calculation avoiding lookahead bias.
Computes technical momentum, trend ratios, volatility, volume, liquidity,
market context, and publication-verified fundamental indicators.
"""
import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from apps.ml_engine.models import MLFeatureDefinition

logger = logging.getLogger(__name__)

FEATURE_SCHEMA_VERSION = "feat-v2.1.0"


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    category: str
    lookback_periods: int
    formula_description: str


# Catalog of standard technical and market features produced by FeaturePipeline
FEATURE_CATALOG: list[FeatureSpec] = [
    FeatureSpec("return_1d", "MOMENTUM", 1, "1-session return (close_adj[t] - close_adj[t-1]) / close_adj[t-1]"),
    FeatureSpec("return_5d", "MOMENTUM", 5, "5-session return (close_adj[t] - close_adj[t-5]) / close_adj[t-5]"),
    FeatureSpec("return_10d", "MOMENTUM", 10, "10-session return (close_adj[t] - close_adj[t-10]) / close_adj[t-10]"),
    FeatureSpec("return_20d", "MOMENTUM", 20, "20-session return (close_adj[t] - close_adj[t-20]) / close_adj[t-20]"),
    FeatureSpec("sma_ratio_20_50", "TREND", 50, "SMA 20 / SMA 50 ratio minus 1.0"),
    FeatureSpec("price_to_sma20", "TREND", 20, "(close_adj[t] - SMA_20) / SMA_20"),
    FeatureSpec("price_to_sma50", "TREND", 50, "(close_adj[t] - SMA_50) / SMA_50"),
    FeatureSpec("price_to_sma200", "TREND", 200, "(close_adj[t] - SMA_200) / SMA_200 (NaN if < 200 sessions)"),
    FeatureSpec("ema_trend_ratio_9_20", "TREND", 20, "EMA 9 / EMA 20 ratio minus 1.0"),
    FeatureSpec("rsi_14", "MOMENTUM", 14, "Wilder's 14-period Relative Strength Index bounded in [0, 100]"),
    FeatureSpec("stoch_rsi_k", "MOMENTUM", 14, "Stochastic RSI %K over 14 periods"),
    FeatureSpec("macd_hist_ratio", "MOMENTUM", 26, "MACD Histogram (12, 26, 9) divided by close_adj"),
    FeatureSpec("bb_bandwidth", "VOLATILITY", 20, "Bollinger Bandwidth: (Upper - Lower) / Middle * 100"),
    FeatureSpec("bb_percent_b", "VOLATILITY", 20, "Bollinger %B: (close_adj - Lower) / (Upper - Lower)"),
    FeatureSpec("atr_ratio_14", "VOLATILITY", 14, "Average True Range (14) divided by close_adj"),
    FeatureSpec("adx_14", "TREND", 14, "Average Directional Index (14) Wilder's smoothed"),
    FeatureSpec("garman_klass_vol", "VOLATILITY", 20, "20-day annualized Garman-Klass volatility estimate"),
    FeatureSpec("realized_vol_20", "VOLATILITY", 20, "20-day rolling standard deviation of 1-day log returns * sqrt(252)"),
    FeatureSpec("volume_ratio_20", "VOLUME", 20, "Volume / 20-day SMA(Volume) capped at 5.0x"),
    FeatureSpec("obv_trend_ratio_20", "VOLUME", 20, "OBV / 20-day SMA(OBV) minus 1.0"),
    FeatureSpec("universe_median_rel_strength_20", "MARKET_CONTEXT", 20, "20-session stock return minus cross-sectional universe median return"),
    FeatureSpec("benchmark_rel_strength_20", "MARKET_CONTEXT", 20, "20-session stock return minus verified NIFTY 50 index benchmark return (NaN when benchmark candles unavailable)"),
    FeatureSpec("market_regime_id", "REGIME", 30, "Market regime categorical: 0=RANGE_BOUND, 1=TRENDING_UP, 2=TRENDING_DOWN, 3=HIGH_VOLATILITY"),
]


class FeaturePipeline:
    """
    Transforms canonical historical OHLCV data into point-in-time feature vectors.
    Strictly avoids future data leakage by ensuring every feature at session t
    is computed exclusively from data available on or before session t.
    """

    def __init__(
        self,
        warmup_sessions: int = 50,
        include_sma200: bool = True,
        schema_version: str = FEATURE_SCHEMA_VERSION,
    ):
        self.warmup_sessions = warmup_sessions
        self.include_sma200 = include_sma200
        self.schema_version = schema_version

    @classmethod
    def sync_feature_definitions_to_db(cls) -> int:
        """
        Populates or updates the MLFeatureDefinition table in database.
        Returns the number of active feature definitions registered.
        """
        count = 0
        for spec in FEATURE_CATALOG:
            MLFeatureDefinition.objects.update_or_create(
                name=spec.name,
                defaults={
                    "category": spec.category,
                    "lookback_periods": spec.lookback_periods,
                    "calculation_version": FEATURE_SCHEMA_VERSION,
                    "formula_description": spec.formula_description,
                    "is_active": True,
                },
            )
            count += 1
        return count

    def compute_stock_features(self, df_stock: pd.DataFrame) -> pd.DataFrame:
        """
        Computes single-stock time-series technical and volatility features.
        Input DataFrame must contain:
          ['session_date', 'close_adj', 'open_adj', 'high_adj', 'low_adj', 'volume_adj']
        Returns DataFrame with original columns plus engineered feature columns.
        """
        if df_stock.empty:
            return pd.DataFrame()

        df = df_stock.sort_values("session_date").reset_index(drop=True).copy()

        c = df["close_adj"].astype(float)
        h = df["high_adj"].astype(float)
        low_p = df["low_adj"].astype(float)
        o = df["open_adj"].astype(float)
        v = df["volume_adj"].astype(float)

        # 1. Momentum Returns
        df["return_1d"] = c.pct_change(1)
        df["return_5d"] = c.pct_change(5)
        df["return_10d"] = c.pct_change(10)
        df["return_20d"] = c.pct_change(20)

        # 2. Moving Averages & Trend Ratios
        sma20 = c.rolling(window=20, min_periods=20).mean()
        sma50 = c.rolling(window=50, min_periods=50).mean()
        sma200 = c.rolling(window=200, min_periods=200).mean()

        df["price_to_sma20"] = (c - sma20) / sma20
        df["price_to_sma50"] = (c - sma50) / sma50
        df["price_to_sma200"] = (c - sma200) / sma200
        df["sma_ratio_20_50"] = (sma20 / sma50) - 1.0

        # EMA Trend Ratios
        ema9 = c.ewm(span=9, adjust=False).mean()
        ema20 = c.ewm(span=20, adjust=False).mean()
        df["ema_trend_ratio_9_20"] = (ema9 / ema20) - 1.0

        # 3. RSI 14 (Wilder's Smoothing)
        delta = c.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()

        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = np.where(avg_loss == 0, np.where(avg_gain > 0, 100.0, 50.0), 100.0 - (100.0 / (1.0 + rs)))
        df["rsi_14"] = pd.Series(rsi, index=df.index).fillna(50.0)

        # Stochastic RSI
        rsi_min14 = df["rsi_14"].rolling(window=14, min_periods=14).min()
        rsi_max14 = df["rsi_14"].rolling(window=14, min_periods=14).max()
        rsi_denom = (rsi_max14 - rsi_min14).replace(0, np.nan)
        df["stoch_rsi_k"] = ((df["rsi_14"] - rsi_min14) / rsi_denom * 100.0).fillna(50.0)

        # 4. MACD (12, 26, 9)
        ema12 = c.ewm(span=12, adjust=False).mean()
        ema26 = c.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        macd_signal = macd_line.ewm(span=9, adjust=False).mean()
        macd_hist = macd_line - macd_signal
        df["macd_hist_ratio"] = macd_hist / c

        # 5. Bollinger Bands (20, 2)
        bb_std = c.rolling(window=20, min_periods=20).std()
        bb_upper = sma20 + (2.0 * bb_std)
        bb_lower = sma20 - (2.0 * bb_std)
        bb_width = bb_upper - bb_lower
        df["bb_bandwidth"] = (bb_width / sma20.replace(0, np.nan)) * 100.0
        df["bb_percent_b"] = (c - bb_lower) / bb_width.replace(0, np.nan)

        # 6. ATR 14 & Volatility Ratios
        prev_close = c.shift(1)
        tr1 = h - low_p
        tr2 = (h - prev_close).abs()
        tr3 = (low_p - prev_close).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr_14 = tr.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
        df["atr_ratio_14"] = atr_14 / c

        # 7. Directional Movement Index & ADX 14
        h_diff = h.diff()
        l_diff = -low_p.diff()
        pos_dm = np.where((h_diff > l_diff) & (h_diff > 0), h_diff, 0.0)
        neg_dm = np.where((l_diff > h_diff) & (l_diff > 0), l_diff, 0.0)
        tr_smooth = tr.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
        pos_di = 100.0 * (pd.Series(pos_dm, index=df.index).ewm(alpha=1 / 14, min_periods=14, adjust=False).mean() / tr_smooth.replace(0, np.nan))
        neg_di = 100.0 * (pd.Series(neg_dm, index=df.index).ewm(alpha=1 / 14, min_periods=14, adjust=False).mean() / tr_smooth.replace(0, np.nan))
        di_denom = (pos_di + neg_di).replace(0, np.nan)
        dx = (100.0 * (pos_di - neg_di).abs() / di_denom).fillna(0.0)
        df["adx_14"] = dx.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean().fillna(20.0)

        # 8. Garman-Klass Volatility & Realized Volatility
        # GK = 0.5 * ln(H/L)^2 - (2*ln(2) - 1) * ln(C/O)^2
        log_hl = np.log((h / low_p.replace(0, np.nan)).clip(lower=1e-6))
        log_co = np.log((c / o.replace(0, np.nan)).clip(lower=1e-6))
        gk_daily = 0.5 * (log_hl ** 2) - (2.0 * np.log(2) - 1.0) * (log_co ** 2)
        gk_rolling = gk_daily.rolling(window=20, min_periods=20).mean()
        df["garman_klass_vol"] = (np.sqrt(gk_rolling.clip(lower=0)) * np.sqrt(252.0) * 100.0).fillna(0.0)

        log_returns = np.log((c / prev_close.replace(0, np.nan)).clip(lower=1e-6))
        df["realized_vol_20"] = (log_returns.rolling(window=20, min_periods=20).std() * np.sqrt(252.0) * 100.0).fillna(0.0)

        # 9. Volume & Liquidity Features
        vol_sma20 = v.rolling(window=20, min_periods=20).mean()
        df["volume_ratio_20"] = (v / vol_sma20.replace(0, np.nan)).clip(upper=5.0)

        # On-Balance Volume (OBV) trend ratio
        obv_direction = np.sign(c.diff()).fillna(0)
        obv = (obv_direction * v).cumsum()
        obv_sma20 = obv.rolling(window=20, min_periods=20).mean()
        df["obv_trend_ratio_20"] = np.where(
            obv_sma20 != 0,
            (obv - obv_sma20) / obv_sma20.abs(),
            0.0,
        )

        # 10. Statistical Market Regime ID
        # 0=RANGE_BOUND, 1=TRENDING_UP, 2=TRENDING_DOWN, 3=HIGH_VOLATILITY
        regime_ids = []
        for idx in range(len(df)):
            if idx < 30:
                regime_ids.append(0)  # Default Range
            else:
                bw = df.at[idx, "bb_bandwidth"]
                cur_rsi = df.at[idx, "rsi_14"]
                s20 = sma20.iloc[idx]
                s50 = sma50.iloc[idx]
                cur_c = c.iloc[idx]
                if pd.notna(bw) and bw > 15.0:
                    regime_ids.append(3)  # HIGH_VOLATILITY
                elif pd.notna(s20) and pd.notna(s50) and cur_c > s20 > s50 and cur_rsi > 55:
                    regime_ids.append(1)  # TRENDING_UP
                elif pd.notna(s20) and pd.notna(s50) and cur_c < s20 < s50 and cur_rsi < 45:
                    regime_ids.append(2)  # TRENDING_DOWN
                else:
                    regime_ids.append(0)  # RANGE_BOUND

        df["market_regime_id"] = regime_ids

        return df

    def transform_universe_canonical(
        self,
        df_canonical: pd.DataFrame,
        fund_publication_lookup: dict[tuple[str, Any], dict[str, float]] | None = None,
    ) -> pd.DataFrame:
        """
        Vectorized transformation of cross-sectional canonical DataFrame containing
        multiple listings across time.
        Preserves exchange-specific symbol identities, applies single-stock time-series
        features per listing group, computes cross-sectional benchmark relative strength,
        and applies publication date guards to fundamental features.
        """
        if df_canonical.empty:
            return pd.DataFrame()

        processed_dfs = []
        for _symbol, group in df_canonical.groupby("symbol", sort=False):
            stock_features = self.compute_stock_features(group)
            processed_dfs.append(stock_features)

        df_out = pd.concat(processed_dfs, ignore_index=True)

        # Cross-Sectional Market Context: Universe Median Relative Strength
        # Excess 20d return over the median return of the cross-sectional universe on each session
        if "return_20d" in df_out.columns:
            session_medians = df_out.groupby("session_date")["return_20d"].transform("median")
            df_out["universe_median_rel_strength_20"] = df_out["return_20d"] - session_medians
        else:
            df_out["universe_median_rel_strength_20"] = 0.0

        # True Benchmark Relative Strength (against verified NIFTY 50 index candles)
        # Sourced only when verified benchmark candles are available; otherwise NaN
        df_out["benchmark_rel_strength_20"] = np.nan

        # Point-in-Time Fundamental Feature Integration Guard
        # If no verified filing publication dates exist, fundamental features are strictly excluded.
        if fund_publication_lookup:
            logger.info("Applying publication-verified fundamental attributes...")
            pe_list, roe_list, de_list = [], [], []
            for _, row in df_out.iterrows():
                key = (str(row["symbol"]), row["session_date"])
                funds = fund_publication_lookup.get(key)
                if funds:
                    pe_list.append(funds.get("pe_ratio", np.nan))
                    roe_list.append(funds.get("roe", np.nan))
                    de_list.append(funds.get("debt_to_equity", np.nan))
                else:
                    pe_list.append(np.nan)
                    roe_list.append(np.nan)
                    de_list.append(np.nan)
            df_out["fund_pe_ratio"] = pe_list
            df_out["fund_roe"] = roe_list
            df_out["fund_debt_to_equity"] = de_list
        else:
            logger.debug("No verified fundamental publication lookup provided. Fundamental features excluded from training.")

        return df_out

    def filter_warmup_periods(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Prunes initial warmup sessions per listing where rolling indicators (e.g. 50-session SMA)
        have insufficient historical observations.
        """
        if df.empty:
            return df

        valid_masks = []
        for _symbol, group in df.groupby("symbol", sort=False):
            # Keep observations with at least warmup_sessions history
            mask = pd.Series(False, index=group.index)
            if len(group) >= self.warmup_sessions:
                mask.iloc[self.warmup_sessions:] = True
            valid_masks.append(mask)

        full_mask = pd.concat(valid_masks)
        return df[full_mask].reset_index(drop=True)
