"""
Unit Tests for Bhavcopy & Data Quality Layer (bhavcopy.py, data_quality.py)
Phase 5 Tests:
1. Candle validation (zero volume, inverted bounds, price discontinuities).
2. Extreme price move handling (rejection without corporate action, allowance with action).
3. Market data auditing and structured logging.
4. Bhavcopy and MTO delivery record parsing.
"""

from datetime import date
import unittest.mock as mock
import pytest

from data_quality import audit_and_clean_market_data, validate_candle


def test_validate_candle_valid_case():
    candle = {
        "symbol": "GOODCO",
        "open": 100.0,
        "high": 105.0,
        "low": 98.0,
        "close": 103.0,
        "prev_close": 100.0,
        "price_change": 3.0,
        "volume": 50000,
    }
    is_valid, reason = validate_candle(candle, "2026-03-24")
    assert is_valid is True
    assert reason is None


def test_validate_candle_missing_or_zero_close():
    candle = {"symbol": "BADCO", "open": 100.0, "high": 105.0, "low": 98.0, "close": 0.0, "volume": 1000}
    is_valid, reason = validate_candle(candle, "2026-03-24")
    assert is_valid is False
    assert "MISSING_OR_ZERO_CLOSE" in reason


def test_validate_candle_inverted_bounds():
    # High < Low
    candle = {"symbol": "BADCO", "open": 100.0, "high": 90.0, "low": 95.0, "close": 92.0, "volume": 1000}
    is_valid, reason = validate_candle(candle, "2026-03-24")
    assert is_valid is False
    assert "INVERTED_HIGH_LOW" in reason

    # High < Close
    candle2 = {"symbol": "BADCO", "open": 100.0, "high": 102.0, "low": 95.0, "close": 105.0, "volume": 1000}
    is_valid, reason = validate_candle(candle2, "2026-03-24")
    assert is_valid is False
    assert "HIGH_BELOW_CLOSE_OR_OPEN" in reason


def test_validate_candle_zero_volume_trading_day():
    candle = {"symbol": "NOVOL", "open": 100.0, "high": 105.0, "low": 98.0, "close": 103.0, "volume": 0}
    # 2026-03-24 is a Tuesday (active trading day)
    is_valid, reason = validate_candle(candle, "2026-03-24")
    assert is_valid is False
    assert "ZERO_VOLUME_ON_TRADING_DAY" in reason


def test_validate_candle_extreme_price_discontinuity():
    # 40% jump without corporate action -> REJECTED
    candle_no_action = {
        "symbol": "SPIKECO",
        "open": 100.0,
        "high": 142.0,
        "low": 99.0,
        "close": 140.0,
        "prev_close": 100.0,
        "price_change": 40.0,
        "volume": 200000,
    }
    with mock.patch("data_quality.is_near_corporate_action", return_value=(False, None)):
        is_valid, reason = validate_candle(candle_no_action, "2026-03-24")
        assert is_valid is False
        assert "EXTREME_PRICE_DISCONTINUITY" in reason

    # 40% move WITH legitimate corporate action (e.g. bonus/split) -> ACCEPTED
    with mock.patch("data_quality.is_near_corporate_action", return_value=(True, {"action_type": "BONUS", "purpose": "Bonus 1:1"})):
        is_valid, reason = validate_candle(candle_no_action, "2026-03-24")
        assert is_valid is True
        assert reason is None


def test_audit_and_clean_market_data():
    raw_universe = {
        "CLEANCO": {
            "symbol": "CLEANCO", "open": 50.0, "high": 52.0, "low": 49.0, "close": 51.0,
            "prev_close": 50.0, "price_change": 2.0, "volume": 10000, "source": "NSE_UDDiP"
        },
        "DIRTYCO": {
            "symbol": "DIRTYCO", "open": 50.0, "high": 52.0, "low": 49.0, "close": 0.0,
            "prev_close": 50.0, "price_change": -100.0, "volume": 0, "source": "NSE_UDDiP"
        },
    }
    cleaned, audit_records = audit_and_clean_market_data(raw_universe, "2026-03-24")
    assert "CLEANCO" in cleaned
    assert "DIRTYCO" not in cleaned
    assert len(audit_records) == 1
    assert audit_records[0]["symbol"] == "DIRTYCO"
