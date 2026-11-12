"""
Unit and Integration Tests for Phase 11: Reports & Tear-Sheets Module.
"""
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import CustomUser
from apps.backtesting.models import BacktestRun, BacktestStrategy
from apps.holdings.models import Holding
from apps.instruments.models import Exchange, ExchangeListing, Instrument
from apps.portfolio.models import Portfolio
from apps.reports.models import ExportFormat, GeneratedReport, ReportType
from apps.trading.models import TradeJournal, TradeJournalStatus, TradeSetup
from services.reports.generator import ReportGenerator


@pytest.mark.django_db
class TestReportsEngineAndViews:
    @pytest.fixture(autouse=True)
    def setup_data(self, client):
        self.client = client
        self.user = CustomUser.objects.create_user(
            username="reportuser",
            email="reportuser@example.com",
            password="testpassword123",
        )
        self.client.force_login(self.user)

        self.exchange = Exchange.objects.create(
            code="NSE", name="National Stock Exchange", country="India", currency="INR"
        )
        self.inst = Instrument.objects.create(
            isin="INE002A01018",
            display_name="RELIANCE",
            legal_name="Reliance Industries Limited",
            sector="Energy",
            industry="Oil & Gas",
        )
        self.listing = ExchangeListing.objects.create(
            instrument=self.inst,
            exchange=self.exchange,
            symbol="RELIANCE",
            trading_symbol="RELIANCE-EQ",
            is_primary=True,
            is_tradeable=True,
        )

        self.portfolio = Portfolio.objects.create(
            user=self.user,
            name="Main Research Portfolio",
        )
        self.holding = Holding.objects.create(
            portfolio=self.portfolio,
            listing=self.listing,
            total_quantity=50,
            average_buy_price=Decimal("2400.00"),
            invested_amount=Decimal("120000.00"),
            current_price=Decimal("2550.00"),
            current_value=Decimal("127500.00"),
            unrealised_pnl=Decimal("7500.00"),
            unrealised_pnl_percent=Decimal("6.25"),
        )

    def test_report_generator_portfolio_csv(self):
        filename, csv_text, count = ReportGenerator.generate_csv(
            user=self.user,
            report_type=ReportType.PORTFOLIO_TEARSHEET,
        )
        assert filename.startswith("portfolio_holdings_")
        assert count == 1
        assert "INDIAN STOCK MARKET RESEARCH" in csv_text
        assert "NSE India Official Bhavcopy" in csv_text
        assert "RELIANCE" in csv_text
        assert "127500.00" in csv_text

    def test_report_generator_swing_setups_csv(self):
        TradeSetup.objects.create(
            listing=self.listing,
            strategy="SMA_PULLBACK",
            status="ACTIVE",
            current_price=Decimal("2500.00"),
            entry_min=Decimal("2480.00"),
            entry_max=Decimal("2520.00"),
            stop_loss=Decimal("2425.00"),
            target_1=Decimal("2650.00"),
            risk_reward_ratio=Decimal("2.00"),
            setup_timestamp=timezone.now(),
        )

        filename, csv_text, count = ReportGenerator.generate_csv(
            user=self.user,
            report_type=ReportType.SWING_SETUPS,
        )
        assert filename.startswith("swing_trade_setups_")
        assert count == 1
        assert "RELIANCE" in csv_text
        assert "SMA_PULLBACK" in csv_text

    def test_report_generator_trade_journal_csv(self):
        TradeJournal.objects.create(
            user=self.user,
            listing=self.listing,
            strategy="SMA_PULLBACK",
            entry_date=timezone.now().date(),
            entry_price=Decimal("2450.00"),
            quantity=20,
            stop_loss=Decimal("2400.00"),
            target_price=Decimal("2600.00"),
            status=TradeJournalStatus.CLOSED,
            exit_date=timezone.now().date(),
            exit_price=Decimal("2600.00"),
            exit_reason="Target Hit",
            realised_pnl=Decimal("3000.00"),
            realised_pnl_percent=Decimal("6.12"),
            entry_reason="Testing trade setup",
        )

        filename, csv_text, count = ReportGenerator.generate_csv(
            user=self.user,
            report_type=ReportType.TRADE_JOURNAL,
        )
        assert filename.startswith("trade_journal_audit_")
        assert count == 1
        assert "3000.00" in csv_text
        assert "Target Hit" in csv_text

    def test_report_generator_backtest_summary_csv(self):
        strat = BacktestStrategy.objects.create(
            name="Breakout Strategy",
            stop_loss_pct=Decimal("3.00"),
            target_pct=Decimal("6.00"),
        )
        today = timezone.now().date()
        BacktestRun.objects.create(
            user=self.user,
            strategy=strat,
            listing=self.listing,
            start_date=today,
            end_date=today,
            initial_capital=Decimal("100000.00"),
            final_capital=Decimal("108500.00"),
            total_return_pct=Decimal("8.50"),
            cagr_pct=Decimal("12.00"),
            max_drawdown_pct=Decimal("2.50"),
            win_rate_pct=Decimal("65.00"),
            profit_factor=Decimal("2.10"),
            total_trades=14,
        )

        filename, csv_text, count = ReportGenerator.generate_csv(
            user=self.user,
            report_type=ReportType.BACKTEST_SUMMARY,
        )
        assert filename.startswith("backtest_performance_")
        assert count == 1
        assert "Breakout Strategy" in csv_text
        assert "8.50" in csv_text

    def test_report_generator_printable_context(self):
        ctx = ReportGenerator.get_printable_context(
            user=self.user,
            report_type=ReportType.PORTFOLIO_TEARSHEET,
            symbol="RELIANCE",
        )
        assert ctx["user"] == self.user
        assert len(ctx["holdings"]) == 1
        assert ctx["stock_data"]["listing"] == self.listing

    def test_report_center_view_get(self):
        url = reverse("reports:center")
        resp = self.client.get(url)
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "Research Reports &amp; Institutional Exports" in content or "Research Reports & Institutional Exports" in content

    def test_report_center_view_htmx(self):
        url = reverse("reports:center")
        resp = self.client.get(url, HTTP_HX_REQUEST="true")
        assert resp.status_code == 200
        assert "Compile New Report" in resp.content.decode()

    def test_report_export_view_csv(self):
        url = reverse("reports:export")
        resp = self.client.post(url, {
            "report_type": ReportType.PORTFOLIO_TEARSHEET,
            "export_format": ExportFormat.CSV,
        })
        assert resp.status_code == 200
        assert resp["Content-Type"].startswith("text/csv")
        assert "portfolio_holdings_" in resp["Content-Disposition"]

        # Audit record created
        assert GeneratedReport.objects.filter(user=self.user, export_format=ExportFormat.CSV).exists()

    def test_printable_tearsheet_view(self):
        url = f"{reverse('reports:print_tearsheet')}?type={ReportType.PORTFOLIO_TEARSHEET}"
        resp = self.client.get(url)
        assert resp.status_code == 200
        assert "CONFIDENTIAL RESEARCH" in resp.content.decode()
        assert "RELIANCE" in resp.content.decode()
