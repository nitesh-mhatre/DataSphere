"""Tests for NSE market time/status logic."""

from datetime import date, datetime

from dataspear.nse.market_time import (
    IST,
    get_market_status,
    is_market_open,
    is_trading_day,
    next_trading_day,
)

# 2026-05-01 is a Friday NSE holiday; 2026-05-04 is the following Monday.
MON_OPEN = datetime(2026, 5, 4, 10, 0, tzinfo=IST)


class TestTradingDay:
    def test_weekday_is_trading(self):
        assert is_trading_day(date(2026, 5, 4)) is True

    def test_weekend_is_not(self):
        assert is_trading_day(date(2026, 5, 2)) is False  # Saturday

    def test_holiday_is_not(self):
        assert is_trading_day(date(2026, 10, 2)) is False  # Gandhi Jayanti

    def test_next_trading_day_skips_weekend(self):
        assert next_trading_day(date(2026, 5, 2)) == date(2026, 5, 4)

    def test_next_trading_day_skips_holiday(self):
        assert next_trading_day(date(2026, 10, 2)) == date(2026, 10, 5)


class TestStatus:
    def test_normal_session_open(self):
        status = get_market_status(MON_OPEN)
        assert status.is_open is True
        assert status.phase == "NORMAL"
        assert status.minutes_to_close > 0
        assert status.trade_rules

    def test_before_open(self):
        status = get_market_status(datetime(2026, 5, 4, 8, 0, tzinfo=IST))
        assert status.is_open is False
        assert status.phase == "CLOSED"
        assert status.close_reason == "NIGHT"
        assert status.minutes_to_open > 0

    def test_pre_open(self):
        status = get_market_status(datetime(2026, 5, 4, 9, 5, tzinfo=IST))
        assert status.is_open is False
        assert status.phase == "PRE_OPEN"

    def test_closing_session(self):
        status = get_market_status(datetime(2026, 5, 4, 15, 45, tzinfo=IST))
        assert status.is_open is False
        assert status.phase == "CLOSING"

    def test_weekend_closed(self):
        status = get_market_status(datetime(2026, 5, 2, 11, 0, tzinfo=IST))
        assert status.is_open is False
        assert status.close_reason == "WEEKEND"

    def test_holiday_closed(self):
        status = get_market_status(datetime(2026, 10, 2, 11, 0, tzinfo=IST))
        assert status.is_open is False
        assert status.close_reason == "HOLIDAY"
        assert status.holiday_name == "Mahatma Gandhi Jayanti"

    def test_is_market_open_helper(self):
        assert is_market_open(MON_OPEN) is True

    def test_context_block_and_dict(self):
        status = get_market_status(MON_OPEN)
        assert "MARKET TIME CONTEXT" in status.context_block()
        assert status.to_dict()["is_open"] is True
