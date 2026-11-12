"""
Report Generation Service.
Complies with Master Specification Section 23.
Produces institutional CSV exports and printable tear-sheets with standardized metadata,
data sources, execution timestamps, and explicit analytical assumptions.
"""
import csv
import io
import logging
from typing import Any

from django.utils import timezone

from apps.backtesting.models import BacktestRun
from apps.fundamental_analysis.models import FundamentalSnapshot
from apps.holdings.models import Holding
from apps.instruments.models import ExchangeListing
from apps.market.models import MarketQuote
from apps.portfolio.models import Portfolio
from apps.reports.models import ReportType
from apps.technical_analysis.models import TechnicalIndicatorSnapshot
from apps.trading.models import TradeJournal, TradeSetup
from apps.watchlists.models import Watchlist, WatchlistItem

logger = logging.getLogger(__name__)


class ReportGenerator:
    """
    Central report compilation and formatting engine.
    """

    @classmethod
    def _build_metadata_header(cls, title: str, period: str = "All Available", assumptions: str = "") -> list[str]:
        now = timezone.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        default_assumptions = (
            assumptions or "Standard STT/brokerage deducted on executions; FIFO lot matching; prices in INR."
        )
        return [
            "# ==============================================================================",
            "# INDIAN STOCK MARKET RESEARCH & INTELLIGENCE PLATFORM",
            f"# Title: {title}",
            f"# Generated At: {now}",
            "# System Data Sources: NSE India Official Bhavcopy, Jugaad-Data, Technical Indicators Engine v1.0",
            f"# Period: {period}",
            f"# Analytical Assumptions: {default_assumptions}",
            "# Regulatory Notice: Research opinion based on historical data. Not financial advice.",
            "# ==============================================================================",
            "",
        ]

    @classmethod
    def generate_csv(cls, user, report_type: str, **kwargs) -> tuple[str, str, int]:
        """
        Generates formatted CSV string and returns (filename, csv_text, row_count).
        """
        output = io.StringIO()

        if report_type in (ReportType.PORTFOLIO_TEARSHEET, ReportType.HOLDINGS_ANALYSIS):
            filename = f"portfolio_holdings_{timezone.now().strftime('%Y%m%d_%H%M')}.csv"
            header_lines = cls._build_metadata_header("Portfolio Holdings & Lot Allocation Analysis")
            for line in header_lines:
                output.write(line + "\n")

            writer = csv.writer(output)
            writer.writerow([
                "Symbol",
                "Company Name",
                "Sector",
                "Quantity",
                "Average Buy Price (INR)",
                "Current Price (INR)",
                "Invested Amount (INR)",
                "Current Value (INR)",
                "Unrealized P&L (INR)",
                "Unrealized Return (%)",
            ])

            portfolio = Portfolio.objects.filter(user=user).first()
            holdings = Holding.objects.filter(portfolio=portfolio).select_related(
                "listing__instrument"
            ).order_by("-current_value") if portfolio else []

            row_count = 0
            for h in holdings:
                writer.writerow([
                    h.listing.symbol,
                    h.listing.instrument.display_name,
                    h.listing.instrument.sector or "N/A",
                    h.total_quantity,
                    f"{h.average_buy_price:.2f}",
                    f"{h.current_price:.2f}",
                    f"{h.invested_amount:.2f}",
                    f"{h.current_value:.2f}",
                    f"{h.unrealised_pnl:.2f}",
                    f"{h.unrealised_pnl_percent:.2f}",
                ])
                row_count += 1
            return filename, output.getvalue(), row_count

        elif report_type == ReportType.SWING_SETUPS:
            filename = f"swing_trade_setups_{timezone.now().strftime('%Y%m%d_%H%M')}.csv"
            header_lines = cls._build_metadata_header("Swing Trade Scanner Opportunities")
            for line in header_lines:
                output.write(line + "\n")

            writer = csv.writer(output)
            writer.writerow([
                "Symbol",
                "Company Name",
                "Setup Type",
                "Entry Min (INR)",
                "Stop Loss (INR)",
                "Target Price (INR)",
                "Risk / Reward",
                "Identified Date",
            ])

            setups = TradeSetup.objects.select_related("listing__instrument").filter(status="ACTIVE")
            row_count = 0
            for s in setups:
                rr = f"1:{s.risk_reward_ratio:.2f}" if s.risk_reward_ratio else "N/A"
                writer.writerow([
                    s.listing.symbol,
                    s.listing.instrument.display_name,
                    s.strategy,
                    f"{s.entry_min:.2f}",
                    f"{s.stop_loss:.2f}",
                    f"{s.target_1:.2f}",
                    rr,
                    s.setup_timestamp.strftime("%Y-%m-%d"),
                ])
                row_count += 1
            return filename, output.getvalue(), row_count

        elif report_type == ReportType.TRADE_JOURNAL:
            filename = f"trade_journal_audit_{timezone.now().strftime('%Y%m%d_%H%M')}.csv"
            header_lines = cls._build_metadata_header("Trade Journal Execution & Review Audit")
            for line in header_lines:
                output.write(line + "\n")

            writer = csv.writer(output)
            writer.writerow([
                "Symbol",
                "Strategy",
                "Status",
                "Entry Date",
                "Entry Price (INR)",
                "Quantity",
                "Exit Date",
                "Exit Price (INR)",
                "Exit Reason",
                "Realized P&L (INR)",
                "Return (%)",
                "Holding Days",
            ])

            trades = TradeJournal.objects.filter(user=user).select_related("listing__instrument").order_by("-entry_date")
            row_count = 0
            for t in trades:
                exit_d = t.exit_date.strftime("%Y-%m-%d") if t.exit_date else "Open"
                exit_p = f"{t.exit_price:.2f}" if t.exit_price else "—"
                pnl = f"{t.realised_pnl:.2f}" if t.realised_pnl is not None else "—"
                pnl_pct = f"{t.realised_pnl_percent:.2f}" if t.realised_pnl_percent is not None else "—"
                holding_days = (t.exit_date - t.entry_date).days if (t.exit_date and t.entry_date) else 0
                writer.writerow([
                    t.listing.symbol,
                    t.strategy,
                    t.get_status_display(),
                    t.entry_date.strftime("%Y-%m-%d"),
                    f"{t.entry_price:.2f}",
                    t.quantity,
                    exit_d,
                    exit_p,
                    t.exit_reason or "—",
                    pnl,
                    pnl_pct,
                    holding_days,
                ])
                row_count += 1
            return filename, output.getvalue(), row_count

        elif report_type == ReportType.BACKTEST_SUMMARY:
            filename = f"backtest_performance_{timezone.now().strftime('%Y%m%d_%H%M')}.csv"
            header_lines = cls._build_metadata_header("Quantitative Strategy Backtest Performance Summary")
            for line in header_lines:
                output.write(line + "\n")

            writer = csv.writer(output)
            writer.writerow([
                "Strategy Name",
                "Symbol",
                "Tested Window",
                "Initial Capital (INR)",
                "Final Capital (INR)",
                "Total Return (%)",
                "CAGR (%)",
                "Max Drawdown (%)",
                "Win Rate (%)",
                "Profit Factor",
                "Total Trades",
            ])

            runs = BacktestRun.objects.filter(user=user).select_related("strategy", "listing").order_by("-created_at")
            row_count = 0
            for r in runs:
                window = f"{r.start_date} to {r.end_date}"
                writer.writerow([
                    r.strategy.name,
                    r.listing.symbol,
                    window,
                    f"{r.initial_capital:.2f}",
                    f"{r.final_capital:.2f}",
                    f"{r.total_return_pct:.2f}",
                    f"{r.cagr_pct:.2f}",
                    f"{r.max_drawdown_pct:.2f}",
                    f"{r.win_rate_pct:.2f}",
                    f"{r.profit_factor:.2f}",
                    r.total_trades,
                ])
                row_count += 1
            return filename, output.getvalue(), row_count

        elif report_type == ReportType.WATCHLIST_SUMMARY:
            filename = f"watchlist_summary_{timezone.now().strftime('%Y%m%d_%H%M')}.csv"
            header_lines = cls._build_metadata_header("Watchlist Tracking & Price Action Summary")
            for line in header_lines:
                output.write(line + "\n")

            writer = csv.writer(output)
            writer.writerow([
                "Watchlist",
                "Symbol",
                "Company Name",
                "Added Date",
                "Added Price (INR)",
                "Current Price (INR)",
                "Return Since Added (%)",
            ])

            items = WatchlistItem.objects.filter(watchlist__user=user).select_related(
                "watchlist", "listing__instrument"
            ).order_by("watchlist__name", "listing__symbol")

            row_count = 0
            for it in items:
                writer.writerow([
                    it.watchlist.name,
                    it.listing.symbol,
                    it.listing.instrument.display_name,
                    it.created_at.strftime("%Y-%m-%d"),
                    f"{it.price_at_addition:.2f}" if it.price_at_addition else "—",
                    f"{it.current_price:.2f}" if it.current_price else "—",
                    f"{it.return_since_added:.2f}" if it.return_since_added else "0.00",
                ])
                row_count += 1
            return filename, output.getvalue(), row_count

        else:
            # Default / Generic fallback
            filename = f"report_{timezone.now().strftime('%Y%m%d_%H%M')}.csv"
            header_lines = cls._build_metadata_header("Standard Data Export")
            for line in header_lines:
                output.write(line + "\n")
            return filename, output.getvalue(), 0

    @classmethod
    def get_printable_context(cls, user, report_type: str, symbol: str | None = None) -> dict[str, Any]:
        """
        Prepares rich view context for clean printable HTML tear-sheets.
        """
        now = timezone.now()
        portfolio = Portfolio.objects.filter(user=user).first()
        holdings = Holding.objects.filter(portfolio=portfolio).select_related(
            "listing__instrument"
        ).order_by("-current_value") if portfolio else []

        stock_data = None
        if symbol:
            try:
                listing = ExchangeListing.objects.filter(symbol=symbol).select_related("instrument", "exchange").first()
                if listing:
                    quote = MarketQuote.objects.filter(listing=listing).first()
                    tech = TechnicalIndicatorSnapshot.objects.filter(listing=listing).first()
                    fund = FundamentalSnapshot.objects.filter(instrument=listing.instrument).first()
                    stock_data = {
                        "listing": listing,
                        "quote": quote,
                        "technical": tech,
                        "fundamental": fund,
                    }
            except Exception as e:
                logger.warning("Could not gather stock data for %s: %s", symbol, e)

        return {
            "user": user,
            "report_type": report_type,
            "title": dict(ReportType.choices).get(report_type, "Research Report"),
            "generated_at": now,
            "portfolio": portfolio,
            "holdings": holdings,
            "stock_data": stock_data,
            "recent_runs": BacktestRun.objects.filter(user=user).select_related("strategy", "listing")[:5],
            "swing_setups": TradeSetup.objects.select_related("listing__instrument").filter(status="ACTIVE")[:10],
            "watchlists": Watchlist.objects.filter(user=user).prefetch_related("items__listing"),
        }
