from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import CustomUser
from apps.instruments.models import Exchange, ExchangeListing, Instrument
from apps.trading.models import TradeJournal, TradeJournalStatus


@pytest.mark.django_db
class TestTradingViews:
    @pytest.fixture(autouse=True)
    def setup_data(self, client):
        self.client = client
        self.user = CustomUser.objects.create_user(
            username="viewtrader",
            email="viewtrader@example.com",
            password="testpassword123",
        )
        self.client.force_login(self.user)

        self.exchange = Exchange.objects.create(code="NSE", name="National Stock Exchange", country="India", currency="INR")
        self.inst = Instrument.objects.create(
            isin="INE888A01010",
            display_name="VIEWTEST",
            legal_name="View Test Limited",
            sector="Consumer Goods",
            industry="FMCG",
            market_cap_category="LARGE",
        )
        self.listing = ExchangeListing.objects.create(
            instrument=self.inst,
            exchange=self.exchange,
            symbol="VIEWTEST",
            trading_symbol="VIEWTEST-EQ",
            is_primary=True,
            is_tradeable=True,
        )

    def test_swing_scanner_view_full_page_and_htmx(self):
        url = reverse("trading:scanner")

        # Full page
        res = self.client.get(url)
        assert res.status_code == 200
        assert "Swing Trading Hub" in res.content.decode()

        # HTMX partial
        res_htmx = self.client.get(url, HTTP_HX_REQUEST="true")
        assert res_htmx.status_code == 200
        content = res_htmx.content.decode()
        assert "Swing Trading Hub" in content
        assert "<!DOCTYPE html>" not in content

    def test_position_sizer_calculate_endpoint(self):
        url = reverse("trading:calculate_size")
        res = self.client.get(url, {
            "capital": "1000000",
            "risk_pct": "1.0",
            "entry": "500",
            "stop_loss": "475",
            "target": "575",
        })
        assert res.status_code == 200
        content = res.content.decode()
        assert "Suggested Qty" in content
        assert "Risk-to-Reward Ratio" in content

    def test_position_sizer_invalid_stop_loss_shows_warning(self):
        url = reverse("trading:calculate_size")
        res = self.client.get(url, {
            "capital": "500000",
            "risk_pct": "1.0",
            "entry": "500",
            "stop_loss": "520",  # SL above entry
        })
        assert res.status_code == 200
        assert "alert-warning" in res.content.decode()

    def test_trade_journal_view_full_page_and_htmx(self):
        url = reverse("trading:journal")

        # Full page
        res = self.client.get(url)
        assert res.status_code == 200
        assert "Swing Trading Journal" in res.content.decode()

        # HTMX partial
        res_htmx = self.client.get(url, HTTP_HX_REQUEST="true")
        assert res_htmx.status_code == 200
        assert "<!DOCTYPE html>" not in res_htmx.content.decode()

    def test_trade_journal_create_requires_checklist(self):
        """Must reject trade submission if checklist boxes are not ticked."""
        url = reverse("trading:journal_add")
        res = self.client.post(url, {
            "symbol": "VIEWTEST",
            "strategy": "Pullback to 20/50 SMA",
            "entry_date": "2026-11-12",
            "entry_price": "500.00",
            "quantity": "50",
            "stop_loss": "480.00",
            "target_price": "550.00",
            # No checklist flags passed!
        })
        assert res.status_code == 302
        assert TradeJournal.objects.count() == 0

    def test_trade_journal_create_and_close_flow(self):
        """Submitting with full checklist creates open trade; closing updates P&L."""
        add_url = reverse("trading:journal_add")
        res = self.client.post(add_url, {
            "symbol": "VIEWTEST",
            "strategy": "Pullback to 20/50 SMA",
            "entry_date": "2026-11-12",
            "entry_price": "500.00",
            "quantity": "50",
            "stop_loss": "480.00",
            "target_price": "550.00",
            "chk_rules": "on",
            "chk_risk": "on",
            "chk_earnings": "on",
            "entry_reason": "Clear 50 SMA confluence.",
        })
        assert res.status_code == 302
        assert TradeJournal.objects.count() == 1

        trade = TradeJournal.objects.first()
        assert trade.status == TradeJournalStatus.OPEN
        assert trade.total_risk == Decimal("1000.00")

        # Close trade
        close_url = reverse("trading:journal_close", kwargs={"pk": trade.id})
        res_close = self.client.post(close_url, {
            "exit_date": "2026-11-15",
            "exit_price": "540.00",
            "exit_reason": "Booked partial gains at resistance",
            "lessons_learned": "Trade played out as planned",
        })
        assert res_close.status_code == 302

        trade.refresh_from_db()
        assert trade.status == TradeJournalStatus.CLOSED
        assert trade.realised_pnl == Decimal("2000.00")  # 50 * (540 - 500)
        assert trade.realised_pnl_percent == Decimal("8.00")

    def test_trade_journal_delete(self):
        trade = TradeJournal.objects.create(
            user=self.user,
            listing=self.listing,
            strategy="Test Strategy",
            entry_date=date(2026, 11, 1),
            entry_price=Decimal("100.00"),
            quantity=10,
            stop_loss=Decimal("90.00"),
            target_price=Decimal("120.00"),
            checklist_completed=True,
        )
        delete_url = reverse("trading:journal_delete", kwargs={"pk": trade.id})
        res = self.client.post(delete_url)
        assert res.status_code == 302
        assert TradeJournal.objects.filter(id=trade.id).count() == 0
