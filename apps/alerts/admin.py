from django.contrib import admin

from apps.alerts.models import AlertRule


@admin.register(AlertRule)
class AlertRuleAdmin(admin.ModelAdmin):
    list_display = ("user", "listing", "alert_type", "target_value", "is_active", "trigger_count", "last_triggered_at")
    list_filter = ("alert_type", "is_active", "is_market_hours_only")
    search_fields = ("user__username", "listing__symbol", "notes")
