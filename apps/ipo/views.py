"""
IPO Intelligence Views.
Provides executive dashboard, categorized issue listings (Live, Upcoming, Closed, SME),
chronological issue calendar, and detailed IPO research profile.
"""
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import Avg, Q, Sum
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import DetailView, ListView, TemplateView, View

from apps.core.mixins import HTMXResponseMixin
from apps.holdings.models import HoldingTransaction, TransactionType
from apps.instruments.models import ExchangeListing
from apps.ipo.models import IPOApplication, IPOMaster, IPOStatus, IssueType
from apps.portfolio.models import Portfolio
from services.ipo.comparison import compare_ipos
from services.ipo.lifecycle import get_status_badge_class, get_timeline_milestones
from services.ipo.performance import (
    compute_ipo_performance_metrics,
    get_listed_ipos_performance_summary,
)
from services.ipo.planner import calculate_bid_plan, estimate_allotment_probability
from services.ipo.research import compute_financial_metrics
from services.ipo.scoring import evaluate_ipo_scoring, get_radar_chart_geometry
from services.ipo.subscription import get_subscription_summary
from services.portfolio.accounting import FIFOAccountingEngine


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

        # Pagination (15 issues per page)
        page_number = self.request.GET.get("page", 1)
        paginator = Paginator(qs, 15)
        page_obj = paginator.get_page(page_number)

        context["page_obj"] = page_obj
        context["ipos"] = page_obj.object_list
        context["current_tab"] = tab
        context["current_type"] = issue_type
        context["search_query"] = search_query
        context["sort_by"] = sort_by
        context["total_count"] = paginator.count
        context["page_range"] = paginator.get_elided_page_range(
            number=page_obj.number, on_each_side=2, on_ends=1
        )

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
            if not score_obj:
                evaluate_ipo_scoring(ipo, save=True)
                ipo.refresh_from_db()
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

        # 4. Scoring & Quantitative Evaluation (Phase C)
        scoring = getattr(ipo, "scoring", None)
        if not scoring:
            evaluate_ipo_scoring(ipo, save=True)
            ipo.refresh_from_db()
            scoring = getattr(ipo, "scoring", None)
        context["scoring"] = scoring

        if scoring:
            context["scoring_pillars"] = [
                {
                    "key": "business",
                    "name": "Business Quality & Moat",
                    "weight": "20%",
                    "score": scoring.business_score,
                    "icon": "bi-buildings",
                    "description": "Market leadership, moat & operating franchise stability",
                },
                {
                    "key": "financials",
                    "name": "Financial Health & Solvency",
                    "weight": "20%",
                    "score": scoring.financials_score,
                    "icon": "bi-cash-coin",
                    "description": "Operating cash flow, profitability & debt-to-equity ratio",
                },
                {
                    "key": "valuation",
                    "name": "Valuation & Price Attractiveness",
                    "weight": "20%",
                    "score": scoring.valuation_score,
                    "icon": "bi-tags",
                    "description": "Post-issue P/E & P/B vs listed industry benchmark peers",
                },
                {
                    "key": "growth",
                    "name": "Growth Trajectory & Scalability",
                    "weight": "15%",
                    "score": scoring.growth_score,
                    "icon": "bi-graph-up-arrow",
                    "description": "3-Year historical revenue CAGR & forward business scalability",
                },
                {
                    "key": "governance",
                    "name": "Management Quality & Governance",
                    "weight": "10%",
                    "score": scoring.governance_score,
                    "icon": "bi-shield-check",
                    "description": "Post-issue promoter retention & lead manager pedigree",
                },
                {
                    "key": "structure",
                    "name": "IPO Structure & Capital Use",
                    "weight": "10%",
                    "score": scoring.structure_score,
                    "icon": "bi-pie-chart",
                    "description": "Fresh growth issue vs OFS exit ratio & deployment clarity",
                },
                {
                    "key": "demand",
                    "name": "Subscription & Market Demand",
                    "weight": "5%",
                    "score": scoring.demand_score,
                    "icon": "bi-activity",
                    "description": "Bidding demand velocity & unofficial grey market sentiment",
                },
            ]
            context["radar_geometry"] = get_radar_chart_geometry(scoring)

        rec_badges = {
            "STRONG_RESEARCH_CANDIDATE": "bg-success text-white border-0",
            "CONSIDER_APPLYING": "bg-primary text-white border-0",
            "APPLY_WITH_CAUTION": "bg-warning text-dark border-0",
            "AVOID": "bg-danger text-white border-0",
            "INSUFFICIENT_DATA": "bg-secondary text-white border-0",
        }
        context["recommendation_badge"] = rec_badges.get(
            scoring.recommendation if scoring else "", "bg-secondary text-white"
        )
        context["latest_gmp"] = ipo.gmp_records.order_by("-observed_at").first()

        # 5. Interactive Bid Planner & Allotment Probability (Phase D)
        planner_category = self.request.GET.get("category", "RETAIL").upper()
        try:
            planner_lots = int(self.request.GET.get("lots", 1))
        except (ValueError, TypeError):
            planner_lots = 1
        planner_cutoff = self.request.GET.get("cutoff", "true").lower() in ["true", "1", "yes"]
        try:
            planner_pans = int(self.request.GET.get("pans", 1))
        except (ValueError, TypeError):
            planner_pans = 1

        context["bid_plan"] = calculate_bid_plan(
            ipo=ipo,
            category=planner_category,
            lots=planner_lots,
            is_cutoff=planner_cutoff,
        )
        context["prob_estimate"] = estimate_allotment_probability(
            ipo=ipo,
            category=planner_category,
            lots_applied=planner_lots,
            num_pan_accounts=planner_pans,
        )
        context["planner_category"] = planner_category
        context["planner_lots"] = planner_lots
        context["planner_cutoff"] = planner_cutoff
        context["planner_pans"] = planner_pans

        # 6. Post-Listing Performance Analytics (Phase F)
        if active_tab == "performance" or ipo.status == IPOStatus.LISTED or ipo.listing_date:
            context["performance_metrics"] = compute_ipo_performance_metrics(ipo)

        return context


class IPOBidPlannerView(HTMXResponseMixin, TemplateView):
    """
    Interactive IPO Bid Planner & Retail Lottery Probability Estimator.
    Computes lot allocations, category eligibility (Retail vs sHNI vs bHNI),
    UPI vs ASBA payment routing, and multi-PAN family allotment probabilities.
    """
    template_name = "ipo/bid_planner.html"
    partial_template_name = "ipo/partials/bid_planner_partial.html"
    active_nav = "ipo_issues"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        symbol = self.kwargs.get("symbol", "").upper()
        ipo = get_object_or_404(
            IPOMaster.objects.select_related("listing", "fundamentals", "scoring"),
            symbol=symbol,
        )
        context["ipo"] = ipo
        context["page_title"] = f"{ipo.company_name} ({ipo.symbol}) - Interactive Bid Planner"
        context["active_nav"] = "ipo_issues"

        category = self.request.GET.get("category", "RETAIL").upper()
        try:
            lots = int(self.request.GET.get("lots", 1))
        except (ValueError, TypeError):
            lots = 1

        is_cutoff = self.request.GET.get("cutoff", "true").lower() in ["true", "1", "yes"]

        custom_price = None
        price_raw = self.request.GET.get("price", "")
        if price_raw and not is_cutoff:
            try:
                custom_price = Decimal(price_raw)
            except (ValueError, TypeError):
                custom_price = None

        budget = None
        budget_raw = self.request.GET.get("budget", "")
        if budget_raw:
            try:
                budget = Decimal(budget_raw)
            except (ValueError, TypeError):
                budget = None

        try:
            pans = int(self.request.GET.get("pans", 1))
        except (ValueError, TypeError):
            pans = 1

        bid_plan = calculate_bid_plan(
            ipo=ipo,
            category=category,
            lots=lots,
            custom_bid_price=custom_price,
            is_cutoff=is_cutoff,
            budget=budget,
        )
        prob_estimate = estimate_allotment_probability(
            ipo=ipo,
            category=category,
            lots_applied=lots,
            num_pan_accounts=pans,
        )

        context["bid_plan"] = bid_plan
        context["prob_estimate"] = prob_estimate
        context["planner_category"] = category
        context["planner_lots"] = lots
        context["planner_cutoff"] = is_cutoff
        context["planner_price"] = custom_price
        context["planner_budget"] = budget
        context["planner_pans"] = pans

        return context


class IPOApplicationListView(LoginRequiredMixin, HTMXResponseMixin, ListView):
    """
    Personal Allotment & Bid Tracker:
    Tracks user's IPO bids, UPI mandate statuses, allotment outcomes,
    refund amounts, and 1-click portfolio transfer.
    """
    model = IPOApplication
    template_name = "ipo/applications_list.html"
    partial_template_name = "ipo/partials/applications_list_partial.html"
    context_object_name = "applications"
    active_nav = "ipo_applications"

    def get_queryset(self):
        qs = IPOApplication.objects.filter(user=self.request.user).select_related("ipo", "ipo__listing")
        status_filter = self.request.GET.get("status", "ALL").upper()
        if status_filter == "AWAITING":
            qs = qs.filter(allotment_status="AWAITING")
        elif status_filter == "ALLOTTED":
            qs = qs.filter(allotment_status__in=["ALLOTTED", "PARTIALLY_ALLOTTED"])
        elif status_filter == "REFUNDED":
            qs = qs.filter(allotment_status__in=["NOT_ALLOTTED", "REFUNDED"])
        return qs.order_by("-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_apps = IPOApplication.objects.filter(user=self.request.user)

        total_blocked = user_apps.filter(
            allotment_status="AWAITING",
            mandate_status="APPROVED",
        ).aggregate(Sum("applied_amount"))["applied_amount__sum"] or Decimal("0.00")

        total_allotted = user_apps.filter(
            allotment_status__in=["ALLOTTED", "PARTIALLY_ALLOTTED"]
        ).aggregate(Sum("allotted_amount"))["allotted_amount__sum"] or Decimal("0.00")

        total_refund = Decimal("0.00")
        for app in user_apps:
            if app.allotment_status != "AWAITING":
                total_refund += app.refund_amount

        context["page_title"] = "My IPO Applications & Allotment Tracker"
        context["active_nav"] = "ipo_applications"
        context["total_applications_count"] = user_apps.count()
        context["total_blocked_funds"] = total_blocked
        context["total_allotted_funds"] = total_allotted
        context["total_refund_funds"] = total_refund
        context["current_status_filter"] = self.request.GET.get("status", "ALL").upper()

        today = timezone.now().date()
        context["available_ipos"] = IPOMaster.objects.filter(
            Q(status__in=[IPOStatus.LIVE, IPOStatus.UPCOMING]) | Q(close_date__gte=today)
        ).order_by("company_name")
        return context


class IPOLogApplicationView(LoginRequiredMixin, View):
    """
    Log a new IPO Application from Bid Planner or standalone tracker modal.
    """
    def post(self, request, *args, **kwargs):
        ipo_id = request.POST.get("ipo_id")
        symbol = request.POST.get("symbol")
        if ipo_id:
            ipo = get_object_or_404(IPOMaster, pk=ipo_id)
        elif symbol:
            ipo = get_object_or_404(IPOMaster, symbol=symbol.upper())
        else:
            messages.error(request, "IPO issue must be specified.")
            return redirect("ipo:applications")

        investor_category = request.POST.get("investor_category", "RETAIL")
        try:
            lots_applied = int(request.POST.get("lots_applied", 1) or 1)
        except (ValueError, TypeError):
            lots_applied = 1

        is_cutoff_bid = request.POST.get("is_cutoff_bid", "true").lower() in ["true", "1", "yes", "on"]

        bid_price_raw = request.POST.get("bid_price")
        if is_cutoff_bid or not bid_price_raw:
            bid_price = ipo.effective_upper_price or Decimal("100.00")
        else:
            try:
                bid_price = Decimal(bid_price_raw)
            except (ValueError, TypeError):
                bid_price = ipo.effective_upper_price or Decimal("100.00")

        shares_applied = lots_applied * ipo.lot_size
        applied_amount = Decimal(shares_applied) * bid_price

        application_number = request.POST.get("application_number", "").strip()
        demat_account = request.POST.get("demat_account", "").strip()
        listing_strategy = request.POST.get("listing_strategy", "HOLD")
        mandate_status = request.POST.get("mandate_status", "APPROVED")
        notes = request.POST.get("notes", "").strip()

        IPOApplication.objects.create(
            user=request.user,
            ipo=ipo,
            investor_category=investor_category,
            application_number=application_number,
            lots_applied=lots_applied,
            shares_applied=shares_applied,
            bid_price=bid_price,
            applied_amount=applied_amount,
            is_cutoff_bid=is_cutoff_bid,
            mandate_status=mandate_status,
            allotment_status="AWAITING",
            demat_account=demat_account,
            listing_strategy=listing_strategy,
            notes=notes,
        )
        messages.success(request, f"Application for {lots_applied} lot(s) of {ipo.company_name} logged successfully.")

        if request.headers.get("HX-Request"):
            response = HttpResponseRedirect(reverse("ipo:applications"))
            response["HX-Redirect"] = reverse("ipo:applications")
            return response
        return redirect("ipo:applications")


class IPOUpdateApplicationOutcomeView(LoginRequiredMixin, View):
    """
    Update allotment outcome (Allotted shares, status, mandate status).
    """
    def post(self, request, pk, *args, **kwargs):
        application = get_object_or_404(IPOApplication, pk=pk, user=request.user)
        allotment_status = request.POST.get("allotment_status", application.allotment_status)
        try:
            allotted_shares = int(request.POST.get("allotted_shares", 0) or 0)
        except (ValueError, TypeError):
            allotted_shares = 0
        mandate_status = request.POST.get("mandate_status", application.mandate_status)

        application.allotment_status = allotment_status
        application.allotted_shares = allotted_shares
        application.allotted_amount = Decimal(allotted_shares) * application.bid_price
        application.mandate_status = mandate_status

        notes = request.POST.get("notes")
        if notes is not None:
            application.notes = notes.strip()

        application.save()
        messages.success(request, f"Outcome updated for {application.ipo.symbol} application.")

        if request.headers.get("HX-Request"):
            response = HttpResponseRedirect(reverse("ipo:applications"))
            response["HX-Redirect"] = reverse("ipo:applications")
            return response
        return redirect("ipo:applications")


class IPOTransferToPortfolioView(LoginRequiredMixin, View):
    """
    1-Click sync from Allotted IPO to Portfolio Holdings.
    Creates immutable BUY HoldingTransaction and recalculates position via FIFOAccountingEngine.
    """
    def post(self, request, pk, *args, **kwargs):
        application = get_object_or_404(IPOApplication, pk=pk, user=request.user)

        if application.transferred_to_portfolio:
            messages.warning(request, f"Allotted shares for {application.ipo.symbol} have already been transferred to portfolio.")
            return redirect("ipo:applications")

        if application.allotted_shares <= 0 or application.allotment_status not in ["ALLOTTED", "PARTIALLY_ALLOTTED"]:
            messages.error(request, "Cannot transfer application with 0 allotted shares.")
            return redirect("ipo:applications")

        listing = application.ipo.listing
        if not listing:
            listing = ExchangeListing.objects.filter(symbol=application.ipo.symbol, is_tradeable=True).first()
            if listing and not application.ipo.listing:
                application.ipo.listing = listing
                application.ipo.save(update_fields=["listing"])

        if not listing:
            messages.error(
                request,
                f"Exchange listing for {application.ipo.symbol} not found. "
                "The stock may not have officially listed on NSE/BSE yet.",
            )
            return redirect("ipo:applications")

        portfolio, _ = Portfolio.objects.get_or_create(
            user=request.user,
            is_default=True,
            defaults={"name": "Main Portfolio"},
        )

        HoldingTransaction.objects.create(
            portfolio=portfolio,
            listing=listing,
            transaction_type=TransactionType.BUY,
            quantity=application.allotted_shares,
            price=application.bid_price,
            brokerage=Decimal("0.00"),
            statutory_taxes=Decimal("0.00"),
            executed_at=timezone.now(),
            notes=f"IPO Allotment sync for {application.ipo.symbol} (App #{application.application_number or application.id})",
        )

        FIFOAccountingEngine.reconcile_holding(portfolio=portfolio, listing=listing)

        application.transferred_to_portfolio = True
        application.save(update_fields=["transferred_to_portfolio"])

        messages.success(
            request,
            f"Successfully transferred {application.allotted_shares} shares of {application.ipo.symbol} "
            f"into your portfolio ({portfolio.name})!",
        )

        if request.headers.get("HX-Request"):
            response = HttpResponseRedirect(reverse("ipo:applications"))
            response["HX-Redirect"] = reverse("ipo:applications")
            return response
        return redirect("ipo:applications")


class IPOApplicationDeleteView(LoginRequiredMixin, View):
    """
    Delete an IPO application record.
    """
    def post(self, request, pk, *args, **kwargs):
        application = get_object_or_404(IPOApplication, pk=pk, user=request.user)
        symbol = application.ipo.symbol
        application.delete()
        messages.info(request, f"Application for {symbol} removed.")
        if request.headers.get("HX-Request"):
            response = HttpResponseRedirect(reverse("ipo:applications"))
            response["HX-Redirect"] = reverse("ipo:applications")
            return response
        return redirect("ipo:applications")


class IPOPerformanceView(HTMXResponseMixin, TemplateView):
    """
    Post-Listing Performance Desk:
    Exhaustive return analytics for listed IPOs including listing day gains,
    multi-horizon holding returns (1W, 1M, 3M, 6M, 1Y), maximum drawdowns, and benchmark alpha.
    """
    template_name = "ipo/performance.html"
    partial_template_name = "ipo/partials/performance_partial.html"
    active_nav = "ipo_performance"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        issue_type = self.request.GET.get("type", "ALL")
        sector = self.request.GET.get("sector", "ALL")
        sort_by = self.request.GET.get("sort", "-total_return")

        summary = get_listed_ipos_performance_summary(
            issue_type=issue_type,
            sector=sector,
            sort_by=sort_by,
        )
        context["page_title"] = "Post-Listing Performance & Returns Desk"
        context["active_nav"] = "ipo_performance"
        context["summary"] = summary
        context["current_type"] = issue_type
        context["current_sector"] = sector
        context["current_sort"] = sort_by

        context["sectors"] = (
            IPOMaster.objects.filter(Q(status=IPOStatus.LISTED) | Q(listing_date__isnull=False))
            .values_list("sector", flat=True)
            .distinct()
            .order_by("sector")
        )
        return context


class IPOComparisonView(HTMXResponseMixin, TemplateView):
    """
    Multi-IPO Side-by-Side Comparison Engine:
    Compares 2 to 4 IPOs across valuation multiples, 3-year growth,
    financial ratios, subscription demand, and 7-pillar composite research scores.
    """
    template_name = "ipo/compare.html"
    partial_template_name = "ipo/partials/compare_partial.html"
    active_nav = "ipo_compare"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        symbols_raw = self.request.GET.get("symbols", "")
        if symbols_raw:
            symbols = [s.strip().upper() for s in symbols_raw.split(",") if s.strip()]
        else:
            # Default to 3 prominent issues
            default_symbols = list(
                IPOMaster.objects.filter(status__in=[IPOStatus.LIVE, IPOStatus.UPCOMING, IPOStatus.LISTED])
                .values_list("symbol", flat=True)[:3]
            )
            symbols = default_symbols or ["SWIGGY", "HYUNDAI", "WAAREEENER"]

        comparison_data = compare_ipos(symbols)
        context["page_title"] = "Multi-IPO Comparison Matrix"
        context["active_nav"] = "ipo_compare"
        context["comparison"] = comparison_data
        context["selected_symbols"] = symbols
        context["selected_symbols_csv"] = ",".join(symbols)
        context["all_ipos"] = IPOMaster.objects.all().order_by("company_name")
        return context


class IPOSyncView(View):
    """
    Triggers live ingestion from ipos.markets and re-renders the dashboard partial.
    """
    def post(self, request, *args, **kwargs):
        from services.ipo.sync import sync_ipos_markets
        try:
            stats = sync_ipos_markets(live_only=False, detail_limit=30)
            messages.success(
                request,
                f"Live Primary Market Sync: {stats['created']} new issues added, {stats['updated']} updated from ipos.markets."
            )
        except Exception as e:
            messages.error(request, f"Live sync failed: {e}")

        if request.headers.get("HX-Request"):
            from django.shortcuts import render
            dashboard_view = IPODashboardView()
            dashboard_view.request = request
            context = dashboard_view.get_context_data()
            return render(request, "ipo/partials/dashboard_partial.html", context)
        return redirect("ipo:dashboard")



