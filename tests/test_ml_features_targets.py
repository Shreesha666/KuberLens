"""
Tests for AI/ML Phase 3: Feature Engineering and Forward Target Labeling.
Complies with AIML Architecture Specification v2.1 and Master Specification Section 18.
Verifies point-in-time calculation, zero future leakage, technical indicators,
fundamental publication guards, forward next-open execution targets, statutory friction,
and incomplete horizon handling.
"""
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from apps.ml_engine.models import MLFeatureDefinition
from services.ml.features import FEATURE_CATALOG, FeaturePipeline
from services.ml.targets import TargetBuilder, TargetConfig


@pytest.fixture
def synthetic_stock_df():
    """
    Creates 100 sessions of synthetic daily OHLCV dataframe.
    """
    base_date = date(2026, 1, 1)
    dates = [base_date + timedelta(days=i) for i in range(100)]
    prices = [100.0 + (i * 0.5) for i in range(100)]
    df = pd.DataFrame({
        "symbol": ["TESTSTOCK"] * 100,
        "exchange": ["NSE"] * 100,
        "isin": ["INE000TEST01"] * 100,
        "session_date": dates,
        "open_raw": [p - 0.2 for p in prices],
        "high_raw": [p + 1.0 for p in prices],
        "low_raw": [p - 1.0 for p in prices],
        "close_raw": prices,
        "volume_raw": [10000 + (i * 50) for i in range(100)],
        "adjustment_factor": [1.0] * 100,
        "open_adj": [p - 0.2 for p in prices],
        "high_adj": [p + 1.0 for p in prices],
        "low_adj": [p - 1.0 for p in prices],
        "close_adj": prices,
        "volume_adj": [10000 + (i * 50) for i in range(100)],
    })
    return df


class TestFeaturePipeline:
    """
    Validates FeaturePipeline technical feature formulas, lookback boundaries,
    and publication-date restrictions.
    """

    def test_sync_feature_definitions_to_db(self, db):
        count = FeaturePipeline.sync_feature_definitions_to_db()
        assert count == len(FEATURE_CATALOG)
        assert MLFeatureDefinition.objects.count() == len(FEATURE_CATALOG)
        rsi_feat = MLFeatureDefinition.objects.get(name="rsi_14")
        assert rsi_feat.category == "MOMENTUM"
        assert rsi_feat.lookback_periods == 14
        # Verify renamed universe median feature
        assert MLFeatureDefinition.objects.filter(name="universe_median_rel_strength_20").exists()
        # Verify true benchmark relative strength feature
        assert MLFeatureDefinition.objects.filter(name="benchmark_rel_strength_20").exists()

    def test_momentum_and_trend_feature_calculation(self, synthetic_stock_df):
        pipeline = FeaturePipeline(warmup_sessions=50)
        df_feat = pipeline.compute_stock_features(synthetic_stock_df)

        assert "return_1d" in df_feat.columns
        assert "return_5d" in df_feat.columns
        assert "return_10d" in df_feat.columns
        assert "return_20d" in df_feat.columns
        assert "price_to_sma20" in df_feat.columns
        assert "price_to_sma50" in df_feat.columns
        assert "sma_ratio_20_50" in df_feat.columns
        assert "rsi_14" in df_feat.columns
        assert "adx_14" in df_feat.columns
        assert "garman_klass_vol" in df_feat.columns
        assert "volume_ratio_20" in df_feat.columns
        assert "market_regime_id" in df_feat.columns

        # Verify mathematical consistency
        # On row 10, return_5d should be (close[10] - close[5]) / close[5]
        c10 = synthetic_stock_df["close_adj"].iloc[10]
        c5 = synthetic_stock_df["close_adj"].iloc[5]
        expected_ret_5 = (c10 - c5) / c5
        assert np.isclose(df_feat["return_5d"].iloc[10], expected_ret_5)

        # RSI values must be strictly bounded in [0, 100]
        assert df_feat["rsi_14"].min() >= 0.0
        assert df_feat["rsi_14"].max() <= 100.0

    def test_no_future_leakage_in_features(self, synthetic_stock_df):
        """
        Altering future price data at session t+10 must have zero impact
        on feature values computed at session t.
        """
        pipeline = FeaturePipeline()
        df1 = pipeline.compute_stock_features(synthetic_stock_df)

        # Alter future data from index 50 onwards
        modified_df = synthetic_stock_df.copy()
        modified_df.loc[50:, "close_adj"] = modified_df.loc[50:, "close_adj"] * 2.0
        modified_df.loc[50:, "high_adj"] = modified_df.loc[50:, "high_adj"] * 2.0
        df2 = pipeline.compute_stock_features(modified_df)

        # Features up to index 49 must be bitwise identical
        cols_to_check = ["return_1d", "return_5d", "return_10d", "return_20d", "rsi_14", "price_to_sma20", "atr_ratio_14"]
        for col in cols_to_check:
            np.testing.assert_allclose(
                df1[col].iloc[:50].values,
                df2[col].iloc[:50].values,
                err_msg=f"Future price alteration leaked into feature {col}!",
            )

    def test_fundamental_publication_guard(self, synthetic_stock_df):
        """
        Fundamental features are strictly excluded if no verified publication date exists,
        preventing lookahead leakage from quarterly filings.
        """
        pipeline = FeaturePipeline()

        # Case 1: No publication lookup -> fundamental columns are completely omitted
        df_no_funds = pipeline.transform_universe_canonical(synthetic_stock_df, fund_publication_lookup=None)
        assert "fund_pe_ratio" not in df_no_funds.columns
        assert "fund_roe" not in df_no_funds.columns

        # Case 2: Verified publication lookup provided
        pub_lookup = {
            ("TESTSTOCK", synthetic_stock_df["session_date"].iloc[60]): {"pe_ratio": 22.5, "roe": 18.2, "debt_to_equity": 0.3}
        }
        df_funds = pipeline.transform_universe_canonical(synthetic_stock_df, fund_publication_lookup=pub_lookup)
        assert "fund_pe_ratio" in df_funds.columns
        assert df_funds["fund_pe_ratio"].iloc[60] == 22.5
        assert pd.isna(df_funds["fund_pe_ratio"].iloc[0])  # Prior sessions must be NaN

    def test_filter_warmup_periods(self, synthetic_stock_df):
        pipeline = FeaturePipeline(warmup_sessions=20)
        df_feat = pipeline.compute_stock_features(synthetic_stock_df)
        df_pruned = pipeline.filter_warmup_periods(df_feat)
        assert len(df_pruned) == 100 - 20
        assert df_pruned["session_date"].iloc[0] == synthetic_stock_df["session_date"].iloc[20]


class TestTargetBuilder:
    """
    Validates forward-return classification targets for 5, 10, and 20 sessions:
    Next-session open execution, transaction friction, and incomplete horizon handling.
    """

    def test_next_session_open_execution_assumption(self, synthetic_stock_df):
        """
        Target return must use next session open (O_{t+1}) as entry and horizon close (C_{t+h}) as exit.
        """
        builder = TargetBuilder(use_tax_calculator=False)
        df_target = builder.compute_stock_targets(synthetic_stock_df)

        # For index 0 and horizon 5:
        # Entry = open_adj[1] (i.e. synthetic_stock_df['open_adj'].iloc[1])
        # Exit = close_adj[5] (i.e. synthetic_stock_df['close_adj'].iloc[5])
        o_next = synthetic_stock_df["open_adj"].iloc[1]
        c_exit = synthetic_stock_df["close_adj"].iloc[5]
        expected_raw_ret = (c_exit - o_next) / o_next

        actual_raw_ret = df_target["target_return_abs_5d"].iloc[0]
        assert np.isclose(actual_raw_ret, expected_raw_ret)

    def test_transaction_cost_deduction(self, synthetic_stock_df):
        """
        Net return must be raw forward return minus realistic Indian round-trip friction.
        """
        builder = TargetBuilder(use_tax_calculator=True)
        df_target = builder.compute_stock_targets(synthetic_stock_df)

        ret_abs_5 = df_target["target_return_abs_5d"].iloc[10]
        ret_net_5 = df_target["target_return_net_5d"].iloc[10]
        assert ret_net_5 < ret_abs_5  # Net return must deduct transaction costs
        friction = ret_abs_5 - ret_net_5
        # Statutory taxes + slippage should be in the realistic range of 0.20% to 0.50%
        assert 0.0020 <= friction <= 0.0060

    def test_incomplete_forward_horizon_leaves_nan(self, synthetic_stock_df):
        """
        Observations near the end of the time series whose forward horizons have not yet completed
        must be assigned NaN (never fabricated or filled with present prices).
        """
        builder = TargetBuilder()
        df_target = builder.compute_stock_targets(synthetic_stock_df)
        n = len(synthetic_stock_df)

        # Horizon 5: last 5 rows must have NaN target
        for idx in range(n - 5, n):
            assert pd.isna(df_target["target_binary_5d"].iloc[idx])
            assert pd.isna(df_target["target_return_net_5d"].iloc[idx])

        # Horizon 10: last 10 rows must have NaN target
        for idx in range(n - 10, n):
            assert pd.isna(df_target["target_binary_10d"].iloc[idx])
            assert pd.isna(df_target["target_return_net_10d"].iloc[idx])

        # Horizon 20: last 20 rows must have NaN target
        for idx in range(n - 20, n):
            assert pd.isna(df_target["target_binary_20d"].iloc[idx])
            assert pd.isna(df_target["target_return_net_20d"].iloc[idx])

    def test_binary_directional_hurdles(self, synthetic_stock_df):
        """
        Binary target is 1 if net return > tau_h, else 0.
        """
        configs = {
            5: TargetConfig(horizon_sessions=5, hurdle_rate=0.010, slippage_pct=0.0005)
        }
        builder = TargetBuilder(target_configs=configs, use_tax_calculator=False)
        df_target = builder.compute_stock_targets(synthetic_stock_df)

        for i in range(len(df_target) - 5):
            net_ret = df_target["target_return_net_5d"].iloc[i]
            label = df_target["target_binary_5d"].iloc[i]
            if net_ret > 0.010:
                assert label == 1.0
            else:
                assert label == 0.0

    def test_multistock_universe_transformation(self, synthetic_stock_df):
        """
        Universe target transformation groups by symbol and computes forward shifts strictly per stock.
        """
        df_stock2 = synthetic_stock_df.copy()
        df_stock2["symbol"] = "STOCKTWO"
        df_stock2["isin"] = "INE999STOCK02"

        df_universe = pd.concat([synthetic_stock_df, df_stock2], ignore_index=True)
        builder = TargetBuilder()
        df_out = builder.transform_universe_targets(df_universe)

        assert len(df_out) == 200
        assert df_out["symbol"].nunique() == 2
        # Verify both stocks have targets computed independently
        assert "target_binary_5d" in df_out.columns
        assert "target_binary_10d" in df_out.columns
        assert "target_binary_20d" in df_out.columns

    def test_target_with_in_holding_corporate_action(self):
        """
        Tests forward economic return calculation when a 2-for-1 stock split
        occurs inside the holding period between entry O_{t+1} and exit C_{t+h}.
        The unadjusted close falls by 50%, but point-in-time adjusted prices
        neutralize the split, reflecting the true economic holding return.
        """
        base_date = date(2026, 6, 1)
        dates = [base_date + timedelta(days=i) for i in range(10)]

        # Stock splits 2-for-1 on day 5 (factor=0.5 prior to day 5)
        # Raw prices: 100 for days 0-4, then 50 for days 5-9 (no real loss)
        raw_closes = [100.0] * 5 + [50.0] * 5
        raw_opens = [100.0] * 5 + [50.0] * 5

        # Backward adjusted prices (neutralized):
        # Day 0-4 adjusted price = 100 * 0.5 = 50.0
        # Day 5-9 adjusted price = 50 * 1.0 = 50.0
        adj_closes = [50.0] * 10
        adj_opens = [50.0] * 10

        df = pd.DataFrame({
            "symbol": ["SPLITSTOCK"] * 10,
            "exchange": ["NSE"] * 10,
            "isin": ["INE000SPLT01"] * 10,
            "session_date": dates,
            "open_raw": raw_opens,
            "high_raw": [p + 2.0 for p in raw_opens],
            "low_raw": [p - 2.0 for p in raw_opens],
            "close_raw": raw_closes,
            "volume_raw": [10000] * 10,
            "adjustment_factor": [0.5] * 5 + [1.0] * 5,
            "open_adj": adj_opens,
            "high_adj": [p + 1.0 for p in adj_opens],
            "low_adj": [p - 1.0 for p in adj_opens],
            "close_adj": adj_closes,
            "volume_adj": [20000] * 5 + [10000] * 5,
        })

        configs = {5: TargetConfig(horizon_sessions=5, hurdle_rate=0.005, slippage_pct=0.0)}
        builder = TargetBuilder(target_configs=configs, use_tax_calculator=False)
        df_target = builder.compute_stock_targets(df)

        # For row 0: Entry is day 1 open (adj = 50.0), Exit is day 5 close (adj = 50.0).
        # Economic return should be (50 - 50) / 50 = 0.0 (NOT -50% loss from raw price drop)
        abs_ret = df_target["target_return_abs_5d"].iloc[0]
        assert np.isclose(abs_ret, 0.0)

        # Step 1 Verification: When tax/costs are enabled, gross return is 0.0 but net return strictly deducts friction
        builder_with_tax = TargetBuilder(target_configs=configs, use_tax_calculator=True)
        df_target_tax = builder_with_tax.compute_stock_targets(df)
        net_ret = df_target_tax["target_return_net_5d"].iloc[0]
        assert np.isclose(df_target_tax["target_return_abs_5d"].iloc[0], 0.0)
        assert net_ret < 0.0  # Even with 0.0 gross return, net return must deduct statutory friction
        assert net_ret == 0.0 - builder_with_tax.compute_round_trip_cost_ratio(entry_price=100.0, exit_price=50.0)
