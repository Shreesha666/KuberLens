from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any


class SourceType(StrEnum):
    DIRECT = "DIRECT"    # Verified direct real-time feed
    DELAYED = "DELAYED"  # Expressly delayed feed (e.g. Yahoo 15m)
    EOD = "EOD"          # Official settled post-market Bhavcopy

class FreshnessStatus(StrEnum):
    FRESH = "FRESH"      # Retrieved fresh within current polling window
    CACHED = "CACHED"    # Served from Redis/memory cache within TTL
    STALE = "STALE"      # Exceeds freshness threshold during active session
    OFFLINE = "OFFLINE"  # Provider failed; displaying last known value

@dataclass(frozen=True)
class MarketQuoteDTO:
    symbol: str
    exchange: str
    price: Decimal
    change: Decimal
    change_percent: Decimal
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    previous_close: Decimal
    volume: int
    source_provider: str
    source_type: SourceType
    freshness_status: FreshnessStatus
    source_timestamp: datetime
    retrieved_at: datetime
    measured_latency_ms: int | None = None
    configured_delay_minutes: int = 0

@dataclass(frozen=True)
class HistoricalCandleDTO:
    timestamp: datetime         # UTC Candle boundary
    interval: str               # "1d", "1h", "15m", "5m"
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    adjusted_close: Decimal | None
    source_provider: str

@dataclass(frozen=True)
class ProviderHealthDTO:
    provider_code: str
    status: str                 # "HEALTHY", "DEGRADED", "OFFLINE"
    latency_ms: int | None
    last_error: str | None
    checked_at: datetime

class MarketDataProvider(ABC):
    """
    Abstract Base Class for all external market data providers.
    Enforces a uniform interface for quotes, historical candles, and health checks.
    """
    code: str
    name: str
    priority: int = 1
    source_type: SourceType = SourceType.DIRECT
    configured_delay_minutes: int = 0

    @abstractmethod
    def get_quote(self, listing: Any) -> MarketQuoteDTO:
        """Fetch latest quote for an exchange listing."""

    @abstractmethod
    def get_historical_candles(
        self,
        listing: Any,
        start_date: date,
        end_date: date,
        interval: str = "1d",
    ) -> list[HistoricalCandleDTO]:
        """Fetch historical OHLCV candle series within date range."""

    @abstractmethod
    def health_check(self) -> ProviderHealthDTO:
        """Check provider connectivity and measure response latency."""
