import json
import logging
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from apps.core.mixins import HTMXResponseMixin
from apps.screener.models import ScreenerConfiguration
from apps.watchlists.models import Watchlist
from services.screener.engine import SYSTEM_PRESETS, ScreenerEngine

logger = logging.getLogger(__name__)


class ScreenerView(LoginRequiredMixin, HTMXResponseMixin, TemplateView):
    """
    Interactive Stock Screener view supporting preset selections,
    dynamic multi-parameter filtering, match explanations, and preset persistence.
    """
    template_name = "screener/screener.html"
    partial_template_name = "screener/partials/screener_partial.html"
    active_nav = "screener"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Stock Screener - Technical & Fundamental Scanner"
        context["system_presets"] = SYSTEM_PRESETS

        # Saved user configurations
        user_configs = ScreenerConfiguration.objects.filter(user=self.request.user)
        context["user_configs"] = user_configs

        # User watchlists for quick adding
        context["user_watchlists"] = Watchlist.objects.filter(user=self.request.user)

        # Determine active filters
        preset_key = self.request.GET.get("preset")
        config_id = self.request.GET.get("config_id")
        active_filters = {}
        active_preset_name = None
        active_preset_desc = None

        if preset_key and preset_key in SYSTEM_PRESETS:
            active_filters = SYSTEM_PRESETS[preset_key]["filters"].copy()
            active_preset_name = SYSTEM_PRESETS[preset_key]["name"]
            active_preset_desc = SYSTEM_PRESETS[preset_key]["description"]
            context["active_preset"] = preset_key
        elif config_id:
            cfg = get_object_or_404(ScreenerConfiguration, id=config_id, user=self.request.user)
            active_filters = cfg.filter_criteria.copy()
            active_preset_name = cfg.name
            active_preset_desc = cfg.description
            context["active_config_id"] = str(cfg.id)
        else:
            # Read from query parameters
            for field in [
                "market_cap",
                "sector",
                "trend_signal",
                "min_rsi",
                "max_rsi",
                "min_score",
                "max_pe",
                "min_pe",
                "min_roe",
                "min_roce",
                "max_debt_to_equity",
                "min_sales_growth",
                "min_dividend_yield",
            ]:
                val = self.request.GET.get(field)
                if val:
                    active_filters[field] = val

            for flag in ["above_sma20", "above_sma50", "above_sma200"]:
                if self.request.GET.get(flag) in ("on", "true", "1"):
                    active_filters[flag] = True

        context["active_filters"] = active_filters
        context["active_preset_name"] = active_preset_name
        context["active_preset_desc"] = active_preset_desc
        context["filters_json"] = json.dumps(
            {k: str(v) if isinstance(v, Decimal) else v for k, v in active_filters.items()}
        )

        from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator

        # Run screener
        results = ScreenerEngine.run_screen(filters=active_filters)
        total_matched = len(results)
        context["matched_count"] = total_matched

        # Pagination support (defaults to 25 stocks per page)
        per_page = self.request.GET.get("per_page", 25)
        try:
            per_page = int(per_page)
            if per_page not in [10, 25, 50, 100]:
                per_page = 25
        except (ValueError, TypeError):
            per_page = 25

        paginator = Paginator(results, per_page)
        page_number = self.request.GET.get("page", 1)
        try:
            page_obj = paginator.get_page(page_number)
        except (EmptyPage, PageNotAnInteger):
            page_obj = paginator.get_page(1)

        context["paginator"] = paginator
        context["page_obj"] = page_obj
        context["results"] = page_obj.object_list
        context["per_page"] = per_page
        if paginator.num_pages > 1:
            context["elided_page_range"] = paginator.get_elided_page_range(
                page_obj.number, on_each_side=2, on_ends=1
            )
        else:
            context["elided_page_range"] = []

        # Preserved query string for pagination links
        query_params = self.request.GET.copy()
        query_params.pop("page", None)
        query_params.pop("per_page", None)
        context["filter_querystring"] = query_params.urlencode()

        return context

    def post(self, request, *args, **kwargs):
        """
        Saves a custom screener configuration.
        """
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        filters_json = request.POST.get("filters_json", "{}")

        if not name:
            messages.error(request, "Please provide a name for this screener configuration.")
            return redirect("screener:index")

        try:
            criteria = json.loads(filters_json)
        except Exception:
            criteria = {}

        cfg = ScreenerConfiguration.objects.create(
            user=request.user,
            name=name,
            description=description,
            filter_criteria=criteria,
        )
        messages.success(request, f"Saved screener configuration '{cfg.name}'.")

        redirect_url = f"{reverse('screener:index')}?config_id={cfg.id}"
        if request.htmx:
            resp = HttpResponseRedirect(redirect_url)
            resp["HX-Redirect"] = redirect_url
            return resp
        return redirect(redirect_url)


class ScreenerExportView(LoginRequiredMixin, View):
    """
    Exports current screening results to a CSV file.
    """
    def get(self, request, *args, **kwargs):
        preset_key = request.GET.get("preset")
        filters = {}
        if preset_key and preset_key in SYSTEM_PRESETS:
            filters = SYSTEM_PRESETS[preset_key]["filters"]
        else:
            for field in [
                "market_cap",
                "sector",
                "trend_signal",
                "min_rsi",
                "max_rsi",
                "min_score",
                "max_pe",
                "min_pe",
                "min_roe",
                "min_roce",
                "max_debt_to_equity",
            ]:
                val = request.GET.get(field)
                if val:
                    filters[field] = val

        results = ScreenerEngine.run_screen(filters=filters)
        csv_data = ScreenerEngine.export_to_csv(results)

        response = HttpResponse(csv_data, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="screener_results.csv"'
        return response


class ScreenerDeleteConfigView(LoginRequiredMixin, View):
    """
    Deletes a saved custom screener configuration.
    """
    def post(self, request, pk, *args, **kwargs):
        cfg = get_object_or_404(ScreenerConfiguration, id=pk, user=request.user)
        name = cfg.name
        cfg.delete()
        messages.success(request, f"Deleted screener configuration '{name}'.")

        redirect_url = reverse("screener:index")
        if request.htmx:
            resp = HttpResponseRedirect(redirect_url)
            resp["HX-Redirect"] = redirect_url
            return resp
        return redirect(redirect_url)
