"""
Indian Stock Exchange (NSE / BSE) Trading Calendar Service.
Handles trading days, weekends, gazetted exchange holidays, and session hours.
"""
import zoneinfo
from datetime import date, datetime, time, timedelta

IST = zoneinfo.ZoneInfo("Asia/Kolkata")

class ExchangeCalendar:
    # Standard market hours (IST)
    MARKET_OPEN_TIME = time(9, 15)
    MARKET_CLOSE_TIME = time(15, 30)

    # National & Fixed NSE/BSE Exchange Holidays (Month, Day)
    FIXED_HOLIDAYS = {
        (1, 26): "Republic Day",
        (5, 1): "Maharashtra Day",
        (8, 15): "Independence Day",
        (10, 2): "Mahatma Gandhi Jayanti",
        (12, 25): "Christmas",
    }

    # Annual variable calendar holidays (Sample active years 2024-2027)
    VARIABLE_HOLIDAYS = {
        # 2024
        date(2024, 1, 22): "Special Holiday",
        date(2024, 3, 8): "Mahashivratri",
        date(2024, 3, 25): "Holi",
        date(2024, 3, 29): "Good Friday",
        date(2024, 4, 11): "Id-Ul-Fitr",
        date(2024, 4, 17): "Ram Navami",
        date(2024, 5, 20): "General Elections",
        date(2024, 6, 17): "Bakri Id",
        date(2024, 7, 17): "Muharram",
        date(2024, 11, 1): "Diwali Laxmi Pujan (Muhurat session only)",
        date(2024, 11, 15): "Guru Nanak Jayanti",
        date(2024, 11, 20): "Maharashtra Assembly Elections",
        # 2025
        date(2025, 2, 26): "Mahashivratri",
        date(2025, 3, 14): "Holi",
        date(2025, 3, 31): "Id-Ul-Fitr",
        date(2025, 4, 14): "Dr. Ambedkar Jayanti",
        date(2025, 4, 18): "Good Friday",
        date(2025, 6, 7): "Bakri Id",
        date(2025, 8, 27): "Ganesh Chaturthi",
        date(2025, 10, 21): "Diwali Laxmi Pujan",
        date(2025, 11, 5): "Guru Nanak Jayanti",
        # 2026
        date(2026, 3, 4): "Holi",
        date(2026, 3, 20): "Id-Ul-Fitr",
        date(2026, 4, 3): "Good Friday",
        date(2026, 4, 14): "Dr. Ambedkar Jayanti",
        date(2026, 5, 28): "Bakri Id",
        date(2026, 6, 26): "Muharram",
        date(2026, 9, 14): "Ganesh Chaturthi",
        date(2026, 10, 20): "Dussehra",
        date(2026, 11, 8): "Diwali Laxmi Pujan (Muhurat session)",
        date(2026, 11, 24): "Guru Nanak Jayanti",
    }

    # Special Evening Muhurat Trading Dates & Hours (Date -> (start_time, end_time))
    MUHURAT_SESSIONS = {
        date(2024, 11, 1): (time(18, 0), time(19, 0)),
        date(2025, 10, 21): (time(18, 15), time(19, 15)),
        date(2026, 11, 8): (time(18, 15), time(19, 15)),
    }

    @classmethod
    def get_trading_days(cls, start_date: date, end_date: date) -> list[date]:
        """
        Returns an ordered list of all active exchange trading days
        between start_date and end_date (inclusive).
        """
        days = []
        current = start_date
        while current <= end_date:
            if cls.is_trading_day(current):
                days.append(current)
            current += timedelta(days=1)
        return days

    @classmethod
    def get_holiday_reason(cls, date_obj: date) -> str | None:
        """Returns holiday name if date is a scheduled exchange holiday, else None."""
        if date_obj in cls.VARIABLE_HOLIDAYS:
            return cls.VARIABLE_HOLIDAYS[date_obj]
        fixed_key = (date_obj.month, date_obj.day)
        if fixed_key in cls.FIXED_HOLIDAYS:
            return cls.FIXED_HOLIDAYS[fixed_key]
        return None

    @classmethod
    def is_trading_day(cls, date_obj: date) -> bool:
        """
        Determines if the given date is an active trading day on NSE/BSE.
        Saturdays and Sundays are non-trading days unless a special session is scheduled.
        """
        # Check Muhurat session override
        if date_obj in cls.MUHURAT_SESSIONS:
            return True

        # Weekend check: Monday=0, Sunday=6
        if date_obj.weekday() in (5, 6):
            return False

        # Holiday check
        if cls.get_holiday_reason(date_obj) is not None:
            return False

        return True

    @classmethod
    def get_last_trading_day(cls, from_date: date | None = None) -> date:
        """
        Returns the most recent confirmed trading day on or before from_date.
        """
        if from_date is None:
            from_date = datetime.now(IST).date()

        current = from_date
        while not cls.is_trading_day(current):
            current -= timedelta(days=1)
        return current

    @classmethod
    def is_market_open(cls, dt: datetime | None = None) -> bool:
        """
        Determines whether the exchange is currently in an active trading session.
        """
        if dt is None:
            dt = datetime.now(IST)
        elif dt.tzinfo is None:
            dt = dt.replace(tzinfo=IST)
        else:
            dt = dt.astimezone(IST)

        curr_date = dt.date()
        curr_time = dt.time()

        # Check special Muhurat session
        if curr_date in cls.MUHURAT_SESSIONS:
            start, end = cls.MUHURAT_SESSIONS[curr_date]
            return start <= curr_time <= end

        # Regular trading day check
        if not cls.is_trading_day(curr_date):
            return False

        return cls.MARKET_OPEN_TIME <= curr_time <= cls.MARKET_CLOSE_TIME

    @classmethod
    def get_session_status(cls, dt: datetime | None = None) -> dict:
        """
        Returns comprehensive session status dictionary for UI and health indicators.
        """
        if dt is None:
            dt = datetime.now(IST)
        elif dt.tzinfo is None:
            dt = dt.replace(tzinfo=IST)
        else:
            dt = dt.astimezone(IST)

        curr_date = dt.date()
        curr_time = dt.time()
        is_trading = cls.is_trading_day(curr_date)
        is_open = cls.is_market_open(dt)

        if not is_trading:
            holiday = cls.get_holiday_reason(curr_date)
            name = f"Holiday: {holiday}" if holiday else "Weekend (Closed)"
        elif is_open:
            name = "Regular Trading Session"
        elif curr_time < cls.MARKET_OPEN_TIME:
            name = "Pre-Market"
        else:
            name = "Post-Market / EOD"

        return {
            "is_open": is_open,
            "is_trading_day": is_trading,
            "session_name": name,
            "exchange": "NSE",
            "current_time_ist": dt.strftime("%Y-%m-%d %H:%M:%S IST"),
            "last_trading_day": cls.get_last_trading_day(curr_date).isoformat(),
        }
