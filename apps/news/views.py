"""
News and Corporate Events Views.
Provides the market news feed and corporate action calendar.
"""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.management import call_command
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import redirect
from django.views import View
from django.views.generic import TemplateView

from apps.core.mixins import HTMXResponseMixin
from apps.news.models import (
    CorporateEvent,
    CorporateEventType,
    EventStatus,
    NewsArticle,
    NewsCategory,
    SentimentType,
)


class NewsFeedView(LoginRequiredMixin, HTMXResponseMixin, TemplateView):
    """
    Financial news, filings feed, and corporate announcements with sentiment indicators.
    """
    template_name = "news/feed.html"
    partial_template_name = "news/partials/feed_partial.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cat_filter = self.request.GET.get("category", "").strip().upper()
        sentiment_filter = self.request.GET.get("sentiment", "").strip().upper()
        symbol_filter = self.request.GET.get("symbol", "").strip().upper()
        query = self.request.GET.get("q", "").strip()

        qs = NewsArticle.objects.select_related("listing__instrument").all()

        if cat_filter and cat_filter in NewsCategory.values:
            qs = qs.filter(category=cat_filter)

        if sentiment_filter and sentiment_filter in SentimentType.values:
            qs = qs.filter(sentiment=sentiment_filter)

        if symbol_filter:
            qs = qs.filter(listing__symbol=symbol_filter)

        if query:
            qs = qs.filter(
                Q(headline__icontains=query) |
                Q(summary__icontains=query) |
                Q(listing__symbol__icontains=query) |
                Q(source__icontains=query)
            )

        # Pagination: 15 news items per page
        page_number = self.request.GET.get("page", 1)
        paginator = Paginator(qs, 15)
        page_obj = paginator.get_page(page_number)

        context["active_nav"] = "market_news"
        context["page_obj"] = page_obj
        context["articles"] = page_obj.object_list
        context["total_count"] = paginator.count
        context["selected_category"] = cat_filter
        context["selected_sentiment"] = sentiment_filter
        context["selected_symbol"] = symbol_filter
        context["search_query"] = query
        context["categories"] = NewsCategory.choices
        context["sentiments"] = SentimentType.choices
        return context


class CorporateEventsCalendarView(LoginRequiredMixin, HTMXResponseMixin, TemplateView):
    """
    Corporate action calendar tracking earnings releases, dividends, splits, and bonus issues.
    """
    template_name = "news/calendar.html"
    partial_template_name = "news/partials/calendar_partial.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        event_type = self.request.GET.get("type", "").strip().upper()
        status_filter = self.request.GET.get("status", "UPCOMING").strip().upper()

        qs = CorporateEvent.objects.select_related("listing__instrument").all()

        if event_type and event_type in CorporateEventType.values:
            qs = qs.filter(event_type=event_type)

        if status_filter and status_filter in EventStatus.values:
            qs = qs.filter(status=status_filter)

        context["active_nav"] = "corporate_events"
        context["events"] = qs[:50]
        context["selected_type"] = event_type
        context["selected_status"] = status_filter
        context["event_types"] = CorporateEventType.choices
        context["statuses"] = EventStatus.choices
        return context


class RefreshNewsFeedView(LoginRequiredMixin, View):
    """
    Refreshes the market news feed and corporate actions up to the current date and time.
    """
    def post(self, request, *args, **kwargs):
        try:
            call_command("seed_news_and_events", clear=True)
            messages.success(request, "Market news and corporate events refreshed with latest announcements.")
        except Exception as e:
            messages.error(request, f"Could not refresh news: {e}")

        if request.htmx:
            feed_view = NewsFeedView.as_view()
            return feed_view(request)
        return redirect("news:feed")

