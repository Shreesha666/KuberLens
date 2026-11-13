from django.db import models

from apps.core.models import AuditedModel


class Exchange(models.Model):
    """
    Financial market exchange venue (e.g., NSE, BSE).
    """
    code = models.CharField(max_length=10, primary_key=True)  # "NSE", "BSE"
    name = models.CharField(max_length=100)
    country = models.CharField(max_length=50, default="India")
    currency = models.CharField(max_length=10, default="INR")
    timezone = models.CharField(max_length=50, default="Asia/Kolkata")
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "instruments_exchange"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.name}"

class Instrument(AuditedModel):
    """
    Canonical corporate or financial asset entity decoupled from venue listings.
    Identified globally by unique ISIN (e.g., INE002A01018).
    """
    isin = models.CharField(max_length=20, unique=True, db_index=True)
    legal_name = models.CharField(max_length=255)
    display_name = models.CharField(max_length=150)
    sector = models.CharField(max_length=100, blank=True, db_index=True)
    industry = models.CharField(max_length=100, blank=True, db_index=True)
    market_cap_category = models.CharField(
        max_length=20,
        choices=[
            ("LARGE", "Large Cap"),
            ("MID", "Mid Cap"),
            ("SMALL", "Small Cap"),
            ("MICRO", "Micro Cap"),
        ],
        default="LARGE",
        db_index=True,
    )
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "instruments_instrument"
        ordering = ["display_name"]
        indexes = [
            models.Index(fields=["sector", "industry"]),
        ]

    def __str__(self):
        return f"{self.display_name} ({self.isin})"

    @property
    def name(self) -> str:
        """Alias for display_name to ensure robust template compatibility."""
        return self.display_name or self.legal_name or ""

class ExchangeListing(AuditedModel):
    """
    Venue-specific listing instance for an instrument (e.g., RELIANCE on NSE, 500325 on BSE).
    """
    instrument = models.ForeignKey(
        Instrument,
        on_delete=models.CASCADE,
        related_name="listings",
        db_index=True,
    )
    exchange = models.ForeignKey(
        Exchange,
        on_delete=models.CASCADE,
        related_name="listings",
        db_index=True,
    )
    symbol = models.CharField(max_length=30, db_index=True)  # e.g., "RELIANCE" or "500325"
    trading_symbol = models.CharField(max_length=50)         # e.g., "RELIANCE-EQ"
    series_or_group = models.CharField(max_length=10, default="EQ")  # "EQ", "A", etc.
    instrument_token = models.CharField(max_length=50, blank=True, null=True)
    lot_size = models.PositiveIntegerField(default=1)
    is_primary = models.BooleanField(default=True)
    is_tradeable = models.BooleanField(default=True)

    class Meta:
        db_table = "instruments_exchange_listing"
        ordering = ["symbol"]
        constraints = [
            models.UniqueConstraint(
                fields=["exchange", "symbol"],
                name="unique_exchange_symbol",
            )
        ]
        indexes = [
            models.Index(fields=["exchange", "symbol"]),
            models.Index(fields=["exchange", "is_tradeable"]),
        ]

    def __str__(self):
        return f"{self.exchange.code}:{self.symbol}"
