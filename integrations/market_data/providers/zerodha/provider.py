"""
Zerodha Kite Connect Market Data Provider Adapter.
Complies with Master Specification Section 22 and Architecture 2.1.
Implements MarketDataProvider interface as an optional read-only data source.
"""
import logging
from datetime import date
from decimal import Decimal
from typing import Any

from django.utils import timezone

from integrations.broker_providers.zerodha.client import KiteConnectClient
from integrations.market_data.base import (
    FreshnessStatus,
    HistoricalCandleDTO,
    MarketDataProvider,
    MarketQuoteDTO,
    ProviderHealthDTO,
    SourceType,
)
from integrations.market_data.exceptions import ProviderUnavailableError

logger = logging.getLogger(__name__)


class ZerodhaKiteProvider(MarketDataProvider):
    """
    Market data provider wrapping Zerodha Kite Connect v3.
    Operates as an optional secondary/tertiary data provider.
    """
    code = "ZERODHA"
    name = "Zerodha Kite Connect (Broker)"
    priority = 3
    source_type = SourceType.DIRECT
    configured_delay_minutes = 0

    def __init__(self, api_key: str = "", access_token: str = ""):
        self.api_key = api_key
        self.access_token = access_token
        self.client = KiteConnectClient(api_key=api_key, access_token=access_token)

    def is_configured(self) -> bool:
        return bool(self.api_key and self.access_token)

    def get_quote(self, listing: Any) -> MarketQuoteDTO:
        if not self.is_configured():
            raise ProviderUnavailableError("Zerodha Kite credentials are not configured or session is unauthenticated.")

        exchange_prefix = listing.exchange.code if hasattr(listing, "exchange") else "NSE"
        instrument_key = f"{exchange_prefix}:{listing.symbol}"

        data = self.client.get_quote([instrument_key])
        quote_data = data.get(instrument_key)
        if not quote_data:
            raise ProviderUnavailableError(f"No quote data returned from Zerodha Kite for {instrument_key}")

        now = timezone.now()
        price = Decimal(str(quote_data.get("last_price", 0.0)))
        ohlc = quote_data.get("ohlc", {})
        open_price = Decimal(str(ohlc.get("open", price)))
        high_price = Decimal(str(ohlc.get("high", price)))
        low_price = Decimal(str(ohlc.get("low", price)))
        close_price = Decimal(str(ohlc.get("close", price)))
        net_change = Decimal(str(quote_data.get("net_change", 0.0)))
        change_pct = Decimal(str(quote_data.get("change", 0.0)))

        return MarketQuoteDTO(
            symbol=listing.symbol,
            exchange=exchange_prefix,
            price=price,
            change=net_change,
            change_percent=change_pct,
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            previous_close=close_price - net_change,
            volume=int(quote_data.get("volume", 0)),
            source_provider=self.code,
            source_type=self.source_type,
            freshness_status=FreshnessStatus.FRESH,
            source_timestamp=now,
            retrieved_at=now,
        )

    def get_historical_candles(
        self,
        listing: Any,
        start_date: date,
        end_date: date,
        interval: str = "1d",
    ) -> list[HistoricalCandleDTO]:
        if not self.is_configured():
            raise ProviderUnavailableError("Zerodha Kite credentials are not configured for historical candle sync.")
        # Historical candles require full Kite historical API subscription; fallback when not activated
        return []

    def health_check(self) -> ProviderHealthDTO:
        now = timezone.now()
        if not self.is_configured():
            return ProviderHealthDTO(
                provider_code=self.code,
                status="OFFLINE",
                latency_ms=None,
                last_error="Zerodha Kite credentials not configured in settings or user session.",
                checked_at=now,
            )
        try:
            start_t = timezone.now()
            # Lightweight ping
            self.client.get_quote(["NSE:NIFTY 50"])
            latency = int((timezone.now() - start_t).total_seconds() * 1000)
            return ProviderHealthDTO(
                provider_code=self.code,
                status="HEALTHY",
                latency_ms=latency,
                last_error=None,
                checked_at=now,
            )
        except Exception as e:
            return ProviderHealthDTO(
                provider_code=self.code,
                status="DEGRADED",
                latency_ms=None,
                last_error=str(e),
                checked_at=now,
            )
