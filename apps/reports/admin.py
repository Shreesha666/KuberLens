from django.contrib import admin

from apps.reports.models import GeneratedReport


@admin.register(GeneratedReport)
class GeneratedReportAdmin(admin.ModelAdmin):
    list_display = ["title", "user", "report_type", "export_format", "record_count", "created_at"]
    list_filter = ["report_type", "export_format", "created_at"]
    search_fields = ["title", "user__username", "user__email"]
    readonly_fields = ["created_at", "updated_at"]

