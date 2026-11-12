from django.contrib import admin

from apps.news.models import CorporateEvent, NewsArticle


@admin.register(NewsArticle)
class NewsArticleAdmin(admin.ModelAdmin):
    list_display = ("headline", "listing", "source", "category", "sentiment", "published_at")
    list_filter = ("category", "sentiment", "source")
    search_fields = ("headline", "summary", "listing__symbol")


@admin.register(CorporateEvent)
class CorporateEventAdmin(admin.ModelAdmin):
    list_display = ("listing", "event_type", "event_date", "title", "ratio_or_value", "status")
    list_filter = ("event_type", "status")
    search_fields = ("title", "details", "listing__symbol")
