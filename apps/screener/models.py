from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import AuditedModel
from apps.instruments.models import ExchangeListing


class ScreenerConfiguration(AuditedModel):
    """
    Stores user-defined or system-preset screener criteria.
    Criteria is serialized as JSON dictionary of multi-variable filters.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="screener_configs",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    preset_slug = models.SlugField(max_length=50, blank=True, null=True, db_index=True)
    filter_criteria = models.JSONField(default=dict)
    is_system_preset = models.BooleanField(default=False)
    is_public = models.BooleanField(default=False)

    class Meta:
        db_table = "screener_configuration"
        ordering = ["-is_system_preset", "name"]

    def __str__(self):
        prefix = "[System] " if self.is_system_preset else ""
        return f"{prefix}{self.name}"


class ScreenerResult(AuditedModel):
    """
    Audit record capturing screening results at a specific point in time.
    Stores matched metric values and the exact human-readable reasons why conditions passed.
    """
    configuration = models.ForeignKey(
        ScreenerConfiguration,
        on_delete=models.CASCADE,
        related_name="results",
        null=True,
        blank=True,
    )
    listing = models.ForeignKey(
        ExchangeListing,
        on_delete=models.CASCADE,
        related_name="screener_matches",
    )
    matched_values = models.JSONField(default=dict)
    match_reasons = models.JSONField(default=list)
    calculation_version = models.CharField(max_length=20, default="v1.0")
    run_timestamp = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "screener_result"
        ordering = ["-run_timestamp"]

    def __str__(self):
        return f"{self.listing.symbol} match for {self.configuration.name if self.configuration else 'Ad-hoc Scan'}"
