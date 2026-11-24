"""
Jugaad-Data Market Data Provider Adapter for Indian NSE Market.
"""
import logging
import time
from datetime import UTC, date, datetime
from decimal import Decimal

from django.utils import timezone

from integrations.market_data.base import (
    FreshnessStatus,
    HistoricalCandleDTO,
    MarketDataProvider,
    MarketQuoteDTO,
    ProviderHealthDTO,
    SourceType,
)
from integrations.market_data.exceptions import (
    ProviderConnectionError,
    RateLimitError,
)
from integrations.market_data.normalizer import MarketDataNormalizer

logger = logging.getLogger(__name__)

class JugaadDataProvider(MarketDataProvider):
    code = "JUGAAD"
    name = "Jugaad-Data (NSE India)"
    priority = 1
    source_type = SourceType.DIRECT
    configured_delay_minutes = 0

    def __init__(self, request_delay_seconds: float = 1.0):
        self.request_delay_seconds = request_delay_seconds
        self._last_request_time = 0.0

    def _rate_limit(self):
        """Polite rate limiting adhering to provider terms."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.request_delay_seconds:
            time.sleep(self.request_delay_seconds - elapsed)
        self._last_request_time = time.time()

    def get_quote(self, listing) -> MarketQuoteDTO:
        """
        Retrieves indicative quote for an NSE listing via Jugaad-Data.
        """
        self._rate_limit()
        start_t = time.time()
        try:
            from jugaad_data.nse import NSELive
            nse = NSELive()
            q = nse.stock_quote(listing.symbol)
            price_info = q.get("priceInfo", {}) or {}
            meta_data = q.get("metaData", {}) or {}
            trade_info = q.get("tradeInfo", {}) or {}
            order_book = q.get("orderBook", {}) or {}

            # Multi-location fallback for live vs off-market structures
            ltp_val = (
                price_info.get("lastPrice")
                or trade_info.get("lastPrice")
                or order_book.get("lastPrice")
                or meta_data.get("lastPrice")
                or meta_data.get("basePrice")
                or meta_data.get("previousClose")
                or "0"
            )
            ltp = Decimal(str(ltp_val))

            prev_close_val = (
                price_info.get("previousClose")
                or meta_data.get("previousClose")
                or trade_info.get("basePrice")
                or ltp
            )
            prev_close = Decimal(str(prev_close_val))

            change_val = (
                price_info.get("change")
                or meta_data.get("change")
                or (ltp - prev_close)
            )
            change = Decimal(str(change_val))

            pchange_val = (
                price_info.get("pChange")
                or meta_data.get("pChange")
                or ((change / prev_close * 100) if prev_close else Decimal("0"))
            )
            p_change = Decimal(str(pchange_val))

            open_val = meta_data.get("open") or price_info.get("open") or ltp
            open_p = Decimal(str(open_val))

            high_val = meta_data.get("dayHigh") or price_info.get("intraDayHighLow", {}).get("max") or ltp
            high_p = Decimal(str(high_val))

            low_val = meta_data.get("dayLow") or price_info.get("intraDayHighLow", {}).get("min") or ltp
            low_p = Decimal(str(low_val))

            close_p = Decimal(str(price_info.get("close") or meta_data.get("closePrice") or ltp)) or ltp
            vol = int(
                trade_info.get("totalTradedVolume")
                or trade_info.get("quantitytraded")
                or q.get("securityWiseDP", {}).get("quantityTraded", 0)
                or 0
            )
            latency_ms = int((time.time() - start_t) * 1000)

            quote = MarketQuoteDTO(
                symbol=listing.symbol,
                exchange=listing.exchange.code,
                price=ltp,
                change=change,
                change_percent=p_change,
                open=open_p,
                high=high_p,
                low=low_p,
                close=close_p,
                previous_close=prev_close,
                volume=vol,
                source_provider=self.code,
                source_type=SourceType.DIRECT,
                freshness_status=FreshnessStatus.FRESH,
                source_timestamp=timezone.now(),
                retrieved_at=timezone.now(),
                measured_latency_ms=latency_ms,
                configured_delay_minutes=0,
            )
            return MarketDataNormalizer.validate_quote(quote)
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "rate" in err_str:
                raise RateLimitError(f"Jugaad-Data rate limit exceeded: {e}") from e
            raise ProviderConnectionError(f"Failed to fetch quote from Jugaad-Data: {e}") from e

    def get_historical_candles(
        self,
        listing,
        start_date: date,
        end_date: date,
        interval: str = "1d",
    ) -> list[HistoricalCandleDTO]:
        """
        Retrieves historical EOD candles for an NSE listing or index via Jugaad-Data.
        Supports both equities and benchmark indices (e.g. ^NSEI mapped to NIFTY 50).
        """
        import zoneinfo
        from datetime import time as dt_time

        ist_tz = zoneinfo.ZoneInfo("Asia/Kolkata")
        sym = listing.symbol.upper()
        max_attempts = 3
        df = None
        last_error = None

        for attempt in range(1, max_attempts + 1):
            self._rate_limit()
            try:
                if sym in ("^NSEI", "NIFTY", "NIFTY 50", "NIFTY50"):
                    from jugaad_data.nse import index_df
                    df = index_df(symbol="NIFTY 50", from_date=start_date, to_date=end_date)
                else:
                    from jugaad_data.nse import stock_df
                    series = getattr(listing, "series_or_group", "EQ") or "EQ"
                    df = stock_df(symbol=sym, from_date=start_date, to_date=end_date, series=series)
                break
            except Exception as e:
                last_error = e
                logger.warning("[Jugaad] Attempt %d/%d failed for %s: %s", attempt, max_attempts, sym, e)
                if attempt < max_attempts:
                    time.sleep(0.5 * (2 ** (attempt - 1)))

        if df is None:
            err_str = str(last_error).lower() if last_error else ""
            if "429" in err_str:
                raise RateLimitError(f"Jugaad-Data rate limit exceeded for {sym}: {last_error}") from last_error
            raise ProviderConnectionError(f"Failed to fetch historical data from Jugaad-Data for {sym}: {last_error}") from last_error

        try:
            candles = []
            for _, row in df.iterrows():
                row_date = row.get("DATE") or row.get("HistoricalDate")
                if hasattr(row_date, "date"):
                    session_date = row_date.date()
                elif isinstance(row_date, str):
                    session_date = date.fromisoformat(row_date[:10])
                else:
                    session_date = row_date

                if session_date > end_date or session_date < start_date:
                    continue

                # Normalize EOD candle to official session close (15:30 IST = 10:00 UTC)
                candle_dt = datetime.combine(session_date, dt_time(15, 30), tzinfo=ist_tz).astimezone(UTC)

                open_col = row.get("OPEN") or row.get("Open") or 0
                high_col = row.get("HIGH") or row.get("High") or 0
                low_col = row.get("LOW") or row.get("Low") or 0
                close_col = row.get("CLOSE") or row.get("Close") or 0
                vol_col = row.get("VOLUME") or row.get("Volume") or row.get("Shares Traded") or 0

                c = HistoricalCandleDTO(
                    timestamp=candle_dt,
                    interval=interval,
                    open=Decimal(str(round(float(open_col), 4))),
                    high=Decimal(str(round(float(high_col), 4))),
                    low=Decimal(str(round(float(low_col), 4))),
                    close=Decimal(str(round(float(close_col), 4))),
                    volume=int(vol_col),
                    adjusted_close=None,
                    source_provider=self.code,
                )
                candles.append(MarketDataNormalizer.validate_candle(c))
            candles.sort(key=lambda x: x.timestamp)
            return candles
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str:
                raise RateLimitError(f"Jugaad-Data rate limit exceeded: {e}") from e
            raise ProviderConnectionError(f"Failed to process historical data from Jugaad-Data for {sym}: {e}") from e

    def health_check(self) -> ProviderHealthDTO:
        start_t = time.time()
        try:
            from jugaad_data.nse import NSELive
            nse = NSELive()
            # Lightweight health ping against NIFTY 50 live quote
            nse.stock_quote("SBIN")
            latency_ms = int((time.time() - start_t) * 1000)
            return ProviderHealthDTO(
                provider_code=self.code,
                status="HEALTHY",
                latency_ms=latency_ms,
                last_error=None,
                checked_at=timezone.now(),
            )
        except Exception as e:
            return ProviderHealthDTO(
                provider_code=self.code,
                status="OFFLINE",
                latency_ms=None,
                last_error=str(e),
                checked_at=timezone.now(),
            )
