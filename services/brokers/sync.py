"""
Broker Holdings Synchronization Service.
Complies with Master Specification Section 22 and Development Plan Phase 10.
Safely synchronizes broker portfolio holdings into user portfolios via read-only APIs.
"""
import logging
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.brokers.models import BrokerConnection, ConnectionStatus
from apps.holdings.models import HoldingTransaction, TransactionType
from apps.instruments.models import Exchange, ExchangeListing, Instrument
from apps.market.models import MarketQuote
from apps.portfolio.models import Portfolio
from integrations.broker_providers.zerodha.client import KiteConnectClient
from services.portfolio.accounting import FIFOAccountingEngine

logger = logging.getLogger(__name__)


class BrokerHoldingsSynchronizer:
    """
    Synchronizes long-term holdings from an active broker session (e.g. Zerodha Kite)
    into the user's platform portfolio and immutable transaction ledger.
    """

    @classmethod
    def sync_holdings(
        cls,
        connection: BrokerConnection,
        client: KiteConnectClient | None = None,
    ) -> dict[str, Any]:
        """
        Synchronizes all active equity holdings from the connected broker.
        """
        now = timezone.now()

        # 1. Validate Token & Expiration
        if not connection.is_token_valid():
            if connection.token_expires_at and connection.token_expires_at <= now:
                connection.status = ConnectionStatus.EXPIRED
                connection.save(update_fields=["status", "updated_at"])
                return {
                    "success": False,
                    "status": ConnectionStatus.EXPIRED,
                    "synced_count": 0,
                    "message": "Broker session token has expired. Daily re-authentication is required.",
                }
            return {
                "success": False,
                "status": connection.status,
                "synced_count": 0,
                "message": f"Broker connection is not active (Status: {connection.get_status_display()}).",
            }

        # 2. Initialize Kite client if not injected
        if client is None:
            client = KiteConnectClient(
                api_key=connection.api_key,
                access_token=connection.get_access_token(),
            )

        # 3. Retrieve user portfolio
        user = connection.user
        portfolio = Portfolio.objects.filter(user=user).first()
        if not portfolio:
            portfolio = Portfolio.objects.create(
                user=user,
                name="Primary Investment Portfolio",
                description="Automatically synchronized from broker account.",
            )

        # 4. Fetch holdings from broker
        try:
            holdings_list = client.get_holdings()
        except ConnectionError as e:
            logger.error("Failed to fetch holdings from broker: %s", e)
            return {
                "success": False,
                "status": ConnectionStatus.ERROR,
                "synced_count": 0,
                "message": str(e),
            }

        synced_count = 0
        total_invested = Decimal("0.00")
        total_current_val = Decimal("0.00")

        # 5. Ingest each holding securely into transaction ledger & reconcile
        with transaction.atomic():
            for item in holdings_list:
                symbol = item.get("tradingsymbol", "").strip().upper()
                exchange_code = item.get("exchange", "NSE").strip().upper()
                isin = item.get("isin", "").strip()
                qty = int(item.get("quantity", 0))
                avg_price = Decimal(str(item.get("average_price", 0.0)))
                last_price = Decimal(str(item.get("last_price", avg_price)))

                if not symbol or qty <= 0:
                    continue

                # Ensure Exchange & Listing exist
                exchange, _ = Exchange.objects.get_or_create(
                    code=exchange_code,
                    defaults={"name": f"{exchange_code} Stock Exchange", "country": "India", "currency": "INR"},
                )

                inst = None
                if isin:
                    inst = Instrument.objects.filter(isin=isin).first()
                if not inst:
                    inst = Instrument.objects.filter(display_name=symbol).first()
                if not inst:
                    inst = Instrument.objects.create(
                        isin=isin or f"IN_{symbol}_TMP",
                        display_name=symbol,
                        legal_name=f"{symbol} Limited",
                        sector="Diversified",
                        industry="Diversified",
                    )

                listing, _ = ExchangeListing.objects.get_or_create(
                    exchange=exchange,
                    symbol=symbol,
                    defaults={
                        "instrument": inst,
                        "trading_symbol": f"{symbol}-EQ",
                        "is_primary": True,
                        "is_tradeable": True,
                    },
                )

                # Update or create quote for live pricing
                MarketQuote.objects.update_or_create(
                    listing=listing,
                    defaults={
                        "price": last_price,
                        "change": Decimal("0.00"),
                        "change_percent": Decimal("0.00"),
                        "open": last_price,
                        "high": last_price,
                        "low": last_price,
                        "close": last_price,
                        "previous_close": avg_price,
                        "volume": 0,
                        "source_provider": "ZERODHA",
                        "source_type": "DIRECT",
                        "freshness_status": "FRESH",
                        "source_timestamp": now,
                        "retrieved_at": now,
                    },
                )

                # Record holding transaction if not already existing
                ref_id = f"KITE_SYNC_{connection.user.id}_{symbol}"
                tx = HoldingTransaction.objects.filter(
                    portfolio=portfolio,
                    listing=listing,
                    reference_transaction_id=ref_id,
                ).first()

                if not tx:
                    HoldingTransaction.objects.create(
                        portfolio=portfolio,
                        listing=listing,
                        transaction_type=TransactionType.BUY,
                        quantity=qty,
                        price=avg_price,
                        brokerage=Decimal("0.00"),
                        statutory_taxes=Decimal("0.00"),
                        executed_at=now,
                        reference_transaction_id=ref_id,
                        notes=f"Synced from {connection.get_broker_name_display()}",
                    )
                else:
                    # Update quantity and avg cost if changed
                    if tx.quantity != qty or tx.price != avg_price:
                        tx.quantity = qty
                        tx.price = avg_price
                        tx.executed_at = now
                        tx.save(update_fields=["quantity", "price", "executed_at", "updated_at"])

                # Reconcile holding state
                holding = FIFOAccountingEngine.reconcile_holding(
                    portfolio=portfolio,
                    listing=listing,
                    current_price=last_price,
                )

                total_invested += holding.invested_amount
                total_current_val += holding.current_value
                synced_count += 1

            # Update connection metadata
            summary = {
                "synced_holdings_count": synced_count,
                "total_invested": float(total_invested),
                "total_current_value": float(total_current_val),
                "synced_at": now.isoformat(),
            }
            connection.last_synced_at = now
            connection.sync_summary = summary
            connection.save(update_fields=["last_synced_at", "sync_summary", "updated_at"])

        return {
            "success": True,
            "status": connection.status,
            "synced_count": synced_count,
            "total_invested": total_invested,
            "total_current_value": total_current_val,
            "message": f"Successfully synchronized {synced_count} holdings from {connection.get_broker_name_display()}.",
        }
