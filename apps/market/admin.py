from django.contrib import admin

from apps.market.models import (
    DataProvider,
    DataQualityIssue,
    DataRefreshLog,
    HistoricalCandle,
    MarketQuote,
)


@admin.register(HistoricalCandle)
class HistoricalCandleAdmin(admin.ModelAdmin):
    list_display = (
        "listing",
        "timestamp",
        "interval",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "source_provider",
        "retrieved_at",
    )
    list_filter = ("interval", "source_provider")
    search_fields = ("listing__symbol", "source_provider")
    date_hierarchy = "timestamp"


@admin.register(DataQualityIssue)
class DataQualityIssueAdmin(admin.ModelAdmin):
    list_display = ("listing", "issue_type", "severity", "detected_at")
    list_filter = ("issue_type", "severity")
    search_fields = ("listing__symbol", "issue_type")
    date_hierarchy = "detected_at"


@admin.register(MarketQuote)
class MarketQuoteAdmin(admin.ModelAdmin):
    list_display = (
        "listing",
        "price",
        "change",
        "change_percent",
        "volume",
        "source_provider",
        "freshness_status",
        "retrieved_at",
    )
    list_filter = ("source_provider", "freshness_status")
    search_fields = ("listing__symbol",)


@admin.register(DataProvider)
class DataProviderAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "priority", "is_enabled", "health_status")
    list_filter = ("is_enabled", "health_status")
    search_fields = ("code", "name")


@admin.register(DataRefreshLog)
class DataRefreshLogAdmin(admin.ModelAdmin):
    list_display = ("provider", "data_type", "status", "records_ingested", "started_at", "completed_at")
    list_filter = ("data_type", "status")
    search_fields = ("provider__code", "data_type")
