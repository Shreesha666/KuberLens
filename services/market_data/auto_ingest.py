"""
Automatic On-Demand Ingestion Engine for NSE Equities.
Allows any valid NSE stock to be dynamically provisioned into Instrument and ExchangeListing,
fetching real-time metadata, quote, and historical candles on the fly.
"""
import logging
from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.utils import timezone

from apps.instruments.models import Exchange, ExchangeListing, Instrument
from apps.market.models import MarketQuote

logger = logging.getLogger(__name__)


class AutoIngestionService:
    @classmethod
    def get_or_create_listing(cls, symbol: str) -> Optional[ExchangeListing]:
        """
        Retrieves an ExchangeListing for the given symbol, or dynamically provisions it
        from Yahoo Finance if it does not yet exist in the local database.
        """
        symbol = symbol.strip().upper()
        if not symbol:
            return None

        # 1. Check if already exists in DB
        listing = (
            ExchangeListing.objects.filter(symbol=symbol, is_tradeable=True)
            .select_related("instrument", "exchange")
            .first()
        )
        if listing:
            return listing

        # 2. Attempt dynamic provisioning via Yahoo Finance
        try:
            return cls._provision_from_yahoo(symbol)
        except Exception as e:
            logger.warning("Dynamic provisioning failed for %s: %s", symbol, e)
            return None

    @classmethod
    def _provision_from_yahoo(cls, symbol: str) -> Optional[ExchangeListing]:
        import yfinance as yf

        t = yf.Ticker(f"{symbol}.NS")
        info = getattr(t, "info", None) or {}

        # If Yahoo doesn't recognize symbol.NS, try symbol.BO (BSE)
        exchange_code = "NSE"
        if not info or not (info.get("regularMarketPrice") or info.get("currentPrice") or info.get("shortName")):
            t_bse = yf.Ticker(f"{symbol}.BO")
            info_bse = getattr(t_bse, "info", None) or {}
            if info_bse and (info_bse.get("regularMarketPrice") or info_bse.get("currentPrice")):
                t = t_bse
                info = info_bse
                exchange_code = "BSE"

        price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
        if not price:
            logger.info("Symbol %s not found on market data providers.", symbol)
            return None

        exchange, _ = Exchange.objects.get_or_create(
            code=exchange_code,
            defaults={"name": "National Stock Exchange" if exchange_code == "NSE" else "Bombay Stock Exchange"}
        )

        display_name = (
            info.get("shortName")
            or info.get("longName")
            or symbol
        ).replace(" Limited", "").replace(" Ltd.", "").strip()

        legal_name = info.get("longName") or info.get("shortName") or display_name
        sector = info.get("sector") or "General"
        industry = info.get("industry") or "Diversified"
        isin = info.get("isin") or f"IN_AUTO_{symbol}"

        # Estimate market cap category
        mcap = info.get("marketCap")
        if mcap:
            mcap_cr = float(mcap) / 10000000.0  # Convert to INR Crores approx
            if mcap_cr >= 20000:
                cap_category = "LARGE"
            elif mcap_cr >= 5000:
                cap_category = "MID"
            elif mcap_cr >= 500:
                cap_category = "SMALL"
            else:
                cap_category = "MICRO"
        else:
            cap_category = "MID"

        with transaction.atomic():
            instrument, _ = Instrument.objects.get_or_create(
                isin=isin,
                defaults={
                    "legal_name": legal_name[:255],
                    "display_name": display_name[:150],
                    "sector": sector[:100],
                    "industry": industry[:100],
                    "market_cap_category": cap_category,
                    "is_active": True,
                }
            )

            listing, _ = ExchangeListing.objects.get_or_create(
                exchange=exchange,
                symbol=symbol,
                defaults={
                    "instrument": instrument,
                    "trading_symbol": f"{symbol}-EQ",
                    "series_or_group": "EQ",
                    "is_primary": True,
                    "is_tradeable": True,
                }
            )

            # Store initial MarketQuote
            now = timezone.now()
            p_dec = Decimal(str(round(float(price), 2)))
            prev_close = info.get("previousClose") or price
            prev_dec = Decimal(str(round(float(prev_close), 2)))
            chg = p_dec - prev_dec
            chg_pct = (chg / prev_dec * Decimal("100.0")) if prev_dec else Decimal("0.0")

            MarketQuote.objects.update_or_create(
                listing=listing,
                defaults={
                    "source_provider": "YAHOO",
                    "source_type": "DELAYED",
                    "freshness_status": "FRESH",
                    "source_timestamp": now,
                    "retrieved_at": now,
                    "price": p_dec,
                    "open": Decimal(str(round(float(info.get("open") or price), 2))),
                    "high": Decimal(str(round(float(info.get("dayHigh") or price), 2))),
                    "low": Decimal(str(round(float(info.get("dayLow") or price), 2))),
                    "close": p_dec,
                    "previous_close": prev_dec,
                    "change": chg,
                    "change_percent": chg_pct,
                    "volume": info.get("volume") or 0,
                }
            )

        logger.info("Successfully auto-ingested %s into local catalog.", symbol)
        return listing

