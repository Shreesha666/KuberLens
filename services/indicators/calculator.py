"""
High-performance Technical Indicator Calculation Engine.
Calculates trend, momentum, volatility, and volume indicators using pandas & numpy.
Ensures deterministic calculation versioning and strict raw/derived data separation.
"""
import logging
from collections.abc import Sequence
from decimal import Decimal

import numpy as np
import pandas as pd
from django.utils import timezone

from apps.market.models import HistoricalCandle
from apps.technical_analysis.models import TechnicalIndicatorSnapshot

logger = logging.getLogger(__name__)


class TechnicalIndicatorCalculator:
    CALCULATION_VERSION = "tech-v1.0.0"

    @classmethod
    def calculate_dataframe(cls, df: pd.DataFrame) -> pd.DataFrame:
        """
        Takes a pandas DataFrame with columns: ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        sorted ascending by timestamp.
        Computes all indicators and appends them as new columns.
        """
        if len(df) == 0:
            return df

        df = df.sort_values("timestamp").reset_index(drop=True).copy()

        # 1. Moving Averages (SMA & EMA)
        for w in [20, 50, 100, 200]:
            df[f"sma_{w}"] = df["close"].rolling(window=w, min_periods=1).mean()

        for s in [9, 20, 50]:
            df[f"ema_{s}"] = df["close"].ewm(span=s, adjust=False).mean()

        # 2. MACD (12, 26, 9)
        ema_12 = df["close"].ewm(span=12, adjust=False).mean()
        ema_26 = df["close"].ewm(span=26, adjust=False).mean()
        df["macd_line"] = ema_12 - ema_26
        df["macd_signal"] = df["macd_line"].ewm(span=9, adjust=False).mean()
        df["macd_histogram"] = df["macd_line"] - df["macd_signal"]

        # 3. RSI 14 (Wilder's Smoothing)
        delta = df["close"].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)

        # Initial average
        avg_gain = gain.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()

        # Handle zero division: zero loss -> RSI 100; zero gain -> RSI 0
        rsi = np.where(
            avg_loss == 0,
            np.where(avg_gain > 0, 100.0, 50.0),
            np.where(
                avg_gain == 0,
                0.0,
                100.0 - (100.0 / (1.0 + (avg_gain / avg_loss.replace(0, np.nan))))
            )
        )
        df["rsi_14"] = pd.Series(rsi, index=df.index).fillna(50.0)

        # Stochastic RSI
        rsi_min_14 = df["rsi_14"].rolling(window=14, min_periods=1).min()
        rsi_max_14 = df["rsi_14"].rolling(window=14, min_periods=1).max()
        rsi_range = (rsi_max_14 - rsi_min_14).replace(0, np.nan)
        stoch_k = ((df["rsi_14"] - rsi_min_14) / rsi_range) * 100
        df["stoch_rsi_k"] = stoch_k.fillna(50.0)
        df["stoch_rsi_d"] = df["stoch_rsi_k"].rolling(window=3, min_periods=1).mean()

        # 4. Bollinger Bands (20, 2)
        bb_sma = df["close"].rolling(window=20, min_periods=1).mean()
        bb_std = df["close"].rolling(window=20, min_periods=1).std().fillna(0)
        df["bollinger_middle"] = bb_sma
        df["bollinger_upper"] = bb_sma + (2 * bb_std)
        df["bollinger_lower"] = bb_sma - (2 * bb_std)
        df["bollinger_bandwidth"] = np.where(
            bb_sma > 0, ((df["bollinger_upper"] - df["bollinger_lower"]) / bb_sma) * 100, 0.0
        )

        # 5. Average True Range (ATR 14)
        prev_close = df["close"].shift(1)
        tr1 = df["high"] - df["low"]
        tr2 = (df["high"] - prev_close).abs()
        tr3 = (df["low"] - prev_close).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df["atr_14"] = tr.ewm(alpha=1 / 14, min_periods=1, adjust=False).mean()

        # 6. Rate of Change (ROC 10)
        df["roc_10"] = df["close"].pct_change(periods=10).fillna(0) * 100

        # 7. Volume Indicators
        df["volume_sma_20"] = df["volume"].rolling(window=20, min_periods=1).mean().fillna(0)
        df["relative_volume"] = np.where(
            df["volume_sma_20"] > 0, df["volume"] / df["volume_sma_20"], 1.0
        )

        # On-Balance Volume (OBV)
        direction = np.sign(df["close"].diff()).fillna(0)
        df["obv"] = (direction * df["volume"]).cumsum()

        # 8. Support and Resistance (Rolling 20-period Min/Max)
        df["support_level"] = df["low"].rolling(window=20, min_periods=1).min()
        df["resistance_level"] = df["high"].rolling(window=20, min_periods=1).max()
        df["swing_low"] = df["support_level"]
        df["swing_high"] = df["resistance_level"]

        # 9. Signal Generation
        # Trend Signal
        df["trend_signal"] = "NEUTRAL"
        bull_mask = (df["close"] > df["sma_50"]) & (df["sma_50"] >= df["sma_200"])
        bear_mask = (df["close"] < df["sma_50"]) & (df["sma_50"] <= df["sma_200"])
        df.loc[bull_mask, "trend_signal"] = "BULLISH"
        df.loc[bear_mask, "trend_signal"] = "BEARISH"

        # RSI Signal
        df["rsi_signal"] = "NEUTRAL"
        df.loc[df["rsi_14"] >= 70, "rsi_signal"] = "OVERBOUGHT"
        df.loc[df["rsi_14"] <= 30, "rsi_signal"] = "OVERSOLD"

        # MACD Signal Type
        df["macd_signal_type"] = "NEUTRAL"
        prev_diff = (df["macd_line"] - df["macd_signal"]).shift(1).fillna(0)
        curr_diff = df["macd_line"] - df["macd_signal"]
        df.loc[(prev_diff <= 0) & (curr_diff > 0), "macd_signal_type"] = "BULLISH_CROSS"
        df.loc[(prev_diff >= 0) & (curr_diff < 0), "macd_signal_type"] = "BEARISH_CROSS"

        # Moving Average Cross Signal (Golden Cross / Death Cross)
        df["ma_cross_signal"] = "NEUTRAL"
        ma_diff_prev = (df["sma_50"] - df["sma_200"]).shift(1).fillna(0)
        ma_diff_curr = df["sma_50"] - df["sma_200"]
        df.loc[(ma_diff_prev <= 0) & (ma_diff_curr > 0), "ma_cross_signal"] = "GOLDEN_CROSS"
        df.loc[(ma_diff_prev >= 0) & (ma_diff_curr < 0), "ma_cross_signal"] = "DEATH_CROSS"

        # Breakout Signal
        df["breakout_signal"] = "NEUTRAL"
        prev_res = df["resistance_level"].shift(1)
        prev_sup = df["support_level"].shift(1)
        df.loc[(prev_res.notna()) & (df["close"] > prev_res), "breakout_signal"] = "RESISTANCE_BREAKOUT"
        df.loc[(prev_sup.notna()) & (df["close"] < prev_sup), "breakout_signal"] = "SUPPORT_BREAKDOWN"

        return df

    @classmethod
    def compute_and_store_snapshots(
        cls,
        listing,
        candles: Sequence[HistoricalCandle],
        calculation_version: str | None = None,
    ) -> list[TechnicalIndicatorSnapshot]:
        """
        Takes raw historical candles for a listing, computes all indicators,
        and saves/updates snapshots in PostgreSQL.
        """
        if not candles:
            return []

        version = calculation_version or cls.CALCULATION_VERSION

        # Convert candles to dataframe
        records = [
            {
                "timestamp": c.timestamp,
                "open": float(c.open),
                "high": float(c.high),
                "low": float(c.low),
                "close": float(c.close),
                "volume": c.volume,
            }
            for c in candles
        ]
        df = pd.DataFrame.from_records(records)
        df_calc = cls.calculate_dataframe(df)

        now = timezone.now()
        snapshots = []

        def to_dec(val):
            if val is None or pd.isna(val) or np.isinf(val):
                return None
            return Decimal(str(round(float(val), 4)))

        def to_int(val):
            if val is None or pd.isna(val) or np.isinf(val):
                return None
            return int(val)

        for _, row in df_calc.iterrows():
            snapshot = TechnicalIndicatorSnapshot(
                listing=listing,
                interval="1d",
                timestamp=row["timestamp"],
                sma_20=to_dec(row.get("sma_20")),
                sma_50=to_dec(row.get("sma_50")),
                sma_100=to_dec(row.get("sma_100")),
                sma_200=to_dec(row.get("sma_200")),
                ema_9=to_dec(row.get("ema_9")),
                ema_20=to_dec(row.get("ema_20")),
                ema_50=to_dec(row.get("ema_50")),
                macd_line=to_dec(row.get("macd_line")),
                macd_signal=to_dec(row.get("macd_signal")),
                macd_histogram=to_dec(row.get("macd_histogram")),
                rsi_14=to_dec(row.get("rsi_14")),
                stoch_rsi_k=to_dec(row.get("stoch_rsi_k")),
                stoch_rsi_d=to_dec(row.get("stoch_rsi_d")),
                adx_14=to_dec(row.get("adx_14")),
                roc_10=to_dec(row.get("roc_10")),
                bollinger_upper=to_dec(row.get("bollinger_upper")),
                bollinger_middle=to_dec(row.get("bollinger_middle")),
                bollinger_lower=to_dec(row.get("bollinger_lower")),
                bollinger_bandwidth=to_dec(row.get("bollinger_bandwidth")),
                atr_14=to_dec(row.get("atr_14")),
                volume_sma_20=to_int(row.get("volume_sma_20")),
                relative_volume=to_dec(row.get("relative_volume")),
                obv=to_int(row.get("obv")),
                support_level=to_dec(row.get("support_level")),
                resistance_level=to_dec(row.get("resistance_level")),
                swing_high=to_dec(row.get("swing_high")),
                swing_low=to_dec(row.get("swing_low")),
                trend_signal=row.get("trend_signal", "NEUTRAL"),
                rsi_signal=row.get("rsi_signal", "NEUTRAL"),
                macd_signal_type=row.get("macd_signal_type", "NEUTRAL"),
                ma_cross_signal=row.get("ma_cross_signal", "NEUTRAL"),
                breakout_signal=row.get("breakout_signal", "NEUTRAL"),
                calculation_version=version,
                calculated_at=now,
            )
            snapshots.append(snapshot)

        # Bulk upsert using ignore_conflicts or delete old version then create
        TechnicalIndicatorSnapshot.objects.filter(
            listing=listing,
            calculation_version=version,
        ).delete()
        TechnicalIndicatorSnapshot.objects.bulk_create(snapshots, batch_size=500)
        logger.info("Saved %d technical indicator snapshots for %s", len(snapshots), listing.symbol)
        return snapshots
