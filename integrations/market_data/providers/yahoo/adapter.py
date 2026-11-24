"""
Yahoo Finance Market Data Provider Adapter for Indian Stock Market.
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

class YahooFinanceProvider(MarketDataProvider):
    code = "YAHOO"
    name = "Yahoo Finance"
    priority = 2
    source_type = SourceType.DELAYED
    configured_delay_minutes = 15

    def _to_yahoo_ticker(self, listing) -> str:
        """Converts an internal exchange listing symbol to Yahoo Finance ticker format."""
        symbol = getattr(listing, "symbol", str(listing)).strip()
        # Direct special tickers like ^NSEI or ^BSESN
        if symbol.startswith("^"):
            return symbol
        exchange_code = getattr(listing.exchange, "code", str(listing.exchange)).upper()
        if exchange_code == "NSE":
            return f"{symbol}.NS"
        elif exchange_code == "BSE":
            # If listing has a trading_symbol (e.g. RELIANCE, TCS) on BSE, prefer trading_symbol.BO
            trading_sym = getattr(listing, "trading_symbol", None)
            if trading_sym and not trading_sym.isdigit():
                return f"{trading_sym}.BO"
            return f"{symbol}.BO"
        return symbol

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

    def get_batch_quotes(self, listings: list) -> list[MarketQuoteDTO]:
        """
        Retrieves quotes for multiple listings concurrently via Yahoo Finance Tickers.
        High throughput, single batch request taking ~1.5 - 3s for 20+ symbols.
        """
        if not listings:
            return []

        start_t = time.time()
        ticker_map = {self._to_yahoo_ticker(lst): lst for lst in listings}
        tickers_str = " ".join(ticker_map.keys())

        try:
            import yfinance as yf
            batch = yf.Tickers(tickers_str)
            now = timezone.now()
            quotes: list[MarketQuoteDTO] = []

            for ticker_str, listing in ticker_map.items():
                t = batch.tickers.get(ticker_str)
                if not t:
                    continue
                fast_info = getattr(t, "fast_info", None)
                if not fast_info:
                    continue

                last_p = getattr(fast_info, "last_price", None)
                prev_p = getattr(fast_info, "previous_close", None)
                if last_p is None:
                    continue

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

                dto = MarketQuoteDTO(
                    symbol=listing.symbol,
                    exchange=getattr(listing.exchange, "code", "NSE"),
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
                    source_timestamp=now,
                    retrieved_at=now,
                    measured_latency_ms=int((time.time() - start_t) * 1000),
                    configured_delay_minutes=self.configured_delay_minutes,
                )
                try:
                    quotes.append(MarketDataNormalizer.validate_quote(dto))
                except Exception as norm_err:
                    logger.debug("Quote normalization failed for %s: %s", listing.symbol, norm_err)

            return quotes
        except Exception as e:
            logger.warning("Batch quote fetch failed in YahooFinanceProvider: %s", e)
            return []

    def get_historical_candles(
        self,
        listing,
        start_date: date,
        end_date: date,
        interval: str = "1d",
    ) -> list[HistoricalCandleDTO]:
        ticker_str = self._to_yahoo_ticker(listing)
        try:
            import zoneinfo
            from datetime import time as dt_time

            import yfinance as yf

            ist_tz = zoneinfo.ZoneInfo("Asia/Kolkata")
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
                # Extract Indian exchange trading session date
                if hasattr(ts, "date"):
                    session_date = ts.date()
                else:
                    session_date = ts.astimezone(ist_tz).date()

                # Normalize EOD candle to official session close (15:30 IST = 10:00 UTC)
                candle_dt = datetime.combine(session_date, dt_time(15, 30), tzinfo=ist_tz).astimezone(UTC)

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
