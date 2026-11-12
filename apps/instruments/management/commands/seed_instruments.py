from django.core.management.base import BaseCommand
from django.db import transaction

from apps.instruments.models import Exchange, ExchangeListing, Instrument

BENCHMARK_INSTRUMENTS = [
    {
        "isin": "INE002A01018",
        "legal_name": "Reliance Industries Limited",
        "display_name": "Reliance Industries",
        "sector": "Energy",
        "industry": "Oil & Gas Refining & Marketing",
        "market_cap": "LARGE",
        "nse_symbol": "RELIANCE",
        "bse_symbol": "500325",
    },
    {
        "isin": "INE467B01029",
        "legal_name": "Tata Consultancy Services Limited",
        "display_name": "TCS",
        "sector": "Information Technology",
        "industry": "IT Services & Consulting",
        "market_cap": "LARGE",
        "nse_symbol": "TCS",
        "bse_symbol": "532540",
    },
    {
        "isin": "INE009A01021",
        "legal_name": "Infosys Limited",
        "display_name": "Infosys",
        "sector": "Information Technology",
        "industry": "IT Services & Consulting",
        "market_cap": "LARGE",
        "nse_symbol": "INFY",
        "bse_symbol": "500209",
    },
    {
        "isin": "INE040A01034",
        "legal_name": "HDFC Bank Limited",
        "display_name": "HDFC Bank",
        "sector": "Financial Services",
        "industry": "Private Sector Bank",
        "market_cap": "LARGE",
        "nse_symbol": "HDFCBANK",
        "bse_symbol": "500180",
    },
    {
        "isin": "INE062A01020",
        "legal_name": "State Bank of India",
        "display_name": "SBI",
        "sector": "Financial Services",
        "industry": "Public Sector Bank",
        "market_cap": "LARGE",
        "nse_symbol": "SBIN",
        "bse_symbol": "500112",
    },
    {
        "isin": "INE090A01021",
        "legal_name": "ICICI Bank Limited",
        "display_name": "ICICI Bank",
        "sector": "Financial Services",
        "industry": "Private Sector Bank",
        "market_cap": "LARGE",
        "nse_symbol": "ICICIBANK",
        "bse_symbol": "532174",
    },
    {
        "isin": "INE154A01025",
        "legal_name": "ITC Limited",
        "display_name": "ITC",
        "sector": "Consumer Goods",
        "industry": "Diversified FMCG",
        "market_cap": "LARGE",
        "nse_symbol": "ITC",
        "bse_symbol": "500875",
    },
    {
        "isin": "INE018A01030",
        "legal_name": "Larsen & Toubro Limited",
        "display_name": "L&T",
        "sector": "Construction",
        "industry": "Engineering & Construction",
        "market_cap": "LARGE",
        "nse_symbol": "LT",
        "bse_symbol": "500510",
    },
    {
        "isin": "INE397D01024",
        "legal_name": "Bharti Airtel Limited",
        "display_name": "Bharti Airtel",
        "sector": "Telecommunication",
        "industry": "Telecom Services",
        "market_cap": "LARGE",
        "nse_symbol": "BHARTIARTL",
        "bse_symbol": "532454",
    },
    {
        "isin": "INE155A01022",
        "legal_name": "Tata Motors Limited",
        "display_name": "Tata Motors",
        "sector": "Automobile",
        "industry": "Commercial & Passenger Vehicles",
        "market_cap": "LARGE",
        "nse_symbol": "TATAMOTORS",
        "bse_symbol": "500570",
    },
]

class Command(BaseCommand):
    help = "Seeds initial financial exchange venues and benchmark Indian equities."

    def handle(self, *args, **options):
        with transaction.atomic():
            # 1. Exchanges
            nse, _ = Exchange.objects.get_or_create(
                code="NSE",
                defaults={"name": "National Stock Exchange of India", "country": "India", "currency": "INR"},
            )
            bse, _ = Exchange.objects.get_or_create(
                code="BSE",
                defaults={"name": "Bombay Stock Exchange", "country": "India", "currency": "INR"},
            )
            self.stdout.write(self.style.SUCCESS("Exchanges verified: NSE, BSE"))

            # 2. Instruments & Listings
            created_count = 0
            for item in BENCHMARK_INSTRUMENTS:
                inst, created = Instrument.objects.get_or_create(
                    isin=item["isin"],
                    defaults={
                        "legal_name": item["legal_name"],
                        "display_name": item["display_name"],
                        "sector": item["sector"],
                        "industry": item["industry"],
                        "market_cap_category": item["market_cap"],
                    },
                )
                if created:
                    created_count += 1

                # NSE Listing
                ExchangeListing.objects.get_or_create(
                    instrument=inst,
                    exchange=nse,
                    symbol=item["nse_symbol"],
                    defaults={
                        "trading_symbol": f"{item['nse_symbol']}-EQ",
                        "series_or_group": "EQ",
                        "is_primary": True,
                    },
                )

                # BSE Listing
                ExchangeListing.objects.get_or_create(
                    instrument=inst,
                    exchange=bse,
                    symbol=item["bse_symbol"],
                    defaults={
                        "trading_symbol": f"{item['nse_symbol']}",
                        "series_or_group": "A",
                        "is_primary": False,
                    },
                )

            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully processed {len(BENCHMARK_INSTRUMENTS)} benchmark instruments. "
                    f"({created_count} newly created)"
                )
            )
