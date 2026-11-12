from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.core.models import AuditedModel
from apps.instruments.models import ExchangeListing


class Watchlist(AuditedModel):
    """
    User-curated collection of exchange listings for ongoing monitoring.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="watchlists",
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        db_table = "watchlists_watchlist"
        ordering = ["-is_default", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "name"],
                name="unique_user_watchlist_name",
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.user.email})"


class WatchlistItem(AuditedModel):
    """
    Individual stock within a user's watchlist with tracking thresholds and notes.
    """
    watchlist = models.ForeignKey(
        Watchlist,
        on_delete=models.CASCADE,
        related_name="items",
    )
    listing = models.ForeignKey(
        ExchangeListing,
        on_delete=models.CASCADE,
        related_name="watchlist_entries",
    )
    added_price = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=Decimal("0.0000"),
    )
    target_price = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        null=True,
        blank=True,
    )
    stop_loss = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        null=True,
        blank=True,
    )
    notes = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "watchlists_watchlist_item"
        ordering = ["sort_order", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["watchlist", "listing"],
                name="unique_watchlist_listing_item",
            )
        ]

    def __str__(self):
        return f"{self.listing.symbol} in {self.watchlist.name}"
