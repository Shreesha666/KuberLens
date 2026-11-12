"""
Unit tests for ExchangeCalendar service.
Tests trading day rules, gazetted holidays, Muhurat trading sessions, and market open/close checks.
"""
import zoneinfo
from datetime import date, datetime

import pytest

from services.calendar.exchange_calendar import ExchangeCalendar

IST = zoneinfo.ZoneInfo("Asia/Kolkata")


@pytest.mark.django_db
class TestExchangeCalendar:
    def test_regular_weekday_is_trading_day(self):
        # A normal Wednesday with no gazetted holiday (e.g. 2024-02-07)
        regular_wednesday = date(2024, 2, 7)
        assert ExchangeCalendar.is_trading_day(regular_wednesday) is True
        assert ExchangeCalendar.get_holiday_reason(regular_wednesday) is None

    def test_weekends_are_not_trading_days(self):
        # Saturday and Sunday
        saturday = date(2024, 2, 10)
        sunday = date(2024, 2, 11)
        assert ExchangeCalendar.is_trading_day(saturday) is False
        assert ExchangeCalendar.is_trading_day(sunday) is False

    def test_fixed_national_holidays(self):
        # Republic Day: Jan 26
        rep_day = date(2025, 1, 26)  # Sunday
        assert ExchangeCalendar.get_holiday_reason(rep_day) == "Republic Day"

        # Independence Day: Aug 15 (2024 was a Thursday)
        ind_day = date(2024, 8, 15)
        assert ExchangeCalendar.is_trading_day(ind_day) is False
        assert ExchangeCalendar.get_holiday_reason(ind_day) == "Independence Day"

        # Gandhi Jayanti: Oct 2 (2024 was a Wednesday)
        gandhi_day = date(2024, 10, 2)
        assert ExchangeCalendar.is_trading_day(gandhi_day) is False
        assert ExchangeCalendar.get_holiday_reason(gandhi_day) == "Mahatma Gandhi Jayanti"

    def test_variable_annual_holidays(self):
        # Holi 2024: March 25 (Monday)
        holi_2024 = date(2024, 3, 25)
        assert ExchangeCalendar.is_trading_day(holi_2024) is False
        assert "Holi" in ExchangeCalendar.get_holiday_reason(holi_2024)

        # Good Friday 2024: March 29 (Friday)
        good_friday = date(2024, 3, 29)
        assert ExchangeCalendar.is_trading_day(good_friday) is False
        assert "Good Friday" in ExchangeCalendar.get_holiday_reason(good_friday)

    def test_muhurat_trading_session(self):
        # Diwali 2024: Nov 1, 2024 (Muhurat session 18:00 to 19:00 IST)
        diwali_date = date(2024, 11, 1)
        assert ExchangeCalendar.is_trading_day(diwali_date) is True

        # During Muhurat trading hour (18:30 IST)
        dt_during = datetime(2024, 11, 1, 18, 30, tzinfo=IST)
        assert ExchangeCalendar.is_market_open(dt_during) is True

        # Outside Muhurat trading hour on same day (10:00 IST)
        dt_outside = datetime(2024, 11, 1, 10, 0, tzinfo=IST)
        assert ExchangeCalendar.is_market_open(dt_outside) is False

    def test_is_market_open_regular_trading_day(self):
        # Regular trading Wednesday (2024-02-07)
        # Pre-market: 08:30 IST -> closed
        pre_mkt = datetime(2024, 2, 7, 8, 30, tzinfo=IST)
        assert ExchangeCalendar.is_market_open(pre_mkt) is False

        # Market open: 09:15 IST -> open
        open_time = datetime(2024, 2, 7, 9, 15, tzinfo=IST)
        assert ExchangeCalendar.is_market_open(open_time) is True

        # Mid-day: 12:30 IST -> open
        mid_day = datetime(2024, 2, 7, 12, 30, tzinfo=IST)
        assert ExchangeCalendar.is_market_open(mid_day) is True

        # Closing exact: 15:30 IST -> open
        close_time = datetime(2024, 2, 7, 15, 30, tzinfo=IST)
        assert ExchangeCalendar.is_market_open(close_time) is True

        # Post-market: 16:00 IST -> closed
        post_mkt = datetime(2024, 2, 7, 16, 0, tzinfo=IST)
        assert ExchangeCalendar.is_market_open(post_mkt) is False

    def test_get_last_trading_day(self):
        # Sunday 2024-02-11 -> Last trading day was Friday 2024-02-09
        sunday = date(2024, 2, 11)
        assert ExchangeCalendar.get_last_trading_day(sunday) == date(2024, 2, 9)

        # On a trading day itself (2024-02-07), returns itself
        wednesday = date(2024, 2, 7)
        assert ExchangeCalendar.get_last_trading_day(wednesday) == wednesday

    def test_get_session_status(self):
        # Test status dictionary output
        dt = datetime(2024, 2, 7, 11, 0, tzinfo=IST)
        status = ExchangeCalendar.get_session_status(dt)
        assert status["is_open"] is True
        assert status["is_trading_day"] is True
        assert status["session_name"] == "Regular Trading Session"
        assert status["exchange"] == "NSE"
        assert "2024-02-07" in status["current_time_ist"]
