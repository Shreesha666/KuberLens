"""
Forward Target Labeling Engine for KuberLens AI/ML.
Complies with AIML Architecture Specification v2.1 and Master Specification Section 18.
Strictly point-in-time calculation avoiding lookahead bias.
Computes forward-return classification targets for 5, 10, and 20 trading sessions:
- Execution at next-session open (O_{t+1})
- Horizon-specific exit at session close (C_{t+h})
- Explicit round-trip transaction costs (brokerage, STT, exchange charges, GST, stamp duty, dynamic slippage)
  integrated with IndianTaxCalculator.
- Incomplete forward horizons are left as NaN (never fabricated or filled with current prices).
"""
import logging
from dataclasses import dataclass
from decimal import Decimal

import numpy as np
import pandas as pd

from services.paper_trading.tax_calculator import IndianTaxCalculator

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TargetConfig:
    horizon_sessions: int
    hurdle_rate: float        # tau_h (e.g. 0.005 for 5d, 0.010 for 10d, 0.015 for 20d)
    slippage_pct: float       # dynamic bid-ask slippage (default 0.0005 per leg = 0.0010 round-trip)
    min_volume_threshold: float = 1000.0


# Standard hurdle rates and horizons per AIML Architecture v2.1
DEFAULT_TARGET_CONFIGS: dict[int, TargetConfig] = {
    5: TargetConfig(horizon_sessions=5, hurdle_rate=0.005, slippage_pct=0.0005),
    10: TargetConfig(horizon_sessions=10, hurdle_rate=0.010, slippage_pct=0.0005),
    20: TargetConfig(horizon_sessions=20, hurdle_rate=0.015, slippage_pct=0.0005),
}


class TargetBuilder:
    """
    Constructs forward-looking supervised targets from historical point-in-time candles.
    Enforces realistic next-session open fill assumptions and statutory transaction friction.
    """

    def __init__(
        self,
        target_configs: dict[int, TargetConfig] | None = None,
        use_tax_calculator: bool = True,
        slippage_pct: float = 0.0005,
    ):
        self.target_configs = target_configs or DEFAULT_TARGET_CONFIGS
        self.use_tax_calculator = use_tax_calculator
        self.slippage_pct = slippage_pct

    def compute_round_trip_cost_ratio(
        self,
        entry_price: float,
        exit_price: float,
        quantity: int = 100,
    ) -> float:
        """
        Computes realistic round-trip friction as a fraction of entry price:
        Statutory charges (STT, Brokerage, Exchange charges, GST, SEBI, Stamp duty)
        plus dynamic slippage on both entry and exit legs.
        """
        if entry_price <= 0 or exit_price <= 0:
            return 0.0035  # Fallback default ~0.35%

        if not self.use_tax_calculator:
            # Fixed standard Indian equity friction: ~0.25% statutory + 0.10% slippage = 0.35%
            return 0.0035

        try:
            buy_charges = IndianTaxCalculator.calculate(
                quantity=quantity,
                price=Decimal(str(round(entry_price, 4))),
                side="BUY",
                product_type="CNC",
            )
            sell_charges = IndianTaxCalculator.calculate(
                quantity=quantity,
                price=Decimal(str(round(exit_price, 4))),
                side="SELL",
                product_type="CNC",
            )
            total_charges = float(buy_charges.total_charges + sell_charges.total_charges)
            turnover = float(entry_price * quantity)
            tax_friction_ratio = total_charges / turnover if turnover > 0 else 0.0025
            total_slippage_ratio = 2.0 * self.slippage_pct
            return tax_friction_ratio + total_slippage_ratio
        except Exception as exc:
            logger.debug("Tax calculation fallback used: %s", exc)
            return 0.0035

    def compute_stock_targets(self, df_stock: pd.DataFrame) -> pd.DataFrame:
        """
        Computes forward-return targets for a single stock DataFrame.
        Input DataFrame must be sorted ascending by session_date with columns:
          ['session_date', 'open_raw', 'close_raw', 'open_adj', 'close_adj']
        Returns DataFrame with additional target columns:
          target_return_{h}d: Continuous net return
          target_binary_{h}d: Binary indicator I(R_{net} > tau_h)
          forward_exit_date_{h}d: Date of the forward exit session
        """
        if df_stock.empty:
            return pd.DataFrame()

        df = df_stock.sort_values("session_date").reset_index(drop=True).copy()
        n = len(df)

        # Realistic execution assumption:
        # Features known at EOD session t -> order placed for next session open O_{t+1}.
        # Next-session raw and adjusted open:
        next_open_raw = df["open_raw"].shift(-1)
        next_open_adj = df["open_adj"].shift(-1)

        for h, config in self.target_configs.items():
            # Exit session is t + h:
            exit_close_raw = df["close_raw"].shift(-h)
            exit_close_adj = df["close_adj"].shift(-h)
            exit_session_date = df["session_date"].shift(-h)

            ret_raw_list = []
            ret_net_list = []
            binary_target_list = []

            for i in range(n):
                o_next_raw = next_open_raw.iloc[i]
                c_exit_raw = exit_close_raw.iloc[i]
                o_next_adj = next_open_adj.iloc[i]
                c_exit_adj = exit_close_adj.iloc[i]

                # If forward horizon is incomplete (beyond available dataset), leave as NaN
                if pd.isna(o_next_adj) or pd.isna(c_exit_adj) or o_next_adj <= 0:
                    ret_raw_list.append(np.nan)
                    ret_net_list.append(np.nan)
                    binary_target_list.append(np.nan)
                    continue

                # Forward return using point-in-time adjusted prices (neutralizes forward splits/bonuses)
                ret_abs = (c_exit_adj - o_next_adj) / o_next_adj

                # Transaction friction calculated using raw trading prices
                cost_ratio = self.compute_round_trip_cost_ratio(
                    entry_price=float(o_next_raw) if pd.notna(o_next_raw) and o_next_raw > 0 else float(o_next_adj),
                    exit_price=float(c_exit_raw) if pd.notna(c_exit_raw) and c_exit_raw > 0 else float(c_exit_adj),
                )

                ret_net = ret_abs - cost_ratio
                binary_label = 1 if ret_net > config.hurdle_rate else 0

                ret_raw_list.append(ret_abs)
                ret_net_list.append(ret_net)
                binary_target_list.append(binary_label)

            df[f"target_return_abs_{h}d"] = ret_raw_list
            df[f"target_return_net_{h}d"] = ret_net_list
            df[f"target_binary_{h}d"] = binary_target_list
            df[f"target_exit_date_{h}d"] = exit_session_date

        return df

    def transform_universe_targets(self, df_canonical: pd.DataFrame) -> pd.DataFrame:
        """
        Computes forward-looking targets across an entire multi-stock universe DataFrame.
        Groups by symbol to ensure shifts and forward horizons are strictly per-stock.
        """
        if df_canonical.empty:
            return pd.DataFrame()

        processed_dfs = []
        for _symbol, group in df_canonical.groupby("symbol", sort=False):
            stock_targets = self.compute_stock_targets(group)
            processed_dfs.append(stock_targets)

        return pd.concat(processed_dfs, ignore_index=True)
