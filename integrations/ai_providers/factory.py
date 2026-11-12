"""
AI Provider Factory.
Instantiates and configures AI Provider implementations based on application settings.
"""
from django.conf import settings

from integrations.ai_providers.base import AIProviderBase
from integrations.ai_providers.fallback import StructuredRuleFallbackProvider
from integrations.ai_providers.gemini import GeminiAIProvider


def get_ai_provider(provider_type: str | None = None) -> AIProviderBase:
    """
    Returns an instance of the configured AI Provider.
    Defaults to Gemini if API key is present and configured, else StructuredRuleFallbackProvider.
    """
    configured = provider_type or getattr(settings, "AI_PROVIDER", "fallback")
    api_key = getattr(settings, "GEMINI_API_KEY", "")
    model_name = getattr(settings, "GEMINI_MODEL", "gemini-2.0-flash")

    if configured.lower() == "gemini":
        return GeminiAIProvider(api_key=api_key, model_name=model_name)
    elif configured.lower() == "mock" or configured.lower() == "fallback":
        return StructuredRuleFallbackProvider()

    # Default fallback
    return StructuredRuleFallbackProvider()

