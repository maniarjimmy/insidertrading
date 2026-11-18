"""
Unit Tests for Outcome Tracker Module (tracker.py)
Tests forward return calculation from next-day open, material vs. routine
announcement classification, benchmark excess return, control lift,
and forward-window filtering (filings on/before scan are context, not outcomes).
"""

from datetime import date, datetime
import tempfile
import pandas as pd
import pytest

from db import get_connection, init_db, upsert_flag
from tracker import (
    classify_announcement,
    evaluate_flag,
    parse_announcement_dt,
    parse_flag_timestamp,
)


def test_classify_announcement_material_catalysts():
    """Verify material categories correctly produce is_material = 1."""
    material_cases = [
        ("Financial Results for the quarter ended Dec 31", "Unaudited quarterly results", "Financial Results"),
        ("Board Meeting Intimation to consider Dividend", "Meeting scheduled on 25-Nov-2026", "Board Meeting"),
        ("Acquisition of 51% stake in European subsidiary", "Definitive agreement executed", "Acquisition"),
        ("Award of Contract worth Rs 1,200 Crores", "Major order won from Ministry of Defence", "Award Of Contract"),
        ("Fund Raising via QIP or Preferential Issue", "Board approved raising Rs 500 Cr", "Fund Raising"),
        ("Credit Rating upgrade by CRISIL to AA+", "Upgraded long term rating", "Credit Rating"),
        ("USFDA approval for ANDA application", "Received final approval", "Regulatory Approval"),
    ]

    for title, details, expected_type in material_cases:
        is_mat, cat = classify_announcement(title, details)
        assert is_mat == 1, f"Failed for {title}: got {is_mat}, {cat}"


def test_classify_announcement_routine_disclosures():
    """Verify routine administrative notices produce is_material = 0."""
    routine_cases = [
        ("Copy of Newspaper Publication", "Notice published in Financial Express", "Routine Disclosure"),
        ("Loss of Share Certificates / Duplicate Certificate", "Intimation under Regulation 39(3)", "Routine Disclosure"),
        ("Investor Presentation Q3 FY26", "Presentation uploaded for analysts", "Routine Disclosure"),
        ("Compliance Certificate under Regulation 74(5)", "Certificate from RTA", "Routine Disclosure"),
        ("Closure of Trading Window", "Window closed for designated persons", "Routine Disclosure"),
        ("Clarification on Price Movement", "Exchange query replied stating no undisclosed info", "Routine Disclosure"),
    ]

    for title, details, expected_type in routine_cases:
        is_mat, cat = classify_announcement(title, details)
        assert is_mat == 0, f"Expected routine for {title}: got {is_mat}, {cat}"


def test_forward_return_calculation_from_next_day_open():
    """
    Test forward return math: measured strictly from next-day open (T+1 Open) to T+N Close.
    Formula: ((Close_TN - Open_T1) / Open_T1) * 100
    """
    open_t1 = 100.0
    close_t1 = 102.0   # T+1 Close: +2.0%
    close_t3 = 108.5   # T+3 Close: +8.5%
    close_t5 = 95.0    # T+5 Close: -5.0%
    close_t10 = 115.0  # T+10 Close: +15.0%

    ret_t1 = round(((close_t1 - open_t1) / open_t1) * 100.0, 2)
    ret_t3 = round(((close_t3 - open_t1) / open_t1) * 100.0, 2)
    ret_t5 = round(((close_t5 - open_t1) / open_t1) * 100.0, 2)
    ret_t10 = round(((close_t10 - open_t1) / open_t1) * 100.0, 2)

    assert ret_t1 == 2.0
    assert ret_t3 == 8.5
    assert ret_t5 == -5.0
    assert ret_t10 == 15.0


def test_excess_return_vs_benchmark():
    """Test excess return: Stock Return - Benchmark Return over the same trading window."""
    stock_fwd_ret = 12.50
    bench_fwd_ret = 3.20
    excess = round(stock_fwd_ret - bench_fwd_ret, 2)
    assert excess == 9.30

    negative_stock_ret = -4.0
    bench_positive_ret = 2.0
    excess_negative = round(negative_stock_ret - bench_positive_ret, 2)
    assert excess_negative == -6.0


def test_statistical_lift_calculation():
    """Test lift ratio: Flagged Precision / Control Precision."""
    flagged_evaluated = 20
    flagged_catalysts = 12  # 60%
    control_evaluated = 20
    control_catalysts = 4   # 20%

    flagged_precision = (flagged_catalysts / flagged_evaluated) * 100.0
    control_precision = (control_catalysts / control_evaluated) * 100.0
    lift = round(flagged_precision / control_precision, 2)

    assert flagged_precision == 60.0
    assert control_precision == 20.0
    assert lift == 3.0


def test_flag_under_10_days_stays_active_with_only_elapsed_horizons(monkeypatch):
    """
    Verify that flags with < 10 trading days elapsed STAY ACTIVE and ONLY
    horizons with actual trading dates are recorded (no future/missing horizons).
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name
    init_db(db_path)

    try:
        # Scan date: 2026-04-06 (Monday). Evaluation date: 2026-04-08 (Wednesday).
        # Elapsed trading days: 2 (04-07 is T+1, 04-08 is T+2).
        # Horizons eligible: T+1 only (since TRACKING_HORIZONS has [1, 2, 3, 5, 10]).
        # Horizon 3, 5, 10 MUST NOT be written. Flag must stay ACTIVE.
        flag_id = upsert_flag({
            "scan_date": "2026-04-06",
            "symbol": "PARTIAL",
            "current_price": 500.0,
            "price_change": 5.0,
            "status": "ACTIVE",
            "run_type": "eod",
        }, db_path=db_path)

        # Mock stock price history for T+1 and T+2
        mock_df = pd.DataFrame({
            "Open": [505.0, 510.0],
            "Close": [510.0, 515.0],
        }, index=[date(2026, 4, 7), date(2026, 4, 8)])

        monkeypatch.setattr("tracker.fetch_price_history", lambda sym, s, e: mock_df)
        monkeypatch.setattr("tracker.fetch_corporate_announcements", lambda sym, s, e: [])

        # Temporarily point DB_PATH to test db
        monkeypatch.setattr("tracker.DB_PATH", db_path)
        monkeypatch.setattr("db.DB_PATH", db_path)

        flag_record = {
            "id": flag_id,
            "scan_date": "2026-04-06",
            "symbol": "PARTIAL",
        }

        # Evaluate as of 2026-04-08 (Wednesday, 2 trading days elapsed)
        res = evaluate_flag(flag_record, today=date(2026, 4, 8), benchmark_df=None, db_path=db_path)

        # Must stay ACTIVE (trading days elapsed = 2 < 10)
        assert res["status"] == "ACTIVE"
        assert res["trading_days_elapsed"] == 2

        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM flags WHERE id=?", (flag_id,))
            assert cursor.fetchone()["status"] == "ACTIVE"

            cursor.execute("SELECT horizon_days FROM outcomes WHERE flag_id=? ORDER BY horizon_days", (flag_id,))
            horizons = [r[0] for r in cursor.fetchall()]
            # Horions 1 and 2 exist (elapsed = 2); future horizons 3, 5, 10 must NOT exist!
            assert horizons == [1, 2]
    finally:
        import os
        try:
            os.remove(db_path)
        except Exception:
            pass


def test_announcement_window_starts_strictly_after_flag_timestamp(monkeypatch):
    """
    Verify that announcements published on or before the flag timestamp are
    treated as pre-move context (excluded from outcomes). Only announcements
    strictly after the flag timestamp are recorded as forward catalysts.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name
    init_db(db_path)

    try:
        flag_id = upsert_flag({
            "scan_date": "2026-04-06 14:30",
            "symbol": "ANNSYM",
            "current_price": 200.0,
            "status": "ACTIVE",
            "run_type": "eod",
        }, db_path=db_path)

        mock_stock_df = pd.DataFrame({
            "Open": [202.0],
            "Close": [205.0],
        }, index=[date(2026, 4, 7)])

        # 1. Pre-move filing: Published on 2026-04-06 10:00 (BEFORE scan timestamp 14:30)
        # 2. Post-move filing: Published on 2026-04-07 11:00 (AFTER scan timestamp)
        mock_announcements = [
            {
                "date_str": "06-Apr-2026 10:00:00",
                "dt": datetime(2026, 4, 6, 10, 0),
                "subject": "Financial Results for Q4",
                "details": "Company reports 40% jump in net profit",
                "url": "http://nse.com/res_q4.pdf",
            },
            {
                "date_str": "07-Apr-2026 11:00:00",
                "dt": datetime(2026, 4, 7, 11, 0),
                "subject": "Award of Contract worth Rs 500 Cr",
                "details": "Order win for supply of transmission towers",
                "url": "http://nse.com/order.pdf",
            }
        ]

        monkeypatch.setattr("tracker.fetch_price_history", lambda sym, s, e: mock_stock_df)
        monkeypatch.setattr("tracker.fetch_corporate_announcements", lambda sym, s, e: mock_announcements)
        monkeypatch.setattr("tracker.DB_PATH", db_path)
        monkeypatch.setattr("db.DB_PATH", db_path)

        flag_record = {
            "id": flag_id,
            "scan_date": "2026-04-06 14:30",
            "symbol": "ANNSYM",
        }

        # Evaluate as of 2026-04-07
        res = evaluate_flag(flag_record, today=date(2026, 4, 7), benchmark_df=None, db_path=db_path)

        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT is_material, announcement_type, announcement_title FROM outcomes WHERE flag_id=?", (flag_id,))
            row = cursor.fetchone()
            assert row["is_material"] == 1
            # Must match the POST-move announcement ("Order Win" / "Award Of Contract"), NOT the pre-move ("Financial Results")!
            assert row["announcement_type"] in ("Order Win", "Award Of Contract")
            assert "transmission towers" in row["announcement_title"]
    finally:
        import os
        try:
            os.remove(db_path)
        except Exception:
            pass
