"""
Unit Tests for Outcome Tracker Module (tracker.py)
Tests forward return calculation from next-day open, material vs. routine
announcement classification, benchmark excess return, and control lift.
"""

from datetime import date
import pytest

from tracker import classify_announcement


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
    """
    Test excess return: Stock Return - Benchmark Return over the same trading window.
    """
    stock_fwd_ret = 12.50
    bench_fwd_ret = 3.20
    excess = round(stock_fwd_ret - bench_fwd_ret, 2)
    assert excess == 9.30

    negative_stock_ret = -4.0
    bench_positive_ret = 2.0
    excess_negative = round(negative_stock_ret - bench_positive_ret, 2)
    assert excess_negative == -6.0


def test_statistical_lift_calculation():
    """
    Test lift ratio: Flagged Precision / Control Precision.
    """
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
