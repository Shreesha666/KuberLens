"""
Management command to seed realistic Indian stock market news, regulatory filings,
and corporate event calendar data (dividends, splits, earnings releases, bonuses).
"""
import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.instruments.models import ExchangeListing
from apps.news.models import (
    CorporateEvent,
    CorporateEventType,
    EventStatus,
    NewsArticle,
    NewsCategory,
    SentimentType,
)

SAMPLE_NEWS_TEMPLATES = [
    {
        "category": NewsCategory.QUARTERLY_RESULTS,
        "sentiment": SentimentType.BULLISH,
        "headline_fmt": "{symbol} Q2 Net Profit Jumps {pct}% YoY, Beats Street Estimates",
        "summary_fmt": "{name} reported consolidated quarterly revenue expansion of {pct2}% driven by strong operational demand across key verticals. EBITDA margins expanded 140 bps.",
        "source": "NSE Corporate Filings",
    },
    {
        "category": NewsCategory.DIVIDEND,
        "sentiment": SentimentType.BULLISH,
        "headline_fmt": "{symbol} Board Declares Interim Dividend of ₹{div_val} Per Share",
        "summary_fmt": "The Board of Directors of {name} approved an interim dividend of ₹{div_val} per equity share. Record date has been set with payment to follow within statutory timelines.",
        "source": "BSE Corporate Announcements",
    },
    {
        "category": NewsCategory.COMPANY_NEWS,
        "sentiment": SentimentType.BULLISH,
        "headline_fmt": "{symbol} Secures Multi-Million Dollar Strategic Order in Core Division",
        "summary_fmt": "{name} announced the signing of a long-term enterprise deal, strengthening its multi-year order backlog and reinforcing revenue visibility for FY26.",
        "source": "Press Trust of India (PTI)",
    },
    {
        "category": NewsCategory.REGULATORY,
        "sentiment": SentimentType.NEUTRAL,
        "headline_fmt": "{symbol} Submits Compliance Certificate Under Regulation 74(5)",
        "summary_fmt": "{name} confirmed compliance with SEBI (Depositories and Participants) Regulations for the quarter ended September 2026.",
        "source": "NSE Filings",
    },
    {
        "category": NewsCategory.SECTOR_NEWS,
        "sentiment": SentimentType.BULLISH,
        "headline_fmt": "Strong Institutional Capital Inflows Boost Indian {sector} Equities",
        "summary_fmt": "Domestic Mutual Funds and foreign portfolio investors continued net accumulation across frontline {sector} leaders amid resilient macro GDP growth.",
        "source": "Financial Express",
    },
    {
        "category": NewsCategory.COMPANY_NEWS,
        "sentiment": SentimentType.BEARISH,
        "headline_fmt": "{symbol} Faces Near-Term Margin Headwinds from Input Cost Inflation",
        "summary_fmt": "Management commentary at {name} investor call highlighted transient commodity price pressures, though long-term volume guidance remains sustained.",
        "source": "LiveMint",
    },
    {
        "category": NewsCategory.BONUS_ISSUE,
        "sentiment": SentimentType.BULLISH,
        "headline_fmt": "{symbol} Board Approves 1:1 Bonus Issue to Reward Shareholders",
        "summary_fmt": "{name} announced a 1:1 bonus issue of equity shares capitalized from general reserves, subject to requisite shareholder approval.",
        "source": "NSE Corporate Filings",
    },
]


class Command(BaseCommand):
    help = "Seeds sample news articles and corporate events for active exchange listings."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Seeding news articles and corporate calendar events..."))

        listings = list(ExchangeListing.objects.filter(is_tradeable=True, is_primary=True).select_related("instrument"))
        if not listings:
            self.stdout.write(self.style.ERROR("No active listings found. Run seed_instruments / seed_nifty250 first."))
            return

        now = timezone.now()
        today = now.date()

        news_created = 0
        events_created = 0

        # 1. Seed News Articles
        for i, listing in enumerate(listings[:50]):
            inst = listing.instrument
            # Generate 2-3 news items per listing
            for j in range(random.randint(1, 3)):
                tmpl = random.choice(SAMPLE_NEWS_TEMPLATES)
                pct = random.randint(12, 38)
                pct2 = random.randint(8, 22)
                div_val = round(random.uniform(5.0, 45.0), 1)

                headline = tmpl["headline_fmt"].format(
                    symbol=listing.symbol, name=inst.display_name, pct=pct, div_val=div_val, sector=inst.sector
                )
                summary = tmpl["summary_fmt"].format(
                    symbol=listing.symbol, name=inst.display_name, pct=pct, pct2=pct2, div_val=div_val, sector=inst.sector
                )

                days_ago = (i * 2 + j) % 30
                pub_time = now - timedelta(days=days_ago, hours=random.randint(1, 12))

                NewsArticle.objects.create(
                    listing=listing,
                    headline=headline,
                    source=tmpl["source"],
                    published_at=pub_time,
                    summary=summary,
                    category=tmpl["category"],
                    sentiment=tmpl["sentiment"],
                    is_ai_summary=(j == 2),
                )
                news_created += 1

        # Seed Macro / Sector news without listing
        for sector in ["Information Technology", "Banking & Financials", "Automobile", "Pharmaceuticals", "Energy"]:
            NewsArticle.objects.create(
                listing=None,
                headline=f"Indian {sector} Sector Positioned for Capital Expenditure Acceleration",
                source="Economic Times Intelligence",
                published_at=now - timedelta(days=random.randint(1, 5)),
                summary=f"Industry report underscores strong balance sheets and capacity utilization across Indian {sector} manufacturers heading into FY27.",
                category=NewsCategory.SECTOR_NEWS,
                sentiment=SentimentType.BULLISH,
                is_ai_summary=True,
            )
            news_created += 1

        # 2. Seed Corporate Events
        event_types = [
            (CorporateEventType.EARNINGS, "Q3 FY26 Financial Results Declaration", None),
            (CorporateEventType.DIVIDEND, "Interim Dividend Ex-Date", "₹18.50 / share"),
            (CorporateEventType.AGM, "Annual General Meeting", None),
            (CorporateEventType.BONUS, "1:1 Bonus Issue Record Date", "1:1 Bonus"),
            (CorporateEventType.SPLIT, "Sub-division of Shares (1:5)", "1:5 Split"),
            (CorporateEventType.BOARD_MEETING, "Board Meeting to Consider Strategic Acquisition", None),
        ]

        for i, listing in enumerate(listings[:40]):
            ev_tuple = event_types[i % len(event_types)]
            ev_type, ev_title, ev_val = ev_tuple

            # Half upcoming, half completed
            days_offset = (i % 20) - 5
            ev_date = today + timedelta(days=days_offset)
            status = EventStatus.UPCOMING if ev_date >= today else EventStatus.COMPLETED

            CorporateEvent.objects.create(
                listing=listing,
                event_type=ev_type,
                event_date=ev_date,
                title=f"{listing.symbol} - {ev_title}",
                details=f"Formal corporate notification filed with the National Stock Exchange of India for {listing.instrument.display_name}.",
                ratio_or_value=ev_val or "",
                status=status,
            )
            events_created += 1

        self.stdout.write(self.style.SUCCESS(
            f"Successfully seeded {news_created} news articles and {events_created} corporate calendar events!"
        ))
