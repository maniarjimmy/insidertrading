"""
Unit Tests for Corporate Filings & Catalyst Classification Module (filings.py)
Phase 2 Test Suite:
1. Evaluates unified classifier on training set (100% target).
2. Evaluates unified classifier on held-out benchmark fixtures (reporting precision/recall).
3. Verifies BSE-to-NSE symbol and ISIN mapping (Requirement D).
4. Verifies pre-announcement event-calendar radar (Requirement F).
5. Verifies caching and request throttling (Requirement E).
"""

from datetime import date, datetime, timedelta
import json
import os
import unittest.mock as mock
import pytest

from filings import (
    _FILINGS_CACHE,
    check_pre_announcement_radar,
    classify_catalyst,
    fetch_corporate_filings,
    fetch_event_calendar,
    get_bse_scrip_code,
    load_symbol_mapping,
)


@pytest.fixture
def fixtures_data():
    fixture_file = os.path.join(os.path.dirname(__file__), "fixtures", "filings_fixtures.json")
    assert os.path.exists(fixture_file), f"Fixture file not found at {fixture_file}"
    with open(fixture_file, "r", encoding="utf-8") as f:
        return json.load(f)


def test_classify_catalyst_training_fixtures(fixtures_data):
    """Verify 100% accuracy on the 25 training fixtures."""
    training_items = [x for x in fixtures_data if x["split"] == "training"]
    assert len(training_items) == 25

    for item in training_items:
        pred_state, pred_mat, pred_cat = classify_catalyst(desc=item["desc"], text=item["text"])
        assert pred_mat == item["expected_material"], (
            f"Failed on #{item['id']} ({item['symbol']}): "
            f"expected material={item['expected_material']}, got {pred_mat} ({pred_cat}) "
            f"Text: {item['text']}"
        )
        assert pred_state == item["expected_state"], (
            f"Failed state on #{item['id']} ({item['symbol']}): "
            f"expected state={item['expected_state']}, got {pred_state}"
        )


def test_classify_catalyst_validation_benchmark(fixtures_data):
    """
    Evaluate precision and recall on the 25 validation benchmark fixtures.
    Must achieve ≥ 90% precision and ≥ 85% recall on validation data.
    """
    val_items = [x for x in fixtures_data if x["split"] == "validation"]
    assert len(val_items) == 25

    tp = fp = tn = fn = 0
    for item in val_items:
        pred_state, pred_mat, pred_cat = classify_catalyst(desc=item["desc"], text=item["text"])
        exp_mat = item["expected_material"]

        if pred_mat == 1 and exp_mat == 1:
            tp += 1
        elif pred_mat == 1 and exp_mat == 0:
            fp += 1
        elif pred_mat == 0 and exp_mat == 0:
            tn += 1
        elif pred_mat == 0 and exp_mat == 1:
            fn += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    accuracy = (tp + tn) / len(val_items)

    assert precision >= 0.90, f"Validation precision {precision:.2f} is below 0.90 threshold"
    assert recall >= 0.85, f"Validation recall {recall:.2f} is below 0.85 threshold"
    assert accuracy >= 0.90, f"Validation accuracy {accuracy:.2f} is below 0.90 threshold"


def test_bse_to_nse_symbol_mapping():
    """Verify BSE-to-NSE symbol and ISIN mapping for representative equities (Requirement D)."""
    mapping = load_symbol_mapping()
    assert len(mapping) >= 400, f"Expected at least 400 mapped securities, got {len(mapping)}"

    # Check key symbols
    test_symbols = {
        "COCHINSHIP": "540678",
        "MAZDOCK": "543237",
        "HINDALCO": "500440",
        "TATAPOWER": "500400",
        "INFY": "500209",
    }

    for sym, expected_bse in test_symbols.items():
        bse_code = get_bse_scrip_code(sym)
        assert bse_code is not None, f"Failed to map NSE symbol {sym} to BSE code"
        assert bse_code == expected_bse, f"Symbol {sym} mapped to {bse_code}, expected {expected_bse}"


def test_classify_catalyst_edge_cases():
    """Verify specific edge cases: disinvestment, production commencement, generic contract wins, and tax orders."""
    # 1. Disinvestment (SHRIRAMFIN)
    st, mat, cat = classify_catalyst(
        desc="Diversification/Disinvestment",
        text="Shriram Overseas Investments has divested its entire stake of 81.63% in Bharath Investments Pte"
    )
    assert mat == 1
    assert st == "CATALYST"

    # 2. Production commencement (WAAREEENER)
    st, mat, cat = classify_catalyst(
        desc="Commencement of commercial production/operations",
        text="Commencement of commercial production by Sangam Solar One"
    )
    assert mat == 1
    assert st == "CATALYST"

    # 3. Generic desc with contract win text (MAZDOCK)
    st, mat, cat = classify_catalyst(
        desc="Disclosure of material issue",
        text="Mazagon Dock Shipbuilders has entered into a contract with Shipping Corporation of India for construction and sale of PSV"
    )
    assert mat == 1
    assert st == "CATALYST"
    assert cat == "Order Win"

    # 4. Tax demand / penalty order routine (VOLTAS)
    with mock.patch("filings.extract_pdf_first_page_text", return_value="demanding payment of differential customs duty of 10.76 crores and a penalty"):
        st, mat, cat = classify_catalyst(
            desc="Action(s) taken or orders passed",
            text="intimation under Regulation 30",
            url="https://nsearchives.nseindia.com/corporate/test.pdf"
        )
        assert mat == 0
        assert st == "NONE"
        assert cat == "Routine Disclosure"

    # 5. SAST statutory routine exemption
    st, mat, cat = classify_catalyst(
        desc="Acquisition",
        text="Disclosures under Reg. 31(4) of SEBI (SAST) Regulations, 2011"
    )
    assert mat == 0
    assert st == "NONE"
    assert cat == "Routine Disclosure"


def test_event_calendar_radar_lookup():
    """Test upcoming corporate event radar detection (Requirement F)."""
    sample_calendar = [
        {
            "symbol": "MAZDOCK",
            "company": "Mazagon Dock Shipbuilders Limited",
            "purpose": "Financial Results/Dividend",
            "date": "25-Nov-2026",
            "bm_desc": "Board meeting to consider interim dividend",
        },
        {
            "symbol": "COCHINSHIP",
            "company": "Cochin Shipyard Limited",
            "purpose": "Financial Results",
            "date": "28-Nov-2026",
            "bm_desc": "Board meeting to approve quarterly results",
        },
    ]

    with mock.patch("filings.fetch_event_calendar", return_value=sample_calendar):
        radar_hit = check_pre_announcement_radar("MAZDOCK", days_ahead=7)
        assert radar_hit is not None
        assert radar_hit["symbol"] == "MAZDOCK"
        assert radar_hit["purpose"] == "Financial Results/Dividend"
        assert radar_hit["event_date"] == "25-Nov-2026"

        radar_miss = check_pre_announcement_radar("RELIANCE", days_ahead=7)
        assert radar_miss is None


def test_filings_caching_mechanism():
    """Verify in-memory caching prevents redundant external network requests (Requirement E)."""
    sym = "TESTSYM"
    d1 = date(2026, 4, 1)
    d2 = date(2026, 4, 10)
    cache_key = (sym, d1.strftime("%d-%m-%Y"), d2.strftime("%d-%m-%Y"))

    mock_filing = [{
        "symbol": sym,
        "date_str": "05-Apr-2026 12:00:00",
        "desc": "Financial Results",
        "text": "Quarterly results announced",
        "url": "https://nsearchives.nseindia.com/doc.pdf",
        "catalyst_state": "CATALYST",
        "is_material": 1,
        "category": "Financial Results",
        "source": "NSE",
    }]

    _FILINGS_CACHE[cache_key] = mock_filing
    try:
        # Should return cached item directly without network calls
        with mock.patch("filings.get_nse_session") as mock_session:
            results = fetch_corporate_filings(sym, d1, d2)
            assert len(results) == 1
            assert results[0]["category"] == "Financial Results"
            mock_session.assert_not_called()
    finally:
        _FILINGS_CACHE.pop(cache_key, None)
