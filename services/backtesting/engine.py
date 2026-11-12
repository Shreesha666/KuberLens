"""
Quantitative Strategy Backtesting Engine.
Complies with Master Specification Section 21.
Runs step-by-step time-series simulations without look-ahead bias,
factoring in realistic fills, slippage, and brokerage transaction costs.
"""
import logging
from datetime import date
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd

from apps.backtesting.models import BacktestRun, BacktestStatus, BacktestStrategy, StrategyType
from apps.instruments.models import ExchangeListing
from apps.market.models import HistoricalCandle

logger = logging.getLogger(__name__)


class BacktestEngine:
    """
    Deterministic chronological simulation engine for historical equity strategies.
    """

    @classmethod
    def run_simulation(
        cls,
        user,
        strategy: BacktestStrategy,
        listing: ExchangeListing,
        start_date: date,
        end_date: date,
        initial_capital: Decimal = Decimal("100000.00"),
        stop_loss_pct: Decimal | None = None,
        target_pct: Decimal | None = None,
        slippage_pct: Decimal | None = None,
        brokerage_pct: Decimal | None = None,
    ) -> BacktestRun:
        """
        Executes a historical backtest run over the specified date window.
        """
        sl_pct = float(stop_loss_pct or strategy.stop_loss_pct) / 100.0
        tp_pct = float(target_pct or strategy.target_pct) / 100.0
        slip = float(slippage_pct or strategy.slippage_pct) / 100.0
        comm = float(brokerage_pct or strategy.brokerage_pct) / 100.0

        candles = HistoricalCandle.objects.filter(
            listing=listing,
            interval__iexact="1d",
            timestamp__date__gte=start_date,
            timestamp__date__lte=end_date,
        ).order_by("timestamp")

        if candles.count() < 25:
            # Expand to all available candles for this listing if date range was too narrow
            candles = HistoricalCandle.objects.filter(
                listing=listing,
                interval__iexact="1d",
            ).order_by("timestamp")

        if candles.count() < 20:
            raise ValueError(f"Insufficient historical candle data for {listing.symbol} to backtest.")

        # Build pandas DataFrame
        records = [
            {
                "date": c.timestamp.date(),
                "open": float(c.open),
                "high": float(c.high),
                "low": float(c.low),
                "close": float(c.close),
                "volume": c.volume,
            }
            for c in candles
        ]
        df = pd.DataFrame(records)
        df = df.sort_values("date").reset_index(drop=True)

        # 1. Compute Indicators Chronologically
        df["sma_20"] = df["close"].rolling(window=20, min_periods=15).mean()
        df["sma_50"] = df["close"].rolling(window=50, min_periods=30).mean()

        # RSI 14
        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14, min_periods=10).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14, min_periods=10).mean()
        rs = gain / (loss.replace(0, np.nan))
        df["rsi_14"] = 100 - (100 / (1 + rs))
        df["rsi_14"] = df["rsi_14"].fillna(50.0)

        # 20-Day Breakout High
        df["high_20"] = df["high"].shift(1).rolling(window=20, min_periods=10).max()

        # MACD (12, 26, 9)
        exp12 = df["close"].ewm(span=12, adjust=False).mean()
        exp26 = df["close"].ewm(span=26, adjust=False).mean()
        df["macd"] = exp12 - exp26
        df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()

        # 2. Chronological Simulation Loop (Zero Lookahead Bias)
        capital = float(initial_capital)
        cash = capital
        shares = 0
        entry_price = 0.0
        entry_date: date | None = None
        trades: list[dict[str, Any]] = []
        equity_curve: list[dict[str, Any]] = []

        strat_type = strategy.strategy_type

        for i in range(len(df)):
            row = df.iloc[i]
            cur_date = row["date"]
            cur_close = row["close"]
            cur_high = row["high"]
            cur_low = row["low"]

            # Evaluate open position exits
            if shares > 0:
                exit_triggered = False
                exit_price = 0.0
                exit_reason = ""

                # Stop loss check
                stop_threshold = entry_price * (1.0 - sl_pct)
                if cur_low <= stop_threshold:
                    exit_triggered = True
                    exit_price = stop_threshold * (1.0 - slip)
                    exit_reason = "STOP_LOSS"

                # Target check
                target_threshold = entry_price * (1.0 + tp_pct)
                if not exit_triggered and cur_high >= target_threshold:
                    exit_triggered = True
                    exit_price = target_threshold * (1.0 - slip)
                    exit_reason = "TARGET"

                # Signal exit (e.g. SMA20 crosses below SMA50)
                if not exit_triggered and i > 0:
                    prev_row = df.iloc[i - 1]
                    if strat_type == StrategyType.SMA_CROSSOVER:
                        if prev_row["sma_20"] >= prev_row["sma_50"] and row["sma_20"] < row["sma_50"]:
                            exit_triggered = True
                            exit_price = cur_close * (1.0 - slip)
                            exit_reason = "SIGNAL_EXIT"
                    elif strat_type == StrategyType.RSI_MEAN_REVERSION:
                        if row["rsi_14"] >= 70.0:
                            exit_triggered = True
                            exit_price = cur_close * (1.0 - slip)
                            exit_reason = "RSI_OVERBOUGHT"

                # Force close on final bar
                if not exit_triggered and i == len(df) - 1:
                    exit_triggered = True
                    exit_price = cur_close * (1.0 - slip)
                    exit_reason = "END_OF_TEST"

                # Execute Exit
                if exit_triggered:
                    gross_proceeds = shares * exit_price
                    exit_fee = gross_proceeds * comm
                    net_proceeds = gross_proceeds - exit_fee
                    cash += net_proceeds

                    cost_basis = shares * entry_price
                    entry_fee = cost_basis * comm
                    total_fee = entry_fee + exit_fee
                    net_pnl = net_proceeds - (cost_basis + entry_fee)
                    ret_pct = (net_pnl / (cost_basis + entry_fee)) * 100.0
                    holding_days = (cur_date - entry_date).days if entry_date else 0

                    trades.append({
                        "entry_date": entry_date.isoformat() if entry_date else "",
                        "entry_price": round(entry_price, 2),
                        "exit_date": cur_date.isoformat(),
                        "exit_price": round(exit_price, 2),
                        "shares": shares,
                        "reason": exit_reason,
                        "gross_pnl": round(gross_proceeds - cost_basis, 2),
                        "fees": round(total_fee, 2),
                        "net_pnl": round(net_pnl, 2),
                        "return_pct": round(ret_pct, 2),
                        "holding_days": holding_days,
                    })

                    shares = 0
                    entry_price = 0.0
                    entry_date = None

            # Evaluate Entry (only if not already in position)
            if shares == 0 and i > 1:
                prev_row = df.iloc[i - 1]
                prev_prev = df.iloc[i - 2]
                buy_signal = False

                if strat_type == StrategyType.SMA_CROSSOVER:
                    # SMA 20 crosses above SMA 50
                    if prev_prev["sma_20"] <= prev_prev["sma_50"] and prev_row["sma_20"] > prev_row["sma_50"]:
                        buy_signal = True

                elif strat_type == StrategyType.RSI_MEAN_REVERSION:
                    # RSI was below 35 and crossed back up
                    if prev_prev["rsi_14"] < 35.0 and prev_row["rsi_14"] >= 35.0:
                        buy_signal = True

                elif strat_type == StrategyType.BREAKOUT_MOMENTUM:
                    # Close broke above 20-day high
                    if prev_row["close"] > prev_row["high_20"] if pd.notna(prev_row["high_20"]) else False:
                        buy_signal = True

                elif strat_type == StrategyType.MACD_CROSSOVER:
                    # MACD crosses above Signal
                    if prev_prev["macd"] <= prev_prev["macd_signal"] and prev_row["macd"] > prev_row["macd_signal"]:
                        buy_signal = True

                if buy_signal:
                    fill_price = cur_close * (1.0 + slip)
                    avail_capital = cash * 0.98  # 2% reserve for commissions
                    num_shares = int(avail_capital // fill_price)

                    if num_shares > 0:
                        shares = num_shares
                        entry_price = fill_price
                        entry_date = cur_date
                        entry_cost = shares * entry_price
                        fee = entry_cost * comm
                        cash -= (entry_cost + fee)

            # Record Daily Equity Snapshot
            portfolio_val = cash + (shares * cur_close)
            equity_curve.append({
                "date": cur_date.isoformat(),
                "equity": round(portfolio_val, 2),
                "in_position": shares > 0,
            })

        final_capital = cash + (shares * df.iloc[-1]["close"])
        tot_return_pct = ((final_capital - capital) / capital) * 100.0

        # 3. Compute Metrics
        days = (df.iloc[-1]["date"] - df.iloc[0]["date"]).days or 1
        years = max(days / 365.25, 0.05)
        cagr = (((final_capital / capital) ** (1.0 / years)) - 1.0) * 100.0 if final_capital > 0 else -100.0

        # Maximum Drawdown
        equities = [p["equity"] for p in equity_curve]
        peak = capital
        max_dd = 0.0
        for eq in equities:
            if eq > peak:
                peak = eq
            dd = ((peak - eq) / peak) * 100.0 if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd

        # Trade Stats
        total_trades = len(trades)
        wins = [t for t in trades if t["net_pnl"] > 0]
        losses = [t for t in trades if t["net_pnl"] <= 0]
        winning_trades = len(wins)
        losing_trades = len(losses)
        win_rate = (winning_trades / total_trades * 100.0) if total_trades > 0 else 0.0

        total_gain = sum(t["net_pnl"] for t in wins)
        total_loss = abs(sum(t["net_pnl"] for t in losses))
        profit_factor = (total_gain / total_loss) if total_loss > 0 else (total_gain if total_gain > 0 else 1.0)

        avg_profit = (sum(t["return_pct"] for t in wins) / winning_trades) if winning_trades > 0 else 0.0
        avg_loss = (sum(t["return_pct"] for t in losses) / losing_trades) if losing_trades > 0 else 0.0
        avg_holding = (sum(t["holding_days"] for t in trades) / total_trades) if total_trades > 0 else 0.0

        # Benchmark: Buy and Hold Return
        start_price = df.iloc[0]["close"]
        end_price = df.iloc[-1]["close"]
        bench_ret = ((end_price - start_price) / start_price) * 100.0 if start_price > 0 else 0.0

        # 4. Save BacktestRun record
        run = BacktestRun.objects.create(
            user=user,
            strategy=strategy,
            listing=listing,
            start_date=df.iloc[0]["date"],
            end_date=df.iloc[-1]["date"],
            initial_capital=Decimal(str(round(capital, 2))),
            final_capital=Decimal(str(round(final_capital, 2))),
            total_return_pct=Decimal(str(round(tot_return_pct, 2))),
            cagr_pct=Decimal(str(round(cagr, 2))),
            max_drawdown_pct=Decimal(str(round(max_dd, 2))),
            win_rate_pct=Decimal(str(round(win_rate, 2))),
            profit_factor=Decimal(str(round(min(profit_factor, 999.99), 2))),
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            avg_profit_pct=Decimal(str(round(avg_profit, 2))),
            avg_loss_pct=Decimal(str(round(avg_loss, 2))),
            avg_holding_days=Decimal(str(round(avg_holding, 1))),
            benchmark_return_pct=Decimal(str(round(bench_ret, 2))),
            trades_log=trades,
            equity_curve=equity_curve[::max(1, len(equity_curve) // 100)],  # sampled for frontend
            status=BacktestStatus.COMPLETED,
        )

        return run
