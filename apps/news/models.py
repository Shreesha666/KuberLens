"""
News and Corporate Events Data Models.
Complies with Master Specification Section 19.
Stores verified corporate filings, earnings announcements, dividends, bonus/split events,
and sector news, distinguishing published facts from AI summaries.
"""
from django.db import models

from apps.core.models import AuditedModel
from apps.instruments.models import ExchangeListing


class NewsCategory(models.TextChoices):
    COMPANY_NEWS = "COMPANY_NEWS", "Company News"
    QUARTERLY_RESULTS = "QUARTERLY_RESULTS", "Quarterly Results"
    DIVIDEND = "DIVIDEND", "Dividend Announcement"
    BONUS_ISSUE = "BONUS_ISSUE", "Bonus Issue"
    STOCK_SPLIT = "STOCK_SPLIT", "Stock Split"
    BUYBACK = "BUYBACK", "Share Buyback"
    BOARD_MEETING = "BOARD_MEETING", "Board Meeting"
    REGULATORY = "REGULATORY", "Regulatory & Filings"
    SECTOR_NEWS = "SECTOR_NEWS", "Sector & Macro News"


class SentimentType(models.TextChoices):
    BULLISH = "BULLISH", "Bullish"
    BEARISH = "BEARISH", "Bearish"
    NEUTRAL = "NEUTRAL", "Neutral"


class CorporateEventType(models.TextChoices):
    EARNINGS = "EARNINGS", "Earnings Release"
    DIVIDEND = "DIVIDEND", "Dividend Ex-Date"
    BONUS = "BONUS", "Bonus Issue"
    SPLIT = "SPLIT", "Stock Split"
    AGM = "AGM", "Annual General Meeting (AGM)"
    BOARD_MEETING = "BOARD_MEETING", "Board Meeting"


class EventStatus(models.TextChoices):
    UPCOMING = "UPCOMING", "Upcoming"
    COMPLETED = "COMPLETED", "Completed"


class NewsArticle(AuditedModel):
    """
    Market and company announcements, regulatory filings, and financial news items.
    """
    listing = models.ForeignKey(
        ExchangeListing,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="news_articles",
        help_text="Associated stock listing, or null for general macro/sector news.",
    )
    headline = models.CharField(max_length=300)
    source = models.CharField(max_length=100, help_text="e.g. NSE Filings, BSE Corporate, Financial Express, Reuters")
    url = models.URLField(blank=True, max_length=500)
    published_at = models.DateTimeField(db_index=True)
    summary = models.TextField()
    category = models.CharField(
        max_length=50,
        choices=NewsCategory.choices,
        default=NewsCategory.COMPANY_NEWS,
        db_index=True,
    )
    sentiment = models.CharField(
        max_length=20,
        choices=SentimentType.choices,
        default=SentimentType.NEUTRAL,
        db_index=True,
    )
    is_ai_summary = models.BooleanField(
        default=False,
        help_text="True if the summary was synthesized by an AI model rather than the raw filing text.",
    )

    class Meta:
        ordering = ["-published_at"]
        verbose_name = "News Article"
        verbose_name_plural = "News Articles"
        indexes = [
            models.Index(fields=["listing", "-published_at"], name="idx_news_listing_pub"),
            models.Index(fields=["category", "-published_at"], name="idx_news_cat_pub"),
        ]

    def __str__(self) -> str:
        sym = f"[{self.listing.symbol}] " if self.listing else "[MACRO] "
        return f"{sym}{self.headline[:60]}"


class CorporateEvent(AuditedModel):
    """
    Calendar of corporate events: earnings release dates, dividend ex-dates, splits, and AGMs.
    """
    listing = models.ForeignKey(
        ExchangeListing,
        on_delete=models.CASCADE,
        related_name="corporate_events",
        db_index=True,
    )
    event_type = models.CharField(
        max_length=50,
        choices=CorporateEventType.choices,
        db_index=True,
    )
    event_date = models.DateField(db_index=True)
    title = models.CharField(max_length=250)
    details = models.TextField(blank=True)
    ratio_or_value = models.CharField(
        max_length=50,
        blank=True,
        help_text="e.g. '₹28.00 / share', '1:1 bonus', '1:5 split'",
    )
    status = models.CharField(
        max_length=20,
        choices=EventStatus.choices,
        default=EventStatus.UPCOMING,
        db_index=True,
    )

    class Meta:
        ordering = ["event_date", "listing__symbol"]
        verbose_name = "Corporate Event"
        verbose_name_plural = "Corporate Events"
        indexes = [
            models.Index(fields=["event_date", "status"], name="idx_event_date_status"),
        ]

    def __str__(self) -> str:
        return f"{self.listing.symbol} - {self.get_event_type_display()} on {self.event_date}"

