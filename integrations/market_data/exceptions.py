"""
Exceptions for Market Data integration and provider layers.
"""

class MarketDataError(Exception):
    """Base exception for all market data errors."""

class ProviderConnectionError(MarketDataError):
    """Raised when network connection to an external provider fails or times out."""

class RateLimitError(MarketDataError):
    """Raised when a provider responds with HTTP 429 or rate limit throttling."""

class DataQualityError(MarketDataError):
    """Raised when received market data violates OHLC bounds or sanity checks."""

class ProviderUnavailableError(MarketDataError):
    """Raised when a requested provider is disabled, offline, or circuit-broken."""
