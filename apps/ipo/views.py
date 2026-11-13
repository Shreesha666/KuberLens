"""
IPO Intelligence Views.
Provides executive dashboard, categorized issue listings (Live, Upcoming, Closed, SME),
chronological issue calendar, and detailed IPO research profile.
"""
from decimal import Decimal

from django.db.models import Avg, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.generic import DetailView, TemplateView

from apps.core.mixins import HTMXResponseMixin
from apps.ipo.models import IPOMaster, IPOStatus, IssueType
from services.ipo.lifecycle import get_status_badge_class, get_timeline_milestones
from services.ipo.research import compute_financial_metrics
from services.ipo.subscription import get_subscription_summary


class IPODashboardView(HTMXResponseMixin, TemplateView):
    """
    Executive IPO Dashboard:
    Summarizes live, upcoming, and closed issues, capital mobilization,
    listing returns, and category breakdowns.
    """
    template_name = "ipo/dashboard.html"
    partial_template_name = "ipo/partials/dashboard_partial.html"
    active_nav = "ipo_dashboard"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().date()
        context["page_title"] = "IPO Intelligence Centre"
        context["active_nav"] = "ipo_dashboard"

        # 1. High-Level KPI Metrics
        live_ipos_qs = IPOMaster.objects.filter(
            Q(status=IPOStatus.LIVE) | (Q(open_date__lte=today) & Q(close_date__gte=today))
        ).distinct()
        upcoming_ipos_qs = IPOMaster.objects.filter(
            Q(status=IPOStatus.UPCOMING) | Q(open_date__gt=today)
        ).distinct()
        listed_ipos_qs = IPOMaster.objects.filter(status=IPOStatus.LISTED)

        context["live_count"] = live_ipos_qs.count()
        context["upcoming_count"] = upcoming_ipos_qs.count()
        context["listed_count"] = listed_ipos_qs.count()

        # Total capital mobilized (Cr)
        total_mobilized = IPOMaster.objects.aggregate(Sum("total_issue_size_cr"))["total_issue_size_cr__sum"] or Decimal("0.00")
        context["total_mobilized_cr"] = total_mobilized

        # Average listing gain for listed IPOs
        avg_listing_gain = listed_ipos_qs.aggregate(Avg("listing_day_gain_percent"))["listing_day_gain_percent__avg"] or Decimal("0.00")
        context["avg_listing_gain"] = avg_listing_gain

        # Mainboard vs SME split
        context["mainboard_count"] = IPOMaster.objects.filter(issue_type=IssueType.MAINBOARD).count()
        context["sme_count"] = IPOMaster.objects.filter(issue_type=IssueType.SME).count()

        # 2. Spotlight Live & Upcoming Issues
        context["spotlight_issues"] = (
            IPOMaster.objects.filter(
                status__in=[IPOStatus.LIVE, IPOStatus.UPCOMING, IPOStatus.ALLOTMENT_FINALIZED]
            )
            .select_related("listing")
            .order_by("open_date", "company_name")[:8]
        )

        # 3. Recent Listing Performance Tracker
        context["recent_listings"] = (
            listed_ipos_qs.select_related("listing")
            .order_by("-listing_date")[:6]
        )

        return context


class IPOIssuesListView(HTMXResponseMixin, TemplateView):
    """
    Catalog of IPO issues with filtering across Live, Upcoming, Closed, and SME.
    """
    template_name = "ipo/issues_list.html"
    partial_template_name = "ipo/partials/issues_list_partial.html"
    active_nav = "ipo_issues"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().date()
        context["active_nav"] = "ipo_issues"

        tab = self.request.GET.get("tab", "all").lower()
        issue_type = self.request.GET.get("type", "all").upper()
        search_query = self.request.GET.get("q", "").strip()
        sort_by = self.request.GET.get("sort", "open_date")

        qs = IPOMaster.objects.all().select_related("listing")

        # Tab Filtering
        if tab == "live":
            qs = qs.filter(Q(status=IPOStatus.LIVE) | (Q(open_date__lte=today) & Q(close_date__gte=today)))
        elif tab == "upcoming":
            qs = qs.filter(Q(status__in=[IPOStatus.UPCOMING, IPOStatus.DRHP_FILED, IPOStatus.SEBI_APPROVED]) | Q(open_date__gt=today))
        elif tab == "closed":
            qs = qs.filter(status__in=[IPOStatus.CLOSED, IPOStatus.ALLOTMENT_FINALIZED, IPOStatus.LISTED])

        # Segment Filtering
        if issue_type in [IssueType.MAINBOARD, IssueType.SME]:
            qs = qs.filter(issue_type=issue_type)

        # Search Query
        if search_query:
            qs = qs.filter(
                Q(symbol__icontains=search_query) |
                Q(company_name__icontains=search_query) |
                Q(sector__icontains=search_query) |
                Q(industry__icontains=search_query)
            )

        # Sorting
        if sort_by == "size_desc":
            qs = qs.order_by("-total_issue_size_cr")
        elif sort_by == "gain_desc":
            qs = qs.order_by("-listing_day_gain_percent")
        elif sort_by == "name_asc":
            qs = qs.order_by("company_name")
        else:
            qs = qs.order_by("-open_date", "company_name")

        context["ipos"] = list(qs)
        context["current_tab"] = tab
        context["current_type"] = issue_type
        context["search_query"] = search_query
        context["sort_by"] = sort_by
        context["total_count"] = len(context["ipos"])

        # Tab counts
        context["all_count"] = IPOMaster.objects.count()
        context["live_count"] = IPOMaster.objects.filter(
            Q(status=IPOStatus.LIVE) | (Q(open_date__lte=today) & Q(close_date__gte=today))
        ).count()
        context["upcoming_count"] = IPOMaster.objects.filter(
            Q(status__in=[IPOStatus.UPCOMING, IPOStatus.DRHP_FILED, IPOStatus.SEBI_APPROVED]) | Q(open_date__gt=today)
        ).count()
        context["closed_count"] = IPOMaster.objects.filter(
            status__in=[IPOStatus.CLOSED, IPOStatus.ALLOTMENT_FINALIZED, IPOStatus.LISTED]
        ).count()

        return context


class IPOCalendarView(HTMXResponseMixin, TemplateView):
    """
    Chronological timeline of upcoming and past IPO events:
    Open Dates, Close Dates, Basis of Allotment, and Listing Dates.
    """
    template_name = "ipo/calendar.html"
    partial_template_name = "ipo/partials/calendar_partial.html"
    active_nav = "ipo_calendar"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().date()
        context["page_title"] = "IPO Calendar & Events Timeline"
        context["active_nav"] = "ipo_calendar"

        ipos = IPOMaster.objects.all().order_by("open_date")
        events = []

        for ipo in ipos:
            if ipo.open_date:
                events.append({
                    "date": ipo.open_date,
                    "event_type": "ISSUE_OPENS",
                    "label": "Issue Opens",
                    "badge_class": "bg-success text-white",
                    "ipo": ipo,
                    "is_past": ipo.open_date < today,
                    "is_today": ipo.open_date == today,
                })
            if ipo.close_date:
                events.append({
                    "date": ipo.close_date,
                    "event_type": "ISSUE_CLOSES",
                    "label": "Issue Closes",
                    "badge_class": "bg-danger text-white",
                    "ipo": ipo,
                    "is_past": ipo.close_date < today,
                    "is_today": ipo.close_date == today,
                })
            if ipo.allotment_date:
                events.append({
                    "date": ipo.allotment_date,
                    "event_type": "ALLOTMENT",
                    "label": "Basis of Allotment",
                    "badge_class": "bg-primary-subtle text-primary border border-primary-subtle",
                    "ipo": ipo,
                    "is_past": ipo.allotment_date < today,
                    "is_today": ipo.allotment_date == today,
                })
            if ipo.listing_date:
                events.append({
                    "date": ipo.listing_date,
                    "event_type": "LISTING",
                    "label": "Listing Day",
                    "badge_class": "bg-dark text-white",
                    "ipo": ipo,
                    "is_past": ipo.listing_date < today,
                    "is_today": ipo.listing_date == today,
                })

        events.sort(key=lambda x: x["date"])
        context["events"] = events
        context["upcoming_events"] = [e for e in events if not e["is_past"]]
        context["past_events"] = [e for e in events if e["is_past"]]
        return context


class IPOResearchListView(HTMXResponseMixin, TemplateView):
    """
    IPO Fundamental Research & Valuation Directory:
    Compares company financials, 3-year revenue CAGR, operating margins,
    and valuation multiples across all active issues.
    """
    template_name = "ipo/research_list.html"
    partial_template_name = "ipo/partials/research_list_partial.html"
    active_nav = "ipo_research"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "IPO Fundamental Research & Valuation"
        context["active_nav"] = "ipo_research"

        sort_by = self.request.GET.get("sort", "score_desc")
        sector_filter = self.request.GET.get("sector", "all")

        ipos_qs = (
            IPOMaster.objects.all()
            .select_related("fundamentals", "scoring", "listing")
            .prefetch_related("subscriptions")
        )

        if sector_filter and sector_filter != "all":
            ipos_qs = ipos_qs.filter(sector=sector_filter)

        items = []
        for ipo in ipos_qs:
            fund = getattr(ipo, "fundamentals", None)
            metrics = compute_financial_metrics(fund, ipo)
            score_obj = getattr(ipo, "scoring", None)
            sub_summary = get_subscription_summary(ipo)

            items.append({
                "ipo": ipo,
                "fundamentals": fund,
                "metrics": metrics,
                "score": score_obj.overall_score if score_obj else Decimal("0.00"),
                "recommendation": score_obj.get_recommendation_display() if score_obj else "Under Review",
                "total_subscription": sub_summary["latest"].total_subscription if sub_summary["latest"] else None,
            })

        # Sorting
        if sort_by == "cagr_desc":
            items.sort(key=lambda x: (x["metrics"]["cagr_3yr"] or Decimal("-999.0")), reverse=True)
        elif sort_by == "pe_asc":
            items.sort(key=lambda x: (x["fundamentals"].post_issue_pe if x["fundamentals"] and x["fundamentals"].post_issue_pe else Decimal("9999.0")))
        elif sort_by == "size_desc":
            items.sort(key=lambda x: (x["ipo"].total_issue_size_cr or Decimal("0.0")), reverse=True)
        else:  # score_desc
            items.sort(key=lambda x: x["score"], reverse=True)

        context["research_items"] = items
        context["sectors"] = sorted({i.sector for i in IPOMaster.objects.exclude(sector="")})
        context["current_sector"] = sector_filter
        context["sort_by"] = sort_by
        return context


class IPODetailView(HTMXResponseMixin, DetailView):
    """
    Comprehensive IPO Research Profile:
    Issue specs, price bands, lot allocations, timeline progress stepper,
    intermediaries, live subscription momentum, and extracted financial fundamentals.
    """
    model = IPOMaster
    template_name = "ipo/detail.html"
    partial_template_name = "ipo/partials/detail_partial.html"
    context_object_name = "ipo"
    active_nav = "ipo_issues"

    def get_object(self, queryset=None):
        symbol = self.kwargs.get("symbol", "").upper()
        return get_object_or_404(
            IPOMaster.objects.select_related("listing", "fundamentals", "scoring"),
            symbol=symbol,
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        ipo = self.object
        active_tab = self.request.GET.get("tab", "overview").lower()

        context["page_title"] = f"{ipo.company_name} ({ipo.symbol}) - IPO Profile"
        context["active_nav"] = "ipo_issues"
        context["active_tab"] = active_tab
        context["status_badge"] = get_status_badge_class(ipo.status)
        context["timeline_steps"] = get_timeline_milestones(ipo)

        # 1. Subscription Analytics (Phase B)
        sub_summary = get_subscription_summary(ipo)
        context["subscription_summary"] = sub_summary
        context["subscription_snapshots"] = list(ipo.subscriptions.order_by("-day_number"))
        context["latest_subscription"] = sub_summary["latest"]

        # 2. Fundamentals & Financial Extraction (Phase B)
        fund = getattr(ipo, "fundamentals", None)
        context["fundamentals"] = fund
        context["research_metrics"] = compute_financial_metrics(fund, ipo)

        # 3. Regulatory Documents Vault (Phase B)
        context["documents"] = list(ipo.documents.order_by("-filing_date", "doc_type"))

        # 4. Scoring & GMP
        context["scoring"] = getattr(ipo, "scoring", None)
        context["latest_gmp"] = ipo.gmp_records.order_by("-observed_at").first()

        return context
