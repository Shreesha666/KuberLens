"""
Unit and Integration Tests for Strategy Backtesting Engine (Phase 9).
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import CustomUser
from apps.backtesting.models import BacktestRun, BacktestStatus, BacktestStrategy, StrategyType
from apps.backtesting.views import ensure_system_strategies
from apps.instruments.models import Exchange, ExchangeListing, Instrument
from apps.market.models import HistoricalCandle, MarketQuote
from services.backtesting.engine import BacktestEngine


@pytest.mark.django_db
class TestBacktestingEngine:
    @pytest.fixture(autouse=True)
    def setup_data(self, client):
        self.client = client
        self.user = CustomUser.objects.create_user(
            username="backtestuser",
            email="backtestuser@example.com",
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
            market_cap_category="LARGE",
        )
        self.listing = ExchangeListing.objects.create(
            instrument=self.inst,
            exchange=self.exchange,
            symbol="RELIANCE",
            trading_symbol="RELIANCE-EQ",
            is_primary=True,
            is_tradeable=True,
        )
        self.quote = MarketQuote.objects.create(
            listing=self.listing,
            price=Decimal("2500.00"),
            change=Decimal("20.00"),
            change_percent=Decimal("0.80"),
            open=Decimal("2490.00"),
            high=Decimal("2515.00"),
            low=Decimal("2480.00"),
            close=Decimal("2500.00"),
            previous_close=Decimal("2480.00"),
            volume=1500000,
            source_timestamp=timezone.now(),
            retrieved_at=timezone.now(),
        )

        # Seed 70 historical daily candles with trending up prices
        now = timezone.now()
        base_price = 2000.0
        for i in range(70, 0, -1):
            c_timestamp = now - timedelta(days=i)
            # Create a gradual trend with occasional pullbacks
            p = base_price + (70 - i) * 8.0 + (5.0 if i % 2 == 0 else -3.0)
            HistoricalCandle.objects.create(
                listing=self.listing,
                timestamp=c_timestamp,
                interval="1d",
                open=Decimal(str(round(p - 4, 2))),
                high=Decimal(str(round(p + 10, 2))),
                low=Decimal(str(round(p - 6, 2))),
                close=Decimal(str(round(p, 2))),
                volume=100000 + i * 1000,
                source_provider="TEST",
            )

    def test_ensure_system_strategies(self):
        ensure_system_strategies()
        assert BacktestStrategy.objects.filter(is_system_preset=True).count() >= 4
        assert BacktestStrategy.objects.filter(strategy_type=StrategyType.SMA_CROSSOVER).exists()
        assert BacktestStrategy.objects.filter(strategy_type=StrategyType.RSI_MEAN_REVERSION).exists()

    def test_backtest_simulation_execution(self):
        ensure_system_strategies()
        strategy = BacktestStrategy.objects.filter(strategy_type=StrategyType.SMA_CROSSOVER).first()
        today = timezone.now().date()
        start_date = today - timedelta(days=65)

        run = BacktestEngine.run_simulation(
            user=self.user,
            strategy=strategy,
            listing=self.listing,
            start_date=start_date,
            end_date=today,
            initial_capital=Decimal("100000.00"),
            stop_loss_pct=Decimal("3.00"),
            target_pct=Decimal("6.00"),
            slippage_pct=Decimal("0.050"),
            brokerage_pct=Decimal("0.030"),
        )

        assert run.status == BacktestStatus.COMPLETED
        assert run.initial_capital == Decimal("100000.00")
        assert run.final_capital > Decimal("0.00")
        assert isinstance(run.trades_log, list)
        assert isinstance(run.equity_curve, list)
        assert len(run.equity_curve) > 0
        assert run.user == self.user

    def test_backtest_dashboard_view_get(self):
        url = reverse("backtesting:dashboard")
        resp = self.client.get(url)
        assert resp.status_code == 200
        assert "Quantitative Strategy Backtester" in resp.content.decode()

    def test_backtest_dashboard_view_htmx(self):
        url = reverse("backtesting:dashboard")
        resp = self.client.get(url, HTTP_HX_REQUEST="true")
        assert resp.status_code == 200
        assert "Simulate Quantitative Strategy" in resp.content.decode()

    def test_backtest_dashboard_view_post_simulation(self):
        ensure_system_strategies()
        strategy = BacktestStrategy.objects.first()
        url = reverse("backtesting:dashboard")

        post_data = {
            "strategy_id": str(strategy.id),
            "symbol": "RELIANCE",
            "initial_capital": "100000",
            "stop_loss_pct": "3.5",
            "target_pct": "7.0",
            "slippage_pct": "0.05",
            "brokerage_pct": "0.03",
        }
        resp = self.client.post(url, post_data)
        assert resp.status_code == 302
        assert "/backtesting/?run_id=" in resp.url
        assert BacktestRun.objects.filter(user=self.user).exists()

    def test_backtest_run_detail_view(self):
        ensure_system_strategies()
        strategy = BacktestStrategy.objects.first()
        today = timezone.now().date()
        run = BacktestEngine.run_simulation(
            user=self.user,
            strategy=strategy,
            listing=self.listing,
            start_date=today - timedelta(days=60),
            end_date=today,
            initial_capital=Decimal("100000.00"),
        )

        url = reverse("backtesting:run_detail", kwargs={"pk": run.id})
        resp = self.client.get(url)
        assert resp.status_code == 200
        assert "Complete Trade Execution Audit" in resp.content.decode()

