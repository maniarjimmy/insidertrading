"""
Unit Tests for Trading Holiday Calendar Module (holidays.py)
"""

from datetime import date, datetime
import os
import pytest

from holidays import (
    count_trading_days,
    get_next_trading_day,
    get_previous_trading_day,
    get_trading_days_between,
    is_trading_day,
    parse_date,
)


def test_parse_date():
    """Verify robust parsing of various date representations."""
    d = parse_date("2026-04-03")
    assert d == date(2026, 4, 3)

    d2 = parse_date("2026-04-03 14:30")
    assert d2 == date(2026, 4, 3)

    d3 = parse_date(datetime(2026, 4, 3, 10, 0))
    assert d3 == date(2026, 4, 3)

    d4 = parse_date(date(2026, 4, 3))
    assert d4 == date(2026, 4, 3)

    with pytest.raises(ValueError):
        parse_date("invalid-date-format")


def test_weekend_detection():
    """Saturdays and Sundays must not be trading days."""
    # 2026-04-04 is Saturday, 2026-04-05 is Sunday
    assert not is_trading_day(date(2026, 4, 4))
    assert not is_trading_day(date(2026, 4, 5))
    assert not is_trading_day("2026-04-04")
    assert not is_trading_day("2026-04-05")


def test_official_nse_holidays():
    """Official 2026 NSE holidays must be recognized as non-trading days."""
    # Republic Day: 2026-01-26 (Monday)
    assert not is_trading_day(date(2026, 1, 26))
    # Good Friday: 2026-04-03 (Friday)
    assert not is_trading_day(date(2026, 4, 3))
    # Maharashtra Day: 2026-05-01 (Friday)
    assert not is_trading_day(date(2026, 5, 1))
    # Gandhi Jayanti: 2026-10-02 (Friday)
    assert not is_trading_day(date(2026, 10, 2))


def test_normal_trading_days():
    """Regular weekdays that are not holidays must be recognized as trading days."""
    # 2026-01-27 (Tuesday following Republic Day)
    assert is_trading_day(date(2026, 1, 27))
    # 2026-04-06 (Monday following Good Friday and weekend)
    assert is_trading_day(date(2026, 4, 6))


def test_get_next_trading_day():
    """Verify stepping forward over weekends and holidays."""
    # Thursday 2026-04-02: Next day is Good Friday (holiday), then Sat/Sun, so next trading day is Monday 2026-04-06
    next_day = get_next_trading_day(date(2026, 4, 2), n=1)
    assert next_day == date(2026, 4, 6)

    # Advancing 2 trading days from 2026-04-02 should land on Tuesday 2026-04-07
    next_2 = get_next_trading_day(date(2026, 4, 2), n=2)
    assert next_2 == date(2026, 4, 7)


def test_get_previous_trading_day():
    """Verify stepping backward over weekends and holidays."""
    # Monday 2026-04-06: previous trading day skips weekend (04-05, 04-04) and Good Friday (04-03) -> 2026-04-02
    prev_day = get_previous_trading_day(date(2026, 4, 6), n=1)
    assert prev_day == date(2026, 4, 2)


def test_trading_days_between_and_count():
    """Verify counting and listing trading days in an interval."""
    # Between Thursday 2026-04-02 and Tuesday 2026-04-07:
    # 04-02 (Thu: trading)
    # 04-03 (Fri: Good Friday holiday)
    # 04-04 (Sat: weekend)
    # 04-05 (Sun: weekend)
    # 04-06 (Mon: trading)
    # 04-07 (Tue: trading)
    days = get_trading_days_between(date(2026, 4, 2), date(2026, 4, 7))
    assert days == [date(2026, 4, 2), date(2026, 4, 6), date(2026, 4, 7)]

    # count_trading_days excludes start date (elapsed days): 04-06 and 04-07 = 2
    count = count_trading_days(date(2026, 4, 2), date(2026, 4, 7))
    assert count == 2
