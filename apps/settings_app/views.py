from django.views.generic import TemplateView

from apps.core.mixins import HTMXResponseMixin
from apps.market.models import DataProvider, DataQualityIssue, DataRefreshLog
from integrations.market_data.registry import ProviderRegistry


class DataSourcesView(HTMXResponseMixin, TemplateView):
    """
    Data Sources management and provider health dashboard view.
    """
    template_name = "settings_app/data_sources.html"
    partial_template_name = "settings_app/partials/data_sources_partial.html"
    active_nav = "data_sources"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Data Sources & Provider Health"

        # Ensure providers exist in database
        for p in ProviderRegistry.get_all():
            DataProvider.objects.get_or_create(
                code=p.code,
                defaults={"name": p.name, "priority": p.priority},
            )

        context["providers"] = DataProvider.objects.all().order_by("priority", "code")
        context["recent_logs"] = DataRefreshLog.objects.all().order_by("-started_at")[:10]
        context["quality_issues"] = DataQualityIssue.objects.all().order_by("-detected_at")[:10]
        return context
