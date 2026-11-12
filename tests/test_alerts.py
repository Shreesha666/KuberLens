"""
Tests for Alert Rules, Evaluator Engine, and Alert Views.
"""
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import CustomUser
from apps.alerts.models import AlertRule, AlertType
from apps.holdings.models import Holding
from apps.instruments.models import Exchange, ExchangeListing, Instrument
from apps.market.models import MarketQuote
from apps.notifications.models import Notification, NotificationSeverity
from apps.portfolio.models import Portfolio
from apps.technical_analysis.models import TechnicalIndicatorSnapshot
from services.alerts.evaluator import AlertEvaluator


@pytest.mark.django_db
class TestAlertEvaluatorAndViews:
    @pytest.fixture(autouse=True)
    def setup_data(self, client):
        self.client = client
        self.user = CustomUser.objects.create_user(
            username="alertuser",
            email="alertuser@example.com",
            password="testpassword123",
        )
        self.client.force_login(self.user)

        self.exchange = Exchange.objects.create(code="NSE", name="National Stock Exchange", country="India", currency="INR")
        self.inst = Instrument.objects.create(
            isin="INE009A01021",
            display_name="INFY",
            legal_name="Infosys Limited",
            sector="Technology",
            industry="IT Services",
            market_cap_category="LARGE",
        )
        self.listing = ExchangeListing.objects.create(
            instrument=self.inst,
            exchange=self.exchange,
            symbol="INFY",
            trading_symbol="INFY-EQ",
            is_primary=True,
            is_tradeable=True,
        )
        self.quote = MarketQuote.objects.create(
            listing=self.listing,
            price=Decimal("1900.00"),
            change=Decimal("25.00"),
            change_percent=Decimal("1.33"),
            open=Decimal("1880.00"),
            high=Decimal("1910.00"),
            low=Decimal("1875.00"),
            close=Decimal("1900.00"),
            previous_close=Decimal("1875.00"),
            volume=950000,
            source_provider="JUGAAD",
            source_timestamp=timezone.now(),
            retrieved_at=timezone.now(),
            freshness_status="FRESH",
            source_type="DIRECT",
        )

    def test_price_above_alert_trigger_and_deduplication(self):
        alert = AlertRule.objects.create(
            user=self.user,
            listing=self.listing,
            alert_type=AlertType.PRICE_ABOVE,
            target_value=Decimal("1850.00"),
            is_active=True,
            is_market_hours_only=False,
            cooldown_minutes=60,
        )

        # 1. First evaluation: should trigger because price (1900) >= target (1850)
        triggered = AlertEvaluator.evaluate_alert(alert, check_market_hours=False)
        assert triggered is True
        assert alert.trigger_count == 1
        assert alert.last_triggered_at is not None

        # Verify Notification generated
        notif = Notification.objects.filter(user=self.user, alert_rule=alert).first()
        assert notif is not None
        assert "Crossed Above" in notif.title
        assert notif.severity == NotificationSeverity.SUCCESS

        # 2. Immediate second evaluation: must be skipped due to cooldown deduplication
        second_run = AlertEvaluator.evaluate_alert(alert, check_market_hours=False)
        assert second_run is False
        assert alert.trigger_count == 1
        assert Notification.objects.filter(user=self.user, alert_rule=alert).count() == 1

    def test_technical_rsi_oversold_alert_trigger(self):
        TechnicalIndicatorSnapshot.objects.create(
            listing=self.listing,
            interval="1D",
            timestamp=timezone.now(),
            trend_signal="BEARISH",
            rsi_14=Decimal("28.0"),
        )

        alert = AlertRule.objects.create(
            user=self.user,
            listing=self.listing,
            alert_type=AlertType.RSI_OVERSOLD,
            target_value=Decimal("30.0"),
            is_active=True,
            is_market_hours_only=False,
        )

        triggered = AlertEvaluator.evaluate_alert(alert, check_market_hours=False)
        assert triggered is True
        assert Notification.objects.filter(user=self.user, alert_rule=alert).exists()

    def test_portfolio_stop_loss_alert_trigger(self):
        portfolio = Portfolio.objects.create(
            user=self.user,
            name="Main Portfolio",
            cash_balance=Decimal("100000.00"),
        )
        Holding.objects.create(
            portfolio=portfolio,
            listing=self.listing,
            total_quantity=100,
            average_buy_price=Decimal("2000.00"),
            invested_amount=Decimal("200000.00"),
            current_price=Decimal("1900.00"),
            current_value=Decimal("190000.00"),
            unrealised_pnl=Decimal("-10000.00"),
            unrealised_pnl_percent=Decimal("-5.00"),
        )

        # Stop loss at 1920 (price 1900 is below 1920)
        alert = AlertRule.objects.create(
            user=self.user,
            listing=self.listing,
            alert_type=AlertType.PORTFOLIO_STOP_LOSS,
            target_value=Decimal("1920.00"),
            is_active=True,
            is_market_hours_only=False,
        )

        triggered = AlertEvaluator.evaluate_alert(alert, check_market_hours=False)
        assert triggered is True
        notif = Notification.objects.filter(user=self.user, alert_rule=alert).first()
        assert "STOP LOSS" in notif.title
        assert notif.severity == NotificationSeverity.DANGER

    def test_alert_views_crud_and_evaluate(self):
        # 1. List View
        res = self.client.get(reverse("alerts:list"))
        assert res.status_code == 200
        assert "Price &amp; Portfolio Alerts" in res.content.decode() or "Price & Portfolio Alerts" in res.content.decode()

        # 2. Create Alert View
        post_data = {
            "symbol": "INFY",
            "alert_type": AlertType.PRICE_ABOVE,
            "target_value": "2000.00",
            "notes": "Target breakout",
            "is_market_hours_only": "on",
        }
        create_res = self.client.post(reverse("alerts:create"), post_data)
        assert create_res.status_code == 302
        alert = AlertRule.objects.filter(user=self.user, listing=self.listing).first()
        assert alert is not None
        assert alert.target_value == Decimal("2000.00")

        # 3. Toggle Status View
        toggle_res = self.client.post(reverse("alerts:toggle", kwargs={"pk": alert.id}))
        assert toggle_res.status_code == 302
        alert.refresh_from_db()
        assert alert.is_active is False

        # 4. Evaluate Action
        eval_res = self.client.post(reverse("alerts:evaluate"))
        assert eval_res.status_code == 302

        # 5. Delete Alert View
        del_res = self.client.post(reverse("alerts:delete", kwargs={"pk": alert.id}))
        assert del_res.status_code == 302
        assert not AlertRule.objects.filter(pk=alert.id).exists()
