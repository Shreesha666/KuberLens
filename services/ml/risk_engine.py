"""
Market Regime Detection and Risk-Veto Intelligence Engine for KuberLens AI/ML.
Complies with AIML Architecture Specification v2.1 and Master Specification Section 18.

Implements explainable, research-only risk intelligence:
1. MarketRegimeDetector:
   Identifies market macro and single-stock regimes:
   - BULLISH_TREND: Strong positive momentum and moving average alignment (C > SMA20 > SMA50, RSI > 55).
   - BEARISH_TREND: Sustained downward pressure (C < SMA20 < SMA50, RSI < 45).
   - SIDEWAYS_CONSOLIDATION: Mean-reverting, low Bollinger bandwidth, neutral RSI.
   - HIGH_VOLATILITY: Bollinger bandwidth expansion (> 15%) or Garman-Klass vol > 40%.
   - MARKET_STRESS: Extreme volatility with severe benchmark or stock breakdown.
2. MLRiskVetoEngine:
   Evaluates existing heuristic setups against multi-factor risk dimensions:
   - Trend weakness / exhaustion
   - Excessive volatility / ATR expansion
   - Relative benchmark weakness
   - Tail drawdown risk
   Outputs explainable risk classifications: LOW_RISK, MODERATE_RISK, HIGH_RISK, INSUFFICIENT_DATA.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


class MarketRegimeClassification(StrEnum):
    BULLISH_TREND = "BULLISH_TREND"
    BEARISH_TREND = "BEARISH_TREND"
    SIDEWAYS_CONSOLIDATION = "SIDEWAYS_CONSOLIDATION"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    MARKET_STRESS = "MARKET_STRESS"


class RiskVetoLevel(StrEnum):
    LOW_RISK = "LOW_RISK"
    MODERATE_RISK = "MODERATE_RISK"
    HIGH_RISK = "HIGH_RISK"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass(frozen=True)
class RiskVetoAssessment:
    symbol: str
    session_date: str
    regime: MarketRegimeClassification
    risk_level: RiskVetoLevel
    is_vetoed: bool
    risk_score: float  # Bounded [0.0, 100.0]
    veto_reasons: list[str]
    metrics: dict[str, float]


class MarketRegimeDetector:
    """
    Classifies market state strictly using point-in-time features available at session close t.
    Zero future information is utilized.
    """

    @staticmethod
    def classify_row(row: pd.Series | dict[str, Any]) -> MarketRegimeClassification:
        bw = float(row.get("bb_bandwidth", 0.0) or 0.0)
        rsi = float(row.get("rsi_14", 50.0) or 50.0)
        p_to_sma20 = float(row.get("price_to_sma20", 0.0) or 0.0)
        p_to_sma50 = float(row.get("price_to_sma50", 0.0) or 0.0)
        p_to_sma200 = float(row.get("price_to_sma200", 0.0) or 0.0)
        atr_ratio = float(row.get("atr_ratio_14", 0.02) or 0.02)
        gk_vol = float(row.get("garman_klass_vol", 20.0) or 20.0)

        # 1. Market Stress / Severe Breakdown
        if (p_to_sma50 < -0.10 and atr_ratio > 0.035) or (gk_vol > 50.0 and rsi < 35.0):
            return MarketRegimeClassification.MARKET_STRESS

        # 2. High Volatility Expansion
        if bw > 15.0 or gk_vol > 40.0 or atr_ratio > 0.035:
            return MarketRegimeClassification.HIGH_VOLATILITY

        # 3. Bullish Trend
        if p_to_sma20 > 0 and p_to_sma50 > 0 and rsi > 55.0 and p_to_sma200 > -0.02:
            return MarketRegimeClassification.BULLISH_TREND

        # 4. Bearish Trend
        if p_to_sma20 < 0 and p_to_sma50 < 0 and rsi < 45.0:
            return MarketRegimeClassification.BEARISH_TREND

        # 5. Sideways Consolidation
        return MarketRegimeClassification.SIDEWAYS_CONSOLIDATION

    def classify_dataframe(self, df_features: pd.DataFrame) -> pd.Series:
        """Vectorized classification across a feature DataFrame."""
        return df_features.apply(self.classify_row, axis=1)


class MLRiskVetoEngine:
    """
    Evaluates trading setups against systematic and idiosyncratic risk factors.
    Acts as an explainable risk veto layer without replacing production heuristic rules.
    """

    def __init__(
        self,
        max_atr_ratio: float = 0.035,  # Veto if ATR ratio > 3.5%
        min_rsi_exhaustion: float = 75.0,  # Veto if overbought exhaustion > 75
        max_sma50_drawdown: float = -0.08,  # Veto if severe intermediate breakdown < -8%
        veto_stress_regime: bool = True,
    ):
        self.max_atr_ratio = max_atr_ratio
        self.min_rsi_exhaustion = min_rsi_exhaustion
        self.max_sma50_drawdown = max_sma50_drawdown
        self.veto_stress_regime = veto_stress_regime
        self.regime_detector = MarketRegimeDetector()

    def assess_setup(self, row: pd.Series | dict[str, Any]) -> RiskVetoAssessment:
        sym = str(row.get("symbol", "UNKNOWN"))
        sdate = str(row.get("session_date", "1970-01-01"))

        # Check data sufficiency
        required_keys = ["atr_ratio_14", "rsi_14", "price_to_sma50", "bb_bandwidth"]
        if any(pd.isna(row.get(k)) for k in required_keys):
            return RiskVetoAssessment(
                symbol=sym,
                session_date=sdate,
                regime=MarketRegimeClassification.SIDEWAYS_CONSOLIDATION,
                risk_level=RiskVetoLevel.INSUFFICIENT_DATA,
                is_vetoed=True,
                risk_score=100.0,
                veto_reasons=["Insufficient historical feature data to evaluate risk."],
                metrics={},
            )

        regime = self.regime_detector.classify_row(row)

        atr_ratio = float(row.get("atr_ratio_14", 0.0))
        rsi = float(row.get("rsi_14", 50.0))
        p_to_sma50 = float(row.get("price_to_sma50", 0.0))
        bw = float(row.get("bb_bandwidth", 0.0))
        rel_strength = float(row.get("benchmark_rel_strength_20", 0.0))

        reasons = []
        risk_score = 20.0  # Base nominal risk

        # Factor 1: Market Regime Stress
        if regime == MarketRegimeClassification.MARKET_STRESS:
            reasons.append("Market regime is in severe stress / structural breakdown.")
            risk_score += 40.0
        elif regime == MarketRegimeClassification.HIGH_VOLATILITY:
            reasons.append(f"Elevated volatility regime (Bandwidth: {bw:.1f}%, ATR: {atr_ratio*100:.1f}%).")
            risk_score += 25.0
        elif regime == MarketRegimeClassification.BEARISH_TREND:
            risk_score += 20.0

        # Factor 2: Extreme Idiosyncratic Volatility
        if atr_ratio > self.max_atr_ratio:
            reasons.append(f"Excessive daily volatility: ATR ratio {atr_ratio*100:.2f}% exceeds safety threshold {self.max_atr_ratio*100:.2f}%.")
            risk_score += 30.0

        # Factor 3: Momentum Exhaustion / Overbought
        if rsi > self.min_rsi_exhaustion:
            reasons.append(f"Momentum exhaustion: RSI(14) is {rsi:.1f} (> {self.min_rsi_exhaustion:.1f}), elevated risk of mean reversion.")
            risk_score += 25.0

        # Factor 4: Severe Intermediate Breakdown
        if p_to_sma50 < self.max_sma50_drawdown:
            reasons.append(f"Severe breakdown: Price is {p_to_sma50*100:.1f}% below 50-day SMA (< {self.max_sma50_drawdown*100:.1f}%).")
            risk_score += 25.0

        # Factor 5: Severe Relative Benchmark Lag
        if rel_strength < -0.08:
            reasons.append(f"Severe relative weakness: 20-day benchmark relative strength is {rel_strength*100:.1f}%.")
            risk_score += 15.0

        risk_score = min(100.0, max(0.0, risk_score))

        # Risk level determination
        if risk_score >= 60.0 or (self.veto_stress_regime and regime == MarketRegimeClassification.MARKET_STRESS):
            risk_level = RiskVetoLevel.HIGH_RISK
            is_vetoed = True
        elif risk_score >= 40.0:
            risk_level = RiskVetoLevel.MODERATE_RISK
            is_vetoed = False
        else:
            risk_level = RiskVetoLevel.LOW_RISK
            is_vetoed = False

        import math

        def _clean_metric(v):
            if v is None or pd.isna(v) or math.isnan(float(v)):
                return None
            return round(float(v), 2)

        metrics = {
            "atr_ratio_pct": _clean_metric(atr_ratio * 100.0),
            "rsi_14": _clean_metric(rsi),
            "price_to_sma50_pct": _clean_metric(p_to_sma50 * 100.0),
            "bb_bandwidth_pct": _clean_metric(bw),
            "benchmark_rel_strength_pct": _clean_metric(rel_strength * 100.0),
        }

        return RiskVetoAssessment(
            symbol=sym,
            session_date=sdate,
            regime=regime,
            risk_level=risk_level,
            is_vetoed=is_vetoed,
            risk_score=round(risk_score, 1),
            veto_reasons=reasons,
            metrics=metrics,
        )

    def evaluate_dataframe(self, df_features: pd.DataFrame) -> list[RiskVetoAssessment]:
        """Evaluates an entire DataFrame row by row."""
        return [self.assess_setup(row) for _, row in df_features.iterrows()]
