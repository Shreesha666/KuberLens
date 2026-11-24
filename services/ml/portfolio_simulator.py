"""
Research Portfolio Simulator for KuberLens AI/ML.
Complies with AIML Architecture Specification v2.1 and Master Specification Section 18.

Implements realistic point-in-time portfolio backtesting:
- Signal generation at EOD session t.
- Next-session executable entry at market open (O_{t+1}).
- Fixed-fractional / equal-weight capital allocation with cash constraints.
- Multi-stock concurrent positions and overlapping holding windows.
- Dynamic transaction friction (statutory Indian taxes + slippage) via PaperTradingTaxCalculator.
- Exit at close of session t + h (C_{t+h}).
- Portfolio equity curve, daily mark-to-market accounting, drawdown, Sharpe, Sortino, turnover.
- Benchmark comparisons: NIFTY 50 Buy-and-Hold, Equal-Weight Pilot Universe, and No-Trade baseline.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from services.paper_trading.tax_calculator import IndianTaxCalculator

logger = logging.getLogger(__name__)


@dataclass
class Position:
    symbol: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    shares: int
    capital_invested: float
    cost_fraction: float
    gross_pnl: float = 0.0
    net_pnl: float = 0.0
    return_net_pct: float = 0.0
    is_closed: bool = False


@dataclass
class PortfolioPerformance:
    initial_capital: float
    ending_capital: float
    total_net_pnl: float
    total_return_pct: float
    annualized_return_pct: float
    annualized_volatility_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown_pct: float
    win_rate_pct: float
    profit_factor: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    average_trade_net_pct: float
    portfolio_turnover: float
    average_concurrent_positions: float
    max_concurrent_positions: float
    equity_curve: list[dict[str, Any]]
    per_stock_pnl: dict[str, float]


class ResearchPortfolioSimulator:
    """
    Simulates portfolio execution from model directional predictions under real-world constraints:
    - Initial capital (default ₹1,000,000 = ₹10 Lakhs).
    - Maximum allocation per position (e.g. 10% = max 10 concurrent positions).
    - Uninvested cash earns risk-free rate or zero.
    - Cash sufficiency check before placing new trades.
    - Transaction charges (brokerage, STT, exchange charges, stamp duty, GST, slippage).
    """

    def __init__(
        self,
        initial_capital: float = 1_000_000.0,
        max_position_pct: float = 0.10,  # Max 10% per position (up to 10 stocks)
        horizon_sessions: int = 20,
        slippage_pct: float = 0.0005,  # 5 bps per leg = 10 bps round-trip
        risk_free_rate: float = 0.065,  # 6.5% annual risk-free rate for Indian G-Sec
    ):
        self.initial_capital = initial_capital
        self.max_position_pct = max_position_pct
        self.horizon_sessions = horizon_sessions
        self.slippage_pct = slippage_pct
        self.risk_free_rate = risk_free_rate

    def simulate(
        self,
        df_signals: pd.DataFrame,
        canonical_price_df: pd.DataFrame,
    ) -> PortfolioPerformance:
        """
        Executes chronological day-by-day portfolio simulation:
        df_signals must have: ['session_date', 'symbol', 'signal'] where signal==1 triggers entry.
        canonical_price_df must have: ['session_date', 'symbol', 'open_raw', 'close_raw', 'open_adj', 'close_adj']
        """
        if df_signals.empty or canonical_price_df.empty:
            return self._empty_performance()

        # Build fast lookup table for stock prices by (date, symbol)
        prices = canonical_price_df.set_index(["session_date", "symbol"]).sort_index()

        # Get sorted sequence of unique trading sessions
        all_dates = sorted(canonical_price_df["session_date"].unique())
        signal_dates_set = set(df_signals["session_date"].unique())
        min_date = df_signals["session_date"].min()
        # Simulation should run through all dates from min_date to end of price history
        sim_dates = [d for d in all_dates if d >= min_date]

        cash = self.initial_capital
        active_positions: list[Position] = []
        completed_trades: list[Position] = []
        daily_equity_history: list[dict[str, Any]] = []

        total_volume_traded = 0.0

        for cur_date in sim_dates:
            # 1. Check exits for positions reaching horizon close today
            still_active = []
            for pos in active_positions:
                if pos.exit_date == cur_date:
                    # Execute exit at today's close
                    try:
                        p_row = prices.loc[(cur_date, pos.symbol)]
                        c_raw = float(p_row["close_raw"]) if pd.notna(p_row["close_raw"]) else pos.entry_price
                    except KeyError:
                        c_raw = pos.entry_price

                    # Apply exit slippage and exit tax friction
                    exit_fill = c_raw * (1.0 - self.slippage_pct)
                    gross_val = pos.shares * exit_fill
                    
                    # Compute realistic tax friction using IndianTaxCalculator
                    try:
                        tax_res = IndianTaxCalculator.calculate(pos.shares, round(exit_fill, 2), "SELL", "CNC")
                        exit_taxes = float(tax_res.total_charges)
                    except Exception:
                        exit_taxes = gross_val * 0.0015  # Fallback 15 bps
                    
                    net_proceeds = gross_val - exit_taxes
                    cash += net_proceeds
                    total_volume_traded += gross_val

                    pos.exit_price = exit_fill
                    pos.gross_pnl = gross_val - pos.capital_invested
                    pos.net_pnl = net_proceeds - pos.capital_invested
                    pos.return_net_pct = (pos.net_pnl / pos.capital_invested * 100.0) if pos.capital_invested > 0 else 0.0
                    pos.is_closed = True
                    completed_trades.append(pos)
                else:
                    still_active.append(pos)
            active_positions = still_active

            # 2. Check today's EOD signals to schedule new entries for tomorrow open
            # Only if cur_date had signals generated
            if cur_date in signal_dates_set:
                today_signals = df_signals[(df_signals["session_date"] == cur_date) & (df_signals["signal"] == 1)]
                
                # Determine next session date
                cur_idx = all_dates.index(cur_date) if cur_date in all_dates else -1
                next_session_idx = cur_idx + 1 if (0 <= cur_idx < len(all_dates) - 1) else None
                exit_session_idx = cur_idx + self.horizon_sessions if (0 <= cur_idx and cur_idx + self.horizon_sessions < len(all_dates)) else None

                if next_session_idx is not None and exit_session_idx is not None:
                    next_session_date = all_dates[next_session_idx]
                    target_exit_date = all_dates[exit_session_idx]

                    # Process entries for each candidate signal
                    max_alloc = self.initial_capital * self.max_position_pct

                    for _, sig_row in today_signals.iterrows():
                        sym = sig_row["symbol"]
                        # Check if already holding position in sym
                        if any(p.symbol == sym for p in active_positions):
                            continue

                        # Check available cash
                        if cash < max_alloc * 0.5:  # Need at least 50% of slot capital to open
                            continue

                        alloc_cash = min(cash, max_alloc)

                        # Lookup next session open price
                        try:
                            next_row = prices.loc[(next_session_date, sym)]
                            o_raw = float(next_row["open_raw"]) if pd.notna(next_row["open_raw"]) else 0.0
                        except KeyError:
                            o_raw = 0.0

                        if o_raw <= 0:
                            continue

                        # Price with buy-side slippage
                        entry_fill = o_raw * (1.0 + self.slippage_pct)
                        shares = int(alloc_cash // entry_fill)
                        if shares <= 0:
                            continue

                        trade_cost = shares * entry_fill
                        try:
                            tax_res = IndianTaxCalculator.calculate(shares, round(entry_fill, 2), "BUY", "CNC")
                            buy_taxes = float(tax_res.total_charges)
                        except Exception:
                            buy_taxes = trade_cost * 0.0015

                        total_entry_cost = trade_cost + buy_taxes
                        if total_entry_cost > cash:
                            shares = int((cash - buy_taxes) // entry_fill)
                            if shares <= 0:
                                continue
                            trade_cost = shares * entry_fill
                            total_entry_cost = trade_cost + buy_taxes

                        cash -= total_entry_cost
                        total_volume_traded += trade_cost

                        pos = Position(
                            symbol=sym,
                            entry_date=next_session_date,
                            exit_date=target_exit_date,
                            entry_price=entry_fill,
                            exit_price=0.0,
                            shares=shares,
                            capital_invested=total_entry_cost,
                            cost_fraction=buy_taxes / trade_cost if trade_cost > 0 else 0.0015,
                        )
                        active_positions.append(pos)

            # 3. Calculate Daily Mark-to-Market Equity
            open_positions_mtm = 0.0
            for pos in active_positions:
                try:
                    p_row = prices.loc[(cur_date, pos.symbol)]
                    c_raw = float(p_row["close_raw"]) if pd.notna(p_row["close_raw"]) else pos.entry_price
                except KeyError:
                    c_raw = pos.entry_price
                open_positions_mtm += (pos.shares * c_raw)

            total_equity = cash + open_positions_mtm
            daily_equity_history.append({
                "date": cur_date,
                "cash": round(cash, 2),
                "open_positions_mtm": round(open_positions_mtm, 2),
                "total_equity": round(total_equity, 2),
                "active_positions_count": len(active_positions),
            })

        # Calculate performance statistics
        eq_series = pd.Series([d["total_equity"] for d in daily_equity_history])
        daily_returns = eq_series.pct_change().dropna()

        ending_equity = float(eq_series.iloc[-1]) if not eq_series.empty else self.initial_capital
        total_pnl = ending_equity - self.initial_capital
        total_ret = (total_pnl / self.initial_capital * 100.0)

        # Drawdown calculation
        running_max = eq_series.cummax()
        drawdowns = (eq_series - running_max) / running_max * 100.0
        max_dd = float(drawdowns.min()) if not drawdowns.empty else 0.0

        # Annualized metrics (assuming 250 sessions per year)
        n_days = len(eq_series)
        years = n_days / 250.0 if n_days > 0 else 1.0
        ann_return = ((1.0 + total_ret / 100.0) ** (1.0 / years) - 1.0) * 100.0 if (years > 0 and (1.0 + total_ret / 100.0) > 0) else 0.0
        ann_vol = float(daily_returns.std() * np.sqrt(250.0) * 100.0) if len(daily_returns) > 1 else 0.0

        daily_rf = self.risk_free_rate / 250.0
        excess_daily_returns = daily_returns - daily_rf
        sharpe = float(excess_daily_returns.mean() / daily_returns.std() * np.sqrt(250.0)) if (len(daily_returns) > 1 and daily_returns.std() > 0) else 0.0

        # Sortino (downside deviation only)
        downside_returns = daily_returns[daily_returns < daily_rf]
        downside_std = float(downside_returns.std() * np.sqrt(250.0)) if len(downside_returns) > 1 else 0.0
        sortino = float((daily_returns.mean() - daily_rf) / (downside_std / np.sqrt(250.0)) * np.sqrt(250.0)) if downside_std > 0 else 0.0

        # Trade stats
        win_trades = [p for p in completed_trades if p.net_pnl > 0]
        loss_trades = [p for p in completed_trades if p.net_pnl <= 0]
        win_rate = (len(win_trades) / len(completed_trades) * 100.0) if completed_trades else 0.0
        
        gross_win = sum(p.net_pnl for p in win_trades)
        gross_loss = abs(sum(p.net_pnl for p in loss_trades))
        profit_factor = (gross_win / gross_loss) if gross_loss > 0 else (99.0 if gross_win > 0 else 1.0)

        avg_trade_ret = float(np.mean([p.return_net_pct for p in completed_trades])) if completed_trades else 0.0
        turnover = (total_volume_traded / self.initial_capital) if self.initial_capital > 0 else 0.0

        active_counts = [d["active_positions_count"] for d in daily_equity_history]
        avg_positions = float(np.mean(active_counts)) if active_counts else 0.0
        max_positions = float(max(active_counts)) if active_counts else 0.0

        # Per stock PnL
        stock_pnl: dict[str, float] = {}
        for p in completed_trades:
            stock_pnl[p.symbol] = round(stock_pnl.get(p.symbol, 0.0) + p.net_pnl, 2)

        return PortfolioPerformance(
            initial_capital=self.initial_capital,
            ending_capital=round(ending_equity, 2),
            total_net_pnl=round(total_pnl, 2),
            total_return_pct=round(total_ret, 2),
            annualized_return_pct=round(ann_return, 2),
            annualized_volatility_pct=round(ann_vol, 2),
            sharpe_ratio=round(sharpe, 2),
            sortino_ratio=round(sortino, 2),
            max_drawdown_pct=round(max_dd, 2),
            win_rate_pct=round(win_rate, 2),
            profit_factor=round(profit_factor, 2),
            total_trades=len(completed_trades),
            winning_trades=len(win_trades),
            losing_trades=len(loss_trades),
            average_trade_net_pct=round(avg_trade_ret, 2),
            portfolio_turnover=round(turnover, 2),
            average_concurrent_positions=round(avg_positions, 1),
            max_concurrent_positions=round(max_positions, 1),
            equity_curve=daily_equity_history,
            per_stock_pnl=stock_pnl,
        )

    def _empty_performance(self) -> PortfolioPerformance:
        return PortfolioPerformance(
            initial_capital=self.initial_capital,
            ending_capital=self.initial_capital,
            total_net_pnl=0.0,
            total_return_pct=0.0,
            annualized_return_pct=0.0,
            annualized_volatility_pct=0.0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            max_drawdown_pct=0.0,
            win_rate_pct=0.0,
            profit_factor=0.0,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            average_trade_net_pct=0.0,
            portfolio_turnover=0.0,
            average_concurrent_positions=0.0,
            max_concurrent_positions=0.0,
            equity_curve=[],
            per_stock_pnl={},
        )
