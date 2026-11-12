"""
Provider Health Monitor and Circuit Breaker Service.
"""
import logging
from datetime import timedelta

from django.utils import timezone

from .registry import ProviderRegistry

logger = logging.getLogger(__name__)

class ProviderHealthMonitor:
    CIRCUIT_BREAKER_FAILURE_THRESHOLD = 3
    COOLDOWN_MINUTES = 15

    @classmethod
    def check_all_providers(cls) -> list[dict]:
        """
        Polls health checks across all registered market data providers,
        updating the DataProvider database model and recording latencies.
        """
        from apps.market.models import DataProvider

        results = []
        for provider in ProviderRegistry.get_all():
            db_provider, _ = DataProvider.objects.get_or_create(
                code=provider.code,
                defaults={"name": provider.name, "priority": provider.priority},
            )

            health = provider.health_check()
            if health.status == "HEALTHY":
                db_provider.health_status = "HEALTHY"
                db_provider.measured_latency_ms = health.latency_ms
                db_provider.last_successful_request = timezone.now()
                db_provider.last_error_message = ""
            else:
                db_provider.health_status = "DEGRADED"
                db_provider.last_error_message = health.last_error or "Health check failed"

            db_provider.save()
            results.append({
                "code": provider.code,
                "name": provider.name,
                "status": db_provider.health_status,
                "latency_ms": db_provider.measured_latency_ms,
                "last_error": db_provider.last_error_message,
                "checked_at": health.checked_at.isoformat(),
            })
        return results

    @classmethod
    def is_provider_available(cls, provider_code: str) -> bool:
        """Checks if a provider is enabled and not circuit-broken in the database."""
        from apps.market.models import DataProvider
        try:
            p = DataProvider.objects.get(code=provider_code)
            if not p.is_enabled:
                return False
            if p.health_status == "OFFLINE":
                # Check if cooldown has elapsed
                if p.updated_at and (timezone.now() - p.updated_at) < timedelta(minutes=cls.COOLDOWN_MINUTES):
                    return False
            return True
        except DataProvider.DoesNotExist:
            return True
