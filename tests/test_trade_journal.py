from datetime import date
from decimal import Decimal

import pytest

from apps.accounts.models import CustomUser
from apps.instruments.models import Exchange, ExchangeListing, Instrument
from apps.trading.models import TradeJournal, TradeJournalStatus


@pytest.mark.django_db
class TestTradeJournal:
    @pytest.fixture(autouse=True)
    def setup_data(self):
        self.user = CustomUser.objects.create_user(
            username="journaltrader",
            email="trader@example.com",
            password="testpassword123",
        )
        self.exchange = Exchange.objects.create(code="NSE", name="National Stock Exchange", country="India", currency="INR")
        self.inst = Instrument.objects.create(
            isin="INE999A01010",
            display_name="JOURNALTEST",
            legal_name="Journal Test Limited",
            sector="Finance",
            industry="Banking",
            market_cap_category="LARGE",
        )
        self.listing = ExchangeListing.objects.create(
            instrument=self.inst,
            exchange=self.exchange,
            symbol="JOURNALTEST",
            trading_symbol="JOURNALTEST-EQ",
            is_primary=True,
            is_tradeable=True,
        )

    def test_create_open_trade_journal_entry(self):
        trade = TradeJournal.objects.create(
            user=self.user,
            listing=self.listing,
            strategy="Pullback to 20/50 SMA",
            entry_date=date(2026, 11, 1),
            entry_price=Decimal("500.00"),
            quantity=100,
            stop_loss=Decimal("475.00"),
            target_price=Decimal("560.00"),
            entry_reason="Testing 50 SMA confluence with positive MACD.",
            checklist_completed=True,
            status=TradeJournalStatus.OPEN,
        )

        assert trade.total_invested == Decimal("50000.00")
        assert trade.total_risk == Decimal("2500.00")  # 100 * (500 - 475)
        assert trade.risk_reward_ratio == Decimal("2.40")  # (560 - 500) / (500 - 475) = 60 / 25
        assert trade.status == TradeJournalStatus.OPEN
        assert trade.realised_pnl is None

    def test_close_trade_with_profit_target_hit(self):
        trade = TradeJournal.objects.create(
            user=self.user,
            listing=self.listing,
            strategy="Consolidation Breakout",
            entry_date=date(2026, 11, 1),
            entry_price=Decimal("1000.00"),
            quantity=50,
            stop_loss=Decimal("950.00"),
            target_price=Decimal("1100.00"),
            entry_reason="Breakout on high volume.",
            checklist_completed=True,
        )

        trade.close_trade(
            exit_date=date(2026, 11, 12),
            exit_price=Decimal("1120.00"),
            exit_reason="Target achieved and exceeded",
            lessons_learned="Patience rewarded; trailed stop correctly.",
        )

        assert trade.status == TradeJournalStatus.TARGET_HIT
        assert trade.realised_pnl == Decimal("6000.00")  # 50 * (1120 - 1000)
        assert trade.realised_pnl_percent == Decimal("12.00")
        assert trade.exit_price == Decimal("1120.00")

    def test_close_trade_with_stop_loss_hit(self):
        trade = TradeJournal.objects.create(
            user=self.user,
            listing=self.listing,
            strategy="Oversold Bounce",
            entry_date=date(2026, 11, 1),
            entry_price=Decimal("200.00"),
            quantity=100,
            stop_loss=Decimal("190.00"),
            target_price=Decimal("225.00"),
            entry_reason="RSI bounce test.",
            checklist_completed=True,
        )

        trade.close_trade(
            exit_date=date(2026, 11, 5),
            exit_price=Decimal("188.00"),
            exit_reason="Stop loss hit on market gap down",
            lessons_learned="Honor stop-loss immediately without hoping.",
        )

        assert trade.status == TradeJournalStatus.STOPPED_OUT
        assert trade.realised_pnl == Decimal("-1200.00")  # 100 * (188 - 200)
        assert trade.realised_pnl_percent == Decimal("-6.00")
