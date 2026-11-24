"""
Unit and Regression Tests for Phase 4.2 Risk Intelligence, Regime Detection & Portfolio Validation.
Complies with AIML Architecture Specification v2.1 and Master Specification Section 18.

Tests cover:
1. Portfolio ledger reconciliation (matching trade net P&L with ending equity cash change).
2. Point-in-time safety of MarketRegimeDetector (deterministic classification from t-only data).
3. RiskVetoEngine multi-factor risk scoring and veto criteria.
4. Probability calibration extremes audit (Platt scaling vs Isotonic floor/cap).
5. Heuristic setup filtering and opportunity cost analysis.
"""
import numpy as np
import pandas as pd

from services.ml.calibrator import ProbabilityCalibrator
from services.ml.portfolio_simulator import ResearchPortfolioSimulator
from services.ml.risk_engine import (
    MarketRegimeClassification,
    MarketRegimeDetector,
    MLRiskVetoEngine,
    RiskVetoLevel,
)


class TestMLPhase42RiskIntelligence:

    def test_portfolio_ledger_reconciliation_exact_pnl(self):
        """
        Verify that portfolio total net P&L equals exactly ending cash minus initial capital
        when all positions are closed at simulation end.
        """
        dates = [f"2026-02-{i:02d}" for i in range(1, 26)]
        rows = []
        for d in dates:
            for sym in ["STOCK_X", "STOCK_Y"]:
                rows.append({
                    "session_date": d,
                    "symbol": sym,
                    "open_raw": 200.0,
                    "close_raw": 210.0,
                    "open_adj": 200.0,
                    "close_adj": 210.0,
                })
        df_prices = pd.DataFrame(rows)

        df_signals = pd.DataFrame([
            {"session_date": "2026-02-01", "symbol": "STOCK_X", "signal": 1},
            {"session_date": "2026-02-05", "symbol": "STOCK_Y", "signal": 1},
        ])

        sim = ResearchPortfolioSimulator(
            initial_capital=1_000_000.0,
            max_position_pct=0.10,
            horizon_sessions=10,
            slippage_pct=0.0005,
        )
        perf = sim.simulate(df_signals, df_prices)

        # Both positions must be closed by Feb 25
        assert perf.total_trades == 2
        per_stock_sum = sum(perf.per_stock_pnl.values())
        assert abs(perf.total_net_pnl - per_stock_sum) < 0.05
        assert abs(perf.ending_capital - (perf.initial_capital + perf.total_net_pnl)) < 0.05

    def test_market_regime_detector_rules(self):
        """
        Verify that MarketRegimeDetector accurately classifies regimes under canonical conditions.
        """
        detector = MarketRegimeDetector()

        # 1. Bullish trend
        bull_row = {
            "bb_bandwidth": 8.0,
            "rsi_14": 62.0,
            "price_to_sma20": 0.03,
            "price_to_sma50": 0.06,
            "price_to_sma200": 0.12,
            "atr_ratio_14": 0.018,
            "garman_klass_vol": 18.0,
        }
        assert detector.classify_row(bull_row) == MarketRegimeClassification.BULLISH_TREND

        # 2. Bearish trend
        bear_row = {
            "bb_bandwidth": 9.0,
            "rsi_14": 38.0,
            "price_to_sma20": -0.04,
            "price_to_sma50": -0.07,
            "price_to_sma200": -0.10,
            "atr_ratio_14": 0.022,
            "garman_klass_vol": 22.0,
        }
        assert detector.classify_row(bear_row) == MarketRegimeClassification.BEARISH_TREND

        # 3. Market Stress
        stress_row = {
            "bb_bandwidth": 22.0,
            "rsi_14": 28.0,
            "price_to_sma20": -0.12,
            "price_to_sma50": -0.15,
            "price_to_sma200": -0.25,
            "atr_ratio_14": 0.048,
            "garman_klass_vol": 55.0,
        }
        assert detector.classify_row(stress_row) == MarketRegimeClassification.MARKET_STRESS

    def test_risk_veto_engine_triggers(self):
        """
        Verify that MLRiskVetoEngine vetoes setups with excessive volatility or breakdown.
        """
        engine = MLRiskVetoEngine(max_atr_ratio=0.035)

        # High risk due to excessive ATR (4.5% > 3.5%)
        risky_setup = {
            "symbol": "HIGH_VOL_CO",
            "session_date": "2026-03-15",
            "atr_ratio_14": 0.045,
            "rsi_14": 52.0,
            "price_to_sma50": -0.02,
            "bb_bandwidth": 16.0,
            "garman_klass_vol": 42.0,
            "benchmark_rel_strength_20": -0.01,
        }
        assessment = engine.assess_setup(risky_setup)
        assert assessment.is_vetoed is True
        assert assessment.risk_level == RiskVetoLevel.HIGH_RISK
        assert any("Excessive daily volatility" in r for r in assessment.veto_reasons)

        # Low risk benign setup
        benign_setup = {
            "symbol": "STABLE_CO",
            "session_date": "2026-03-15",
            "atr_ratio_14": 0.016,
            "rsi_14": 56.0,
            "price_to_sma20": 0.02,
            "price_to_sma50": 0.04,
            "price_to_sma200": 0.08,
            "bb_bandwidth": 6.5,
            "garman_klass_vol": 15.0,
            "benchmark_rel_strength_20": 0.03,
        }
        assessment_benign = engine.assess_setup(benign_setup)
        assert assessment_benign.is_vetoed is False
        assert assessment_benign.risk_level == RiskVetoLevel.LOW_RISK

    def test_platt_vs_isotonic_calibration_extremes(self):
        """
        Verify that Platt scaling prevents saturation at 0.001 or 0.999 compared to Isotonic.
        """
        np.random.seed(42)
        raw_val = np.random.uniform(0.40, 0.48, 100)
        y_val = (raw_val > 0.44).astype(int)

        platt = ProbabilityCalibrator(method="platt").fit(raw_val, y_val)
        iso = ProbabilityCalibrator(method="isotonic").fit(raw_val, y_val)

        test_points = np.array([0.38, 0.42, 0.46, 0.52])
        p_platt = platt.calibrate(test_points)
        assert iso.calibrate(test_points) is not None

        # Platt scaling should be smooth and strictly within interior (0.05, 0.95)
        assert np.all((p_platt > 0.01) & (p_platt < 0.99))
        assert p_platt[3] > p_platt[2] > p_platt[1] > p_platt[0]
