from django.contrib import admin

from apps.ipo.models import (
    IPOApplication,
    IPOFundamentals,
    IPOGMPRecord,
    IPOMaster,
    IPOScoring,
    IPOSubscriptionSnapshot,
)


@admin.register(IPOMaster)
class IPOMasterAdmin(admin.ModelAdmin):
    list_display = ("symbol", "company_name", "issue_type", "status", "price_band_display", "total_issue_size_cr", "open_date", "close_date", "listing_date")
    list_filter = ("issue_type", "status", "exchange", "sector")
    search_fields = ("symbol", "company_name", "isin")
    date_hierarchy = "open_date"


@admin.register(IPOSubscriptionSnapshot)
class IPOSubscriptionSnapshotAdmin(admin.ModelAdmin):
    list_display = ("ipo", "day_number", "total_subscription", "qib_subscription", "nii_subscription", "retail_subscription", "snapshot_timestamp")
    list_filter = ("day_number",)
    search_fields = ("ipo__symbol", "ipo__company_name")


@admin.register(IPOFundamentals)
class IPOFundamentalsAdmin(admin.ModelAdmin):
    list_display = ("ipo", "revenue_fy_latest", "ebitda_margin_percent", "pat_latest", "roe_percent", "post_issue_pe")
    search_fields = ("ipo__symbol", "ipo__company_name")


@admin.register(IPOScoring)
class IPOScoringAdmin(admin.ModelAdmin):
    list_display = ("ipo", "overall_score", "recommendation", "listing_gain_potential", "long_term_potential")
    list_filter = ("recommendation", "listing_gain_potential")
    search_fields = ("ipo__symbol", "ipo__company_name")


@admin.register(IPOGMPRecord)
class IPOGMPRecordAdmin(admin.ModelAdmin):
    list_display = ("ipo", "reported_gmp", "estimated_listing_price", "estimated_gain_percent", "source_name", "observed_at")
    search_fields = ("ipo__symbol",)


@admin.register(IPOApplication)
class IPOApplicationAdmin(admin.ModelAdmin):
    list_display = ("user", "ipo", "investor_category", "lots_applied", "applied_amount", "mandate_status", "allotment_status")
    list_filter = ("investor_category", "mandate_status", "allotment_status")
    search_fields = ("user__email", "ipo__symbol", "application_number")
