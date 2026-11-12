"""
Unit and Integration Tests for Phase 10: F&O Preparation & Zerodha Kite Integration.
"""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import CustomUser
from apps.brokers.models import BrokerConnection, BrokerName, ConnectionStatus
from apps.holdings.models import Holding, HoldingTransaction
from apps.instruments.models import Exchange, ExchangeListing, Instrument
from apps.market.models import DerivativeContract, DerivativeContractType, OptionType
from integrations.broker_providers.zerodha.client import KiteConnectClient
from services.brokers.sync import BrokerHoldingsSynchronizer


@pytest.mark.django_db
class TestBrokerIntegrationAndDerivatives:
    @pytest.fixture(autouse=True)
    def setup_data(self, client):
        self.client = client
        self.user = CustomUser.objects.create_user(
            username="brokeruser",
            email="brokeruser@example.com",
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

    def test_broker_connection_fernet_encryption(self):
        conn = BrokerConnection.objects.create(
            user=self.user,
            broker_name=BrokerName.ZERODHA,
            api_key="test_api_key_123",
        )
        raw_secret = "super_confidential_kite_secret_999"
        raw_token = "access_token_daily_xyz123"

        conn.set_api_secret(raw_secret)
        conn.set_access_token(raw_token)
        conn.save()

        # Reload from DB
        conn.refresh_from_db()

        # Database raw fields must be ciphertext, NOT containing plaintext
        assert raw_secret not in conn.api_secret_encrypted
        assert raw_token not in conn.access_token_encrypted
        assert len(conn.api_secret_encrypted) > 20

        # Helper methods must return decrypted plaintext
        assert conn.get_api_secret() == raw_secret
        assert conn.get_access_token() == raw_token

    def test_strict_safety_no_order_placement(self):
        client = KiteConnectClient(api_key="test_key", access_token="test_token")
        with pytest.raises(PermissionError) as exc_info:
            client.place_order(symbol="RELIANCE", quantity=10, transaction_type="BUY")
        assert "CRITICAL SAFETY VIOLATION" in str(exc_info.value)

        with pytest.raises(PermissionError):
            client.modify_order(order_id="12345")

        with pytest.raises(PermissionError):
            client.cancel_order(order_id="12345")

    def test_kite_client_session_and_holdings_mock(self):
        client = KiteConnectClient(api_key="my_key", api_secret="my_secret")

        mock_token_resp = MagicMock()
        mock_token_resp.status_code = 200
        mock_token_resp.json.return_value = {
            "status": "success",
            "data": {
                "access_token": "mocked_session_token_123",
                "public_token": "mocked_pub_token",
            },
        }

        with patch.object(client._session, "post", return_value=mock_token_resp):
            session = client.generate_session(request_token="daily_request_token_abc")
            assert session["access_token"] == "mocked_session_token_123"
            assert client.access_token == "mocked_session_token_123"

        # Mock holdings
        mock_holdings_resp = MagicMock()
        mock_holdings_resp.status_code = 200
        mock_holdings_resp.json.return_value = {
            "status": "success",
            "data": [
                {
                    "tradingsymbol": "RELIANCE",
                    "exchange": "NSE",
                    "isin": "INE002A01018",
                    "quantity": 25,
                    "average_price": 2420.50,
                    "last_price": 2510.00,
                    "pnl": 2237.50,
                }
            ],
        }

        with patch.object(client._session, "get", return_value=mock_holdings_resp):
            holdings = client.get_holdings()
            assert len(holdings) == 1
            assert holdings[0]["tradingsymbol"] == "RELIANCE"

    def test_broker_holdings_synchronizer(self):
        conn = BrokerConnection.objects.create(
            user=self.user,
            broker_name=BrokerName.ZERODHA,
            api_key="valid_key",
            status=ConnectionStatus.CONNECTED,
            is_active=True,
            token_expires_at=timezone.now() + timedelta(hours=6),
        )
        conn.set_access_token("valid_access_token")
        conn.save()

        mock_client = MagicMock(spec=KiteConnectClient)
        mock_client.get_holdings.return_value = [
            {
                "tradingsymbol": "RELIANCE",
                "exchange": "NSE",
                "isin": "INE002A01018",
                "quantity": 30,
                "average_price": 2400.00,
                "last_price": 2500.00,
            }
        ]

        result = BrokerHoldingsSynchronizer.sync_holdings(conn, client=mock_client)
        assert result["success"] is True
        assert result["synced_count"] == 1

        conn.refresh_from_db()
        assert conn.last_synced_at is not None
        assert conn.sync_summary["synced_holdings_count"] == 1

        # Check holding created
        holding = Holding.objects.filter(portfolio__user=self.user, listing=self.listing).first()
        assert holding is not None
        assert holding.total_quantity == 30
        assert holding.average_buy_price == Decimal("2400.0000")
        assert HoldingTransaction.objects.filter(portfolio__user=self.user, listing=self.listing).exists()

    def test_expired_session_handling(self):
        conn = BrokerConnection.objects.create(
            user=self.user,
            broker_name=BrokerName.ZERODHA,
            api_key="expired_key",
            status=ConnectionStatus.CONNECTED,
            is_active=True,
            token_expires_at=timezone.now() - timedelta(hours=1),  # Expired
        )
        conn.set_access_token("expired_token")
        conn.save()

        result = BrokerHoldingsSynchronizer.sync_holdings(conn)
        assert result["success"] is False
        assert result["status"] == ConnectionStatus.EXPIRED

        conn.refresh_from_db()
        assert conn.status == ConnectionStatus.EXPIRED

    def test_derivative_contracts(self):
        expiry = timezone.now().date() + timedelta(days=15)
        fut = DerivativeContract.objects.create(
            underlying_listing=self.listing,
            contract_type=DerivativeContractType.FUTURES,
            option_type=OptionType.NONE,
            expiry_date=expiry,
            lot_size=250,
            trading_symbol="RELIANCE24NOVFUT",
            open_interest=500000,
            change_in_oi=12000,
        )
        opt_ce = DerivativeContract.objects.create(
            underlying_listing=self.listing,
            contract_type=DerivativeContractType.OPTIONS,
            option_type=OptionType.CE,
            strike_price=Decimal("2500.00"),
            expiry_date=expiry,
            lot_size=250,
            trading_symbol="RELIANCE24NOV2500CE",
            open_interest=250000,
            implied_volatility=Decimal("17.80"),
        )

        assert DerivativeContract.objects.filter(underlying_listing=self.listing).count() == 2
        assert fut.contract_type == DerivativeContractType.FUTURES
        assert opt_ce.option_type == OptionType.CE
        assert opt_ce.strike_price == Decimal("2500.00")

    def test_broker_settings_view_get(self):
        url = reverse("brokers:settings")
        resp = self.client.get(url)
        assert resp.status_code == 200
        assert "Broker Connections &amp; Portfolio Sync" in resp.content.decode() or "Broker Connections & Portfolio Sync" in resp.content.decode()

    def test_broker_settings_view_htmx(self):
        url = reverse("brokers:settings")
        resp = self.client.get(url, HTTP_HX_REQUEST="true")
        assert resp.status_code == 200
        assert "Zerodha Kite Connection Status" in resp.content.decode()

    def test_broker_save_credentials_flow(self):
        url = reverse("brokers:save_credentials")
        resp = self.client.post(url, {"api_key": "new_kite_api_key", "api_secret": "new_kite_secret"})
        assert resp.status_code == 302
        assert resp.url == reverse("brokers:settings")

        conn = BrokerConnection.objects.filter(user=self.user, broker_name=BrokerName.ZERODHA).first()
        assert conn is not None
        assert conn.api_key == "new_kite_api_key"
        assert conn.get_api_secret() == "new_kite_secret"

    def test_broker_disconnect_flow(self):
        conn = BrokerConnection.objects.create(
            user=self.user,
            broker_name=BrokerName.ZERODHA,
            api_key="test_key",
            status=ConnectionStatus.CONNECTED,
            is_active=True,
        )
        conn.set_access_token("some_token")
        conn.save()

        url = reverse("brokers:disconnect")
        resp = self.client.post(url)
        assert resp.status_code == 302

        conn.refresh_from_db()
        assert conn.status == ConnectionStatus.DISCONNECTED
        assert conn.is_active is False
        assert conn.get_access_token() == ""

    def test_derivatives_overview_view(self):
        url = reverse("brokers:derivatives")
        resp = self.client.get(url)
        assert resp.status_code == 200
        assert "F&amp;O Derivatives Intelligence" in resp.content.decode() or "F&O Derivatives Intelligence" in resp.content.decode()

