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


def test_real_corporate_actions_uddip():
    """
    Test corporate action adjustment on real historical data from official NSE UDDiP Bhavcopy.
    Asserts:
    1. Adjusted economic returns across ex-date are plausible (|r| < 25%).
    2. Adjuster refuses / no-ops on already-adjusted data (preventing double-adjustment).
    """
    real_cases = [
        {
            "symbol": "COCHINSHIP",
            "action": {"symbol": "COCHINSHIP", "action_type": "SPLIT", "ratio": 2.0, "ex_date": "2024-01-10"},
            "raw_candles": [
                {"date": "2024-01-08", "close": 1293.65, "volume": 2299797},
                {"date": "2024-01-09", "close": 1338.00, "volume": 3355705},
                {"date": "2024-01-10", "close": 802.80, "volume": 22442717},
                {"date": "2024-01-11", "close": 772.80, "volume": 11469695},
            ]
        },
        {
            "symbol": "CANBK",
            "action": {"symbol": "CANBK", "action_type": "SPLIT", "ratio": 5.0, "ex_date": "2024-05-15"},
            "raw_candles": [
                {"date": "2024-05-13", "close": 549.35, "volume": 10498821},
                {"date": "2024-05-14", "close": 566.55, "volume": 9219466},
                {"date": "2024-05-15", "close": 119.00, "volume": 58148316},
                {"date": "2024-05-16", "close": 113.70, "volume": 83518740},
            ]
        },
        {
            "symbol": "BPCL",
            "action": {"symbol": "BPCL", "action_type": "BONUS", "ratio": 2.0, "ex_date": "2024-06-21"},
            "raw_candles": [
                {"date": "2024-06-19", "close": 615.80, "volume": 9824003},
                {"date": "2024-06-20", "close": 626.25, "volume": 9038323},
                {"date": "2024-06-21", "close": 307.60, "volume": 30004484},
                {"date": "2024-06-24", "close": 305.25, "volume": 7557297},
            ]
        },
        {
            "symbol": "HINDPETRO",
            "action": {"symbol": "HINDPETRO", "action_type": "BONUS", "ratio": 1.5, "ex_date": "2024-06-21"},
            "raw_candles": [
                {"date": "2024-06-19", "close": 515.50, "volume": 6529379},
                {"date": "2024-06-20", "close": 523.80, "volume": 4582098},
                {"date": "2024-06-21", "close": 340.85, "volume": 13108523},
                {"date": "2024-06-24", "close": 337.95, "volume": 8084076},
            ]
        },
        {
            "symbol": "OIL",
            "action": {"symbol": "OIL", "action_type": "BONUS", "ratio": 1.5, "ex_date": "2024-07-02"},
            "raw_candles": [
                {"date": "2024-06-28", "close": 723.05, "volume": 6366365},
                {"date": "2024-07-01", "close": 713.85, "volume": 3516710},
                {"date": "2024-07-02", "close": 485.35, "volume": 12658263},
                {"date": "2024-07-03", "close": 495.30, "volume": 3237838},
            ]
        },
        {
            "symbol": "NESTLEIND",
            "action": {"symbol": "NESTLEIND", "action_type": "SPLIT", "ratio": 10.0, "ex_date": "2024-01-05"},
            "raw_candles": [
                {"date": "2024-01-03", "close": 26635.20, "volume": 101346},
                {"date": "2024-01-04", "close": 27116.40, "volume": 132390},
                {"date": "2024-01-05", "close": 2666.40, "volume": 2577064},
                {"date": "2024-01-08", "close": 2619.30, "volume": 1032378},
            ]
        },
    ]

    for case in real_cases:
        sym = case["symbol"]
        act = case["action"]
        raw = [dict(c) for c in case["raw_candles"]]
        adj = adjust_price_for_corporate_actions(raw, [act])

        # Find ex-date candle and pre-ex candle
        ex_idx = [i for i, c in enumerate(adj) if c["date"] == act["ex_date"]][0]
        c_pre = adj[ex_idx - 1]
        c_ex = adj[ex_idx]

        # Calculate ex-date adjusted economic return
        adj_return = ((c_ex["close"] - c_pre["close"]) / c_pre["close"]) * 100.0
        assert abs(adj_return) < 25.0, (
            f"Ex-date adjusted return for {sym} ({adj_return:.2f}%) exceeds plausible 25% threshold"
        )

        # Test double-adjustment prevention guard:
        # Re-running adjustment on already-adjusted data must NO-OP
        re_adj = adjust_price_for_corporate_actions(adj, [act])
        assert re_adj[0]["close"] == adj[0]["close"], f"Double adjustment guard failed to no-op for {sym}"


def test_flat_ex_date_price_does_not_misfire():
    """
    Assert that when price genuinely doesn't move across ex-date on an adjusted basis
    (adjusted return = 0.0%), the double-adjustment guard does NOT misfire and correctly
    applies the backward split adjustment.
    """
    mock_action = {
        "symbol": "FLATCO",
        "action_type": "SPLIT",
        "ratio": 2.0,
        "ex_date": "2026-03-25",
    }

    # Raw prices drop exactly 2.0x (from 200.0 to 100.0), meaning adjusted return is exactly 0.0%
    flat_candles = [
        {"date": "2026-03-24", "open": 200.0, "high": 205.0, "low": 195.0, "close": 200.0, "volume": 1000},
        {"date": "2026-03-25", "open": 100.0, "high": 102.0, "low": 98.0, "close": 100.0, "volume": 2000},
    ]

    adjusted = adjust_price_for_corporate_actions(flat_candles, [mock_action])
    assert len(adjusted) == 2

    # Pre-split candle must be adjusted to 100.0 (200.0 / 2.0)
    assert adjusted[0]["close"] == 100.0
    assert adjusted[0]["adj_factor"] == 2.0
    assert adjusted[1]["close"] == 100.0
    assert adjusted[1]["adj_factor"] == 1.0

    # Economic return across ex-date is exactly 0.0%
    adj_ret = ((adjusted[1]["close"] - adjusted[0]["close"]) / adjusted[0]["close"]) * 100.0
    assert adj_ret == 0.0

    # Conversely, if candles are already adjusted (100.0 -> 100.0 in raw input),
    # the guard MUST fire and refuse to divide by 2 again (no-op)
    already_adjusted_candles = [
        {"date": "2026-03-24", "open": 100.0, "high": 102.0, "low": 98.0, "close": 100.0, "volume": 2000},
        {"date": "2026-03-25", "open": 100.0, "high": 102.0, "low": 98.0, "close": 100.0, "volume": 2000},
    ]
    no_op_result = adjust_price_for_corporate_actions(already_adjusted_candles, [mock_action])
    assert no_op_result[0]["close"] == 100.0, "Guard failed to no-op on already adjusted flat series"


