"""
Unit Tests for Corporate Actions Module (corporate_actions.py)
Phase 5 Tests:
1. Parse action purpose strings (splits, bonuses, rights, dividends).
2. Detect whether a target date is within +/- N trading days of an ex-date.
3. Compute cumulative price adjustment factors backwards across splits/bonuses.
"""

from datetime import date
import pytest

from corporate_actions import (
    adjust_price_for_corporate_actions,
    is_near_corporate_action,
    parse_action_purpose,
)


def test_parse_action_purpose():
    # Bonus issues
    act_type, ratio = parse_action_purpose("Bonus issue in the ratio of 1:1")
    assert act_type == "BONUS"
    assert ratio == 2.0  # (1 + 1) / 1

    act_type, ratio = parse_action_purpose("Bonus 2:1")
    assert act_type == "BONUS"
    assert ratio == 3.0  # (1 + 2) / 1

    act_type, ratio = parse_action_purpose("Bonus 1:2")
    assert act_type == "BONUS"
    assert ratio == 1.5  # (2 + 1) / 2

    # Stock splits
    act_type, ratio = parse_action_purpose("Sub-division of shares from Rs. 10/- to Rs. 2/-")
    assert act_type == "SPLIT"
    assert ratio == 5.0  # 10 / 2

    act_type, ratio = parse_action_purpose("Stock Split from 10 to 1")
    assert act_type == "SPLIT"
    assert ratio == 10.0  # 10 / 1

    # Rights & Dividends
    act_type, ratio = parse_action_purpose("Rights Issue 1:4")
    assert act_type == "RIGHTS"

    act_type, ratio = parse_action_purpose("Interim Dividend Rs 5 Per Share")
    assert act_type == "DIVIDEND"


def test_is_near_corporate_action():
    mock_actions = [
        {
            "symbol": "SPLITCO",
            "ex_date": "2026-03-24",  # Tuesday
            "action_type": "SPLIT",
            "ratio": 2.0,
            "purpose": "Sub-division from 10 to 5",
        },
        {
            "symbol": "BONUSCO",
            "ex_date": "2026-03-27",  # Friday
            "action_type": "BONUS",
            "ratio": 2.0,
            "purpose": "Bonus 1:1",
        },
    ]

    # Exactly on ex-date
    is_near, details = is_near_corporate_action("SPLITCO", "2026-03-24", window_days=2, actions=mock_actions)
    assert is_near is True
    assert details["action_type"] == "SPLIT"

    # 1 trading day before (23-Mar-2026)
    is_near, _ = is_near_corporate_action("SPLITCO", "2026-03-23", window_days=2, actions=mock_actions)
    assert is_near is True

    # 2 trading days after (26-Mar-2026)
    is_near, _ = is_near_corporate_action("SPLITCO", "2026-03-26", window_days=2, actions=mock_actions)
    assert is_near is True

    # 5 trading days away (16-Mar-2026)
    is_near, _ = is_near_corporate_action("SPLITCO", "2026-03-16", window_days=2, actions=mock_actions)
    assert is_near is False

    # Unrelated symbol
    is_near, _ = is_near_corporate_action("OTHERCO", "2026-03-24", window_days=2, actions=mock_actions)
    assert is_near is False


def test_adjust_price_for_corporate_actions():
    # Stock undergoes 1:1 bonus on 2026-03-25 (ratio 2.0)
    mock_actions = [{
        "symbol": "TESTCO",
        "ex_date": "2026-03-25",
        "action_type": "BONUS",
        "ratio": 2.0,
    }]

    unadjusted_candles = [
        {"date": "2026-03-23", "open": 200.0, "high": 210.0, "low": 195.0, "close": 205.0, "volume": 1000},
        {"date": "2026-03-24", "open": 205.0, "high": 215.0, "low": 200.0, "close": 210.0, "volume": 1200},
        {"date": "2026-03-25", "open": 105.0, "high": 110.0, "low": 100.0, "close": 108.0, "volume": 2500},
    ]

    adjusted = adjust_price_for_corporate_actions(unadjusted_candles, mock_actions)
    assert len(adjusted) == 3

    # On or before ex-date (23rd and 24th), prices should be divided by 2.0 and volume multiplied by 2.0
    c0 = adjusted[0]
    assert c0["date"] == "2026-03-23"
    assert c0["close"] == 102.5  # 205 / 2.0
    assert c0["volume"] == 2000  # 1000 * 2.0

    c1 = adjusted[1]
    assert c1["date"] == "2026-03-24"
    assert c1["close"] == 105.0  # 210 / 2.0

    # Post ex-date candle unchanged
    c2 = adjusted[2]
    assert c2["date"] == "2026-03-25"
    assert c2["close"] == 108.0  # Already at ex-bonus price
    assert c2["volume"] == 2500
