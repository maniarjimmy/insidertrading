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
    classify_catalyst_v2,
    classify_catalyst_v3,
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
            url="https://nsearchives.nseindia.com/corporate/test.pdf",
            parse_pdf=True
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


def test_classify_catalyst_v3_regraded_and_rules():
    """Verify classifier-v3 precision rules on regraded rows and statutory boundaries."""
    # 1. TRITURBINE TDS dividend fix
    st, mat, cat = classify_catalyst_v3("Updates", "Communication To Shareholders- Intimation On Tax Deduction On Dividend")
    assert mat == 0 and st == "NONE" and cat == "Routine Disclosure"

    # 2. ACMESOLAR and HFCL routine disclosures
    st, mat, cat = classify_catalyst_v3("General Updates", "Acme Solar Holdings Limited has informed the Exchange about submission of Newspaper Publication w.r.t. Audited Financial Results")
    assert mat == 0 and st == "NONE" and cat == "Routine Disclosure"

    st, mat, cat = classify_catalyst_v3("Analysts/Institutional Investor Meet/Con. Call Updates", "HFCL Limited has informed the Exchange about Transcript of Conference Call on the Un-audited Financial Results")
    assert mat == 0 and st == "NONE" and cat == "Routine Disclosure"

    # 3. IKS Third-Party Acquisition
    st, mat, cat = classify_catalyst_v3("Press Release", "IKS Health Announces Agreement to Acquire TruBridge to Strengthen Access to Rural Healthcare")
    assert mat == 1 and st == "CATALYST" and cat == "Acquisition (Third-Party)"

    # 4. Open Offer under SAST Reg 3/4/5/18 (genuine acquirer disclosure not dropped)
    st, mat, cat = classify_catalyst_v3("Acquisition", "Public Announcement under Regulation 3(1) and Regulation 4 of SEBI Takeover Regulations for Open Offer")
    assert mat == 1 and st == "CATALYST" and cat == "Acquisition (Third-Party)"

    # 5. Routine SAST Reg 29/31 (statutory disclosure dropped)
    st, mat, cat = classify_catalyst_v3("Acquisition", "Disclosure under Regulation 29(2) of SEBI (Substantial Acquisition of Shares and Takeovers) Regulations, 2011")
    assert mat == 0 and st == "NONE" and cat == "Routine Disclosure"

    st, mat, cat = classify_catalyst_v3("Acquisition", "Disclosure under Regulation 31(1) of SEBI SAST Regulations regarding encumbrance of shares by promoter")
    assert mat == 0 and st == "NONE" and cat == "Routine Disclosure"

    # 6. Credit Rating: Upgrade vs Reaffirmation vs Downgrade
    st, mat, cat = classify_catalyst_v3("Credit Rating", "CRISIL Ratings has upgraded its rating on bank facilities to CRISIL AA/Stable")
    assert mat == 1 and st == "CATALYST" and cat == "Credit Rating (Upgrade)"

    st, mat, cat = classify_catalyst_v3("Credit Rating", "ICRA has reaffirmed the credit rating of the company at ICRA A1+")
    assert mat == 0 and st == "NONE" and cat == "Credit Rating (Reaffirmation)"

    st, mat, cat = classify_catalyst_v3("Credit Rating", "CARE has downgraded the rating on long term bank facilities to CARE BBB")
    assert mat == 0 and st == "CATALYST" and cat == "Credit Rating (Downgrade)"

    # 7. Intra-group / JV vs Third-Party Acquisition
    st, mat, cat = classify_catalyst_v3("Acquisition", "Incorporation of a new wholly owned subsidiary in Germany")
    assert mat == 0 and st == "CATALYST" and cat == "Acquisition (Intra-Group/JV)"

    st, mat, cat = classify_catalyst_v3("Acquisition", "Execution of definitive agreement for slump sale of manufacturing unit")
    assert mat == 0 and st == "CATALYST" and cat == "Disinvestment"

    # 8. Order Win and Production Commencement
    st, mat, cat = classify_catalyst_v3("Award of Order / Receipt of Order", "Company bags new commercial order worth Rs 450 Cr from Indian Railways")
    assert mat == 1 and st == "CATALYST" and cat == "Order Win"

    st, mat, cat = classify_catalyst_v3("Commencement of Commercial Production", "Commencement of commercial operations at Dahej solar glass manufacturing facility")
    assert mat == 1 and st == "CATALYST" and cat == "Production Commencement"

