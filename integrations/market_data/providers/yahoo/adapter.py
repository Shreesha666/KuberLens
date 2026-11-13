"""
Yahoo Finance Market Data Provider Adapter for Indian Stock Market.
"""
import logging
import time
from datetime import UTC, date
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

class YahooFinanceProvider(MarketDataProvider):
    code = "YAHOO"
    name = "Yahoo Finance"
    priority = 2
    source_type = SourceType.DELAYED
    configured_delay_minutes = 15

    def _to_yahoo_ticker(self, listing) -> str:
        """Converts an internal exchange listing symbol to Yahoo Finance ticker format."""
        exchange_code = getattr(listing.exchange, "code", str(listing.exchange)).upper()
        if exchange_code == "NSE":
            return f"{listing.symbol}.NS"
        elif exchange_code == "BSE":
            return f"{listing.symbol}.BO"
        return listing.symbol

    def get_quote(self, listing) -> MarketQuoteDTO:
        start_t = time.time()
        ticker_str = self._to_yahoo_ticker(listing)
        try:
            import yfinance as yf
            ticker = yf.Ticker(ticker_str)
            fast_info = ticker.fast_info

            last_p = getattr(fast_info, "last_price", None)
            prev_p = getattr(fast_info, "previous_close", None)

            if last_p is None:
                # Fallback to recent history candles
                hist = ticker.history(period="5d")
                if not hist.empty:
                    last_p = float(hist["Close"].iloc[-1])
                    if len(hist) > 1 and prev_p is None:
                        prev_p = float(hist["Close"].iloc[-2])

            if last_p is None:
                raise ProviderConnectionError(f"Yahoo Finance returned no price data for {ticker_str}")

            price = Decimal(str(round(last_p, 4)))
            prev_close = Decimal(str(round(prev_p, 4))) if prev_p is not None else price
            open_val = getattr(fast_info, "open", None)
            high_val = getattr(fast_info, "day_high", None)
            low_val = getattr(fast_info, "day_low", None)

            open_p = Decimal(str(round(open_val, 4))) if open_val else price
            high_p = Decimal(str(round(high_val, 4))) if high_val else price
            low_p = Decimal(str(round(low_val, 4))) if low_val else price
            change = price - prev_close
            p_change = (change / prev_close * 100) if prev_close else Decimal("0")
            vol = int(getattr(fast_info, "last_volume", 0) or 0)
            latency_ms = int((time.time() - start_t) * 1000)

            quote = MarketQuoteDTO(
                symbol=listing.symbol,
                exchange=listing.exchange.code,
                price=price,
                change=change,
                change_percent=p_change,
                open=open_p,
                high=high_p,
                low=low_p,
                close=price,
                previous_close=prev_close,
                volume=vol,
                source_provider=self.code,
                source_type=self.source_type,
                freshness_status=FreshnessStatus.FRESH,
                source_timestamp=timezone.now(),
                retrieved_at=timezone.now(),
                measured_latency_ms=latency_ms,
                configured_delay_minutes=self.configured_delay_minutes,
            )
            return MarketDataNormalizer.validate_quote(quote)
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "rate" in err_str:
                raise RateLimitError(f"Yahoo Finance rate limit exceeded: {e}") from e
            raise ProviderConnectionError(f"Failed to fetch quote from Yahoo Finance: {e}") from e

    def get_historical_candles(
        self,
        listing,
        start_date: date,
        end_date: date,
        interval: str = "1d",
    ) -> list[HistoricalCandleDTO]:
        ticker_str = self._to_yahoo_ticker(listing)
        try:
            import yfinance as yf
            ticker = yf.Ticker(ticker_str)
            # Fetch historical range
            df = ticker.history(
                start=start_date.strftime("%Y-%m-%d"),
                end=end_date.strftime("%Y-%m-%d"),
                interval="1d",
                auto_adjust=False,
            )
            candles = []
            for ts, row in df.iterrows():
                # Convert timestamp to UTC datetime
                if hasattr(ts, "to_pydatetime"):
                    candle_dt = ts.to_pydatetime()
                else:
                    candle_dt = ts
                if candle_dt.tzinfo is None:
                    candle_dt = candle_dt.replace(tzinfo=UTC)
                else:
                    candle_dt = candle_dt.astimezone(UTC)

                adj_close = Decimal(str(round(row.get("Adj Close", row["Close"]), 4))) if "Adj Close" in row else None
                c = HistoricalCandleDTO(
                    timestamp=candle_dt,
                    interval=interval,
                    open=Decimal(str(round(row["Open"], 4))),
                    high=Decimal(str(round(row["High"], 4))),
                    low=Decimal(str(round(row["Low"], 4))),
                    close=Decimal(str(round(row["Close"], 4))),
                    volume=int(row["Volume"]),
                    adjusted_close=adj_close,
                    source_provider=self.code,
                )
                candles.append(MarketDataNormalizer.validate_candle(c))
            candles.sort(key=lambda x: x.timestamp)
            return candles
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str:
                raise RateLimitError(f"Yahoo Finance rate limit exceeded: {e}") from e
            raise ProviderConnectionError(f"Failed to fetch historical candles from Yahoo Finance: {e}") from e

    def health_check(self) -> ProviderHealthDTO:
        start_t = time.time()
        try:
            import yfinance as yf
            ticker = yf.Ticker("RELIANCE.NS")
            _ = ticker.fast_info.last_price
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
