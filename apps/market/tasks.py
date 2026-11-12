"""
Celery asynchronous background tasks for market data ingestion and health monitoring.
"""
import logging
from datetime import datetime

from celery import shared_task
from django.utils import timezone

from integrations.market_data.health import ProviderHealthMonitor
from services.calendar.exchange_calendar import ExchangeCalendar
from services.market_data.service import MarketDataService

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def ingest_daily_bhavcopy_task(self, target_date_str: str | None = None):
    """
    Scheduled task (18:30 IST Mon-Fri) to ingest official NSE EOD Bhavcopy.
    Verifies trading day status via ExchangeCalendar before downloading.
    """
    if target_date_str:
        target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    else:
        target_date = timezone.now().date()

    if not ExchangeCalendar.is_trading_day(target_date):
        logger.info("Skipping Bhavcopy task for %s: non-trading day / holiday.", target_date)
        return {"status": "skipped", "reason": "holiday_or_weekend", "date": target_date.isoformat()}

    try:
        count = MarketDataService.ingest_eod_bhavcopy(target_date)
        return {"status": "success", "date": target_date.isoformat(), "records_ingested": count}
    except Exception as exc:
        logger.error("Bhavcopy ingestion task failed: %s", exc)
        raise self.retry(exc=exc) from exc

@shared_task
def monitor_provider_health_task():
    """
    Scheduled task running every 5 minutes to ping registered data providers
    and update their latency and health statuses in the database.
    """
    results = ProviderHealthMonitor.check_all_providers()
    logger.info("Provider health check task completed: %s", results)
    return results
