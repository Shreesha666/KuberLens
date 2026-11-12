"""
Universal validation and normalization pipeline for market quotes and candles.
"""
from decimal import Decimal

from .base import HistoricalCandleDTO, MarketQuoteDTO
from .exceptions import DataQualityError


class MarketDataNormalizer:
    @staticmethod
    def validate_candle(candle: HistoricalCandleDTO) -> HistoricalCandleDTO:
        """
        Validates OHLC relations and volume sanity:
        1. Low <= Open <= High
        2. Low <= Close <= High
        3. Volume >= 0
        4. Prices > 0
        """
        if candle.open <= Decimal("0") or candle.close <= Decimal("0") or candle.high <= Decimal("0") or candle.low <= Decimal("0"):
            raise DataQualityError(
                f"Invalid non-positive price in candle for {candle.timestamp}: "
                f"O={candle.open}, H={candle.high}, L={candle.low}, C={candle.close}"
            )

        if candle.low > candle.high:
            raise DataQualityError(
                f"Low price ({candle.low}) exceeds High price ({candle.high}) at {candle.timestamp}"
            )

        if candle.open < candle.low or candle.open > candle.high:
            raise DataQualityError(
                f"Open price ({candle.open}) outside bounds [{candle.low}, {candle.high}] at {candle.timestamp}"
            )

        if candle.close < candle.low or candle.close > candle.high:
            raise DataQualityError(
                f"Close price ({candle.close}) outside bounds [{candle.low}, {candle.high}] at {candle.timestamp}"
            )

        if candle.volume < 0:
            raise DataQualityError(
                f"Negative volume ({candle.volume}) encountered at {candle.timestamp}"
            )

        return candle

    @staticmethod
    def validate_quote(quote: MarketQuoteDTO) -> MarketQuoteDTO:
        """
        Validates basic sanity of live/delayed quote.
        """
        if quote.price <= Decimal("0"):
            raise DataQualityError(f"Invalid non-positive quote price ({quote.price}) for {quote.symbol}")

        if quote.volume < 0:
            raise DataQualityError(f"Negative volume ({quote.volume}) in quote for {quote.symbol}")

        return quote
