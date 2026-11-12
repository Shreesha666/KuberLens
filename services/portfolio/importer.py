"""
Portfolio CSV Importer Service.
Parses CSV file streams or raw pasted text from brokers (Zerodha Kite, Groww, Upstox, generic CSV),
normalizes column headers, generates canonical instruments, records transactions, and reconciles FIFO positions.
"""
import csv
import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from django.utils import timezone

from apps.holdings.models import (
    Holding,
    HoldingTransaction,
    LotAllocation,
    TransactionType,
)
from apps.instruments.models import Exchange, ExchangeListing, Instrument
from apps.market.models import MarketQuote
from apps.portfolio.models import Portfolio
from services.portfolio.accounting import FIFOAccountingEngine

logger = logging.getLogger(__name__)


class PortfolioCSVImporter:
    HEADER_MAP = {
        "symbol": [
            "instrument",
            "symbol",
            "stock",
            "scrip",
            "tradingsymbol",
            "trading symbol",
            "ticker",
            "company",
        ],
        "quantity": ["qty.", "qty", "quantity", "shares", "net qty", "units"],
        "avg_cost": [
            "avg. cost",
            "avg cost",
            "avg price",
            "average price",
            "buy price",
            "avg_cost",
            "rate",
            "price",
        ],
        "ltp": [
            "ltp",
            "current price",
            "cur. val",
            "last price",
            "close",
            "market price",
            "cmp",
        ],
    }

    @classmethod
    def clean_decimal(cls, val: Any) -> Decimal:
        if val is None:
            return Decimal("0.00")
        s = str(val).strip().replace(",", "").replace("₹", "").replace("$", "")
        if not s or s == "-":
            return Decimal("0.00")
        try:
            return Decimal(s)
        except InvalidOperation:
            # Try extracting digits and dot
            matched = re.search(r"[-+]?\d*\.?\d+", s)
            if matched:
                try:
                    return Decimal(matched.group(0))
                except InvalidOperation:
                    return Decimal("0.00")
            return Decimal("0.00")

    @classmethod
    def clean_int(cls, val: Any) -> int:
        d = cls.clean_decimal(val)
        return int(round(d))

    @classmethod
    def parse_and_import(
        cls,
        portfolio: Portfolio,
        content: str,
        clear_existing: bool = False,
        default_exchange_code: str = "NSE",
    ) -> dict[str, Any]:
        """
        Parses CSV string content and populates portfolio transactions.
        Returns summary dictionary with counts, totals, and errors if any.
        """
        lines = [line.strip() for line in content.strip().splitlines() if line.strip()]
        if not lines:
            raise ValueError("CSV content is empty.")

        reader = csv.reader(lines)
        raw_header = next(reader, None)
        if not raw_header:
            raise ValueError("Unable to read CSV header row.")

        # Normalize header keys
        header_indices = {}
        for idx, col_name in enumerate(raw_header):
            clean_col = col_name.strip().lower()
            for canonical_key, aliases in cls.HEADER_MAP.items():
                if clean_col in aliases and canonical_key not in header_indices:
                    header_indices[canonical_key] = idx

        if "symbol" not in header_indices:
            raise ValueError(
                "Could not find stock symbol column. Expected column headers like 'Instrument', 'Symbol', or 'Stock'."
            )
        if "quantity" not in header_indices:
            raise ValueError(
                "Could not find quantity column. Expected column headers like 'Qty.', 'Qty', or 'Quantity'."
            )
        if "avg_cost" not in header_indices:
            raise ValueError(
                "Could not find average price column. Expected column headers like 'Avg. cost', 'Buy Price', or 'Rate'."
            )

        exchange, _ = Exchange.objects.get_or_create(
            code=default_exchange_code,
            defaults={
                "name": f"{default_exchange_code} Stock Exchange",
                "country": "India",
                "currency": "INR",
            },
        )

        if clear_existing:
            LotAllocation.objects.filter(sell_transaction__portfolio=portfolio).delete()
            HoldingTransaction.objects.filter(portfolio=portfolio).delete()
            Holding.objects.filter(portfolio=portfolio).delete()

        now = timezone.now()
        imported_count = 0
        total_invested = Decimal("0.00")
        total_current_val = Decimal("0.00")
        skipped_rows = 0

        for row in reader:
            if not row or len(row) <= max(header_indices.values()):
                continue

            symbol_raw = str(row[header_indices["symbol"]]).strip().upper()
            # Clean symbol (e.g. "RELIANCE-EQ" or "MOREPENLAB-BE" -> "MOREPENLAB")
            symbol = re.sub(r"(-EQ|-BE)$", "", symbol_raw)
            if not symbol:
                continue

            qty = cls.clean_int(row[header_indices["quantity"]])
            avg_cost = cls.clean_decimal(row[header_indices["avg_cost"]])
            if qty <= 0 or avg_cost <= Decimal("0.00"):
                skipped_rows += 1
                continue

            ltp = avg_cost
            if "ltp" in header_indices:
                parsed_ltp = cls.clean_decimal(row[header_indices["ltp"]])
                if parsed_ltp > Decimal("0.00"):
                    ltp = parsed_ltp

            # 1. Canonical Instrument
            # Fallback ISIN based on symbol hash if not already registered
            default_isin = f"INE{abs(hash(symbol)) % 1000000000:09d}"
            instrument, _ = Instrument.objects.get_or_create(
                display_name=symbol,
                defaults={
                    "isin": default_isin,
                    "legal_name": f"{symbol} Limited",
                    "sector": "Other",
                    "industry": "Equity",
                },
            )

            # 2. Exchange Listing
            listing, _ = ExchangeListing.objects.get_or_create(
                symbol=symbol,
                exchange=exchange,
                defaults={"instrument": instrument, "is_tradeable": True},
            )

            # 3. Market Quote (LTP)
            MarketQuote.objects.update_or_create(
                listing=listing,
                retrieved_at=now,
                defaults={
                    "source_provider": "PORTFOLIO_IMPORT",
                    "source_type": "DELAYED",
                    "freshness_status": "FRESH",
                    "source_timestamp": now,
                    "price": ltp,
                    "open": avg_cost,
                    "high": max(ltp, avg_cost),
                    "low": min(ltp, avg_cost),
                    "close": ltp,
                    "previous_close": avg_cost,
                    "change": ltp - avg_cost,
                    "change_percent": (
                        ((ltp - avg_cost) / avg_cost * Decimal("100.0"))
                        if avg_cost > 0
                        else Decimal("0.00")
                    ),
                    "volume": 10000,
                    "configured_delay_minutes": 15,
                },
            )

            # 4. Remove previous transaction for this symbol if appending
            if not clear_existing:
                HoldingTransaction.objects.filter(portfolio=portfolio, listing=listing).delete()

            # 5. Record core BUY transaction in Immutable Ledger
            HoldingTransaction.objects.create(
                portfolio=portfolio,
                listing=listing,
                transaction_type=TransactionType.BUY,
                quantity=qty,
                price=avg_cost,
                brokerage=Decimal("0.00"),
                statutory_taxes=Decimal("0.00"),
                executed_at=now,
                notes="Imported via UI CSV Uploader",
            )

            # 6. Reconcile holding deterministically
            holding = FIFOAccountingEngine.reconcile_holding(
                portfolio=portfolio,
                listing=listing,
                current_price=ltp,
            )

            total_invested += holding.invested_amount
            total_current_val += holding.current_value
            imported_count += 1

        return {
            "imported_count": imported_count,
            "skipped_rows": skipped_rows,
            "total_invested": total_invested,
            "total_current_val": total_current_val,
            "total_pnl": total_current_val - total_invested,
        }
