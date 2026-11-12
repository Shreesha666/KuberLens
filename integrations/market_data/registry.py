"""
Registry for Market Data Providers.
Manages provider discovery, priority resolution, and fallback routing.
"""
import logging
from typing import ClassVar

from .base import MarketDataProvider
from .exceptions import ProviderUnavailableError
from .providers.jugaad.adapter import JugaadDataProvider
from .providers.yahoo.adapter import YahooFinanceProvider

logger = logging.getLogger(__name__)

class ProviderRegistry:
    _providers: ClassVar[dict[str, MarketDataProvider]] = {}

    @classmethod
    def register(cls, provider: MarketDataProvider):
        cls._providers[provider.code] = provider
        logger.info("Registered market data provider: %s (%s)", provider.name, provider.code)

    @classmethod
    def get(cls, provider_code: str) -> MarketDataProvider:
        provider = cls._providers.get(provider_code.upper())
        if not provider:
            raise ProviderUnavailableError(f"Provider '{provider_code}' is not registered.")
        return provider

    @classmethod
    def get_all(cls) -> list[MarketDataProvider]:
        return sorted(cls._providers.values(), key=lambda p: p.priority)

    @classmethod
    def get_primary(cls) -> MarketDataProvider:
        providers = cls.get_all()
        if not providers:
            raise ProviderUnavailableError("No market data providers are currently registered.")
        return providers[0]

    @classmethod
    def get_fallback(cls) -> MarketDataProvider | None:
        providers = cls.get_all()
        return providers[1] if len(providers) > 1 else None

# Automatically register initial Phase 2 providers
ProviderRegistry.register(JugaadDataProvider())
ProviderRegistry.register(YahooFinanceProvider())
