"""
Celery background tasks for Technical Analysis calculations.
Executes asynchronously after raw historical market data ingestion.
"""
import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.instruments.models import ExchangeListing
from apps.market.models import HistoricalCandle
from services.indicators.calculator import TechnicalIndicatorCalculator

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def calculate_technical_indicators_task(self, listing_id: str, days: int = 365, interval: str = "1d"):
    """
    Computes technical indicators for a specific listing using raw stored candles.
    """
    try:
        listing = ExchangeListing.objects.get(id=listing_id)
        start_date = timezone.now() - timedelta(days=days)
        candles = list(
            HistoricalCandle.objects.filter(
                listing=listing,
                interval=interval,
                timestamp__gte=start_date,
            ).order_by("timestamp")
        )

        if not candles:
            logger.warning("No candles available for %s to compute indicators.", listing.symbol)
            return {"status": "skipped", "symbol": listing.symbol, "reason": "no_candles"}

        snapshots = TechnicalIndicatorCalculator.compute_and_store_snapshots(listing, candles)
        return {"status": "success", "symbol": listing.symbol, "snapshots_created": len(snapshots)}
    except Exception as exc:
        logger.error("Error calculating technical indicators for listing %s: %s", listing_id, exc)
        raise self.retry(exc=exc) from exc


@shared_task
def calculate_all_active_indicators_task(days: int = 365, interval: str = "1d"):
    """
    Scheduled task running daily after EOD Bhavcopy ingestion to update all active listings.
    """
    listings = ExchangeListing.objects.filter(is_tradeable=True)
    count = 0
    for listing in listings:
        calculate_technical_indicators_task.delay(str(listing.id), days=days, interval=interval)
        count += 1
    return {"status": "queued", "tasks_dispatched": count}
