"""
Portfolio Data Models.
Defines user portfolio containers, cash balances, and multi-portfolio ownership.
"""
from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.core.models import AuditedModel


class Portfolio(AuditedModel):
    """
    User portfolio container tracking aggregate asset allocations and cash balance.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="portfolios",
        db_index=True,
    )
    name = models.CharField(max_length=100, default="Main Portfolio")
    currency = models.CharField(max_length=10, default="INR")
    cash_balance = models.DecimalField(
        max_digits=16,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    is_default = models.BooleanField(default=True)
    description = models.TextField(blank=True)

    class Meta:
        db_table = "portfolio_portfolio"
        ordering = ["-is_default", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "name"],
                name="unique_user_portfolio_name",
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.user.email})"
