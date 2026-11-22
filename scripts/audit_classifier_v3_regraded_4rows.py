import os
import sys
import subprocess

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from filings import classify_catalyst_v3

def run():
    head_commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode().strip()
    out_file = os.path.join(BASE_DIR, "output", "audit", f"classifier_v3_regraded_4rows_{head_commit}.txt")
    os.makedirs(os.path.dirname(out_file), exist_ok=True)

    rows = [
        {
            "symbol": "ACMESOLAR",
            "desc": "General Updates",
            "text": "Acme Solar Holdings Limited has informed the Exchange about submission of Newspaper Publication w.r.t. Audited Financial Results for the Quarter and Financial Year ended March 31, 2026",
            "expected_state": "NONE",
            "expected_mat": 0,
            "expected_cat": "Routine Disclosure",
            "rationale": "Newspaper publication of financial results -> Routine Disclosure under Priority 1/2a"
        },
        {
            "symbol": "HFCL",
            "desc": "Analysts/Institutional Investor Meet/Con. Call Updates",
            "text": "HFCL Limited has informed the Exchange about Transcript of Conference Call on the Un-audited Financial Results of the Company for the 3rd Quarter and Nine Months ended December 31, 2025, of the Financial Year 2025-26",
            "expected_state": "NONE",
            "expected_mat": 0,
            "expected_cat": "Routine Disclosure",
            "rationale": "Analyst concall transcript -> Routine Disclosure under Priority 1/2a"
        },
        {
            "symbol": "IKS",
            "desc": "Press Release",
            "text": 'Inventurus Knowledge Solutions Limited has informed the Exchange regarding a press release dated April 23, 2026, titled "IKS Health Announces Agreement to Acquire TruBridge to Strengthen Access to Rural and Community-Based Healthcare".',
            "expected_state": "CATALYST",
            "expected_mat": 1,
            "expected_cat": "Acquisition (Third-Party)",
            "rationale": "Press release announcing genuine third-party commercial acquisition -> Positive Unscheduled-Material"
        },
        {
            "symbol": "TRITURBINE",
            "desc": "Updates",
            "text": "Triveni Turbine Limited has informed the Exchange regarding 'Communication To Shareholders- Intimation On Tax Deduction On Dividend'.",
            "expected_state": "NONE",
            "expected_mat": 0,
            "expected_cat": "Routine Disclosure",
            "rationale": "Dividend TDS / tax deduction circular to shareholders -> Routine Disclosure (TRITURBINE fix)"
        },
    ]

    # Additional Edge Cases required by Item 3:
    # 3a. Credit rating upgrade vs reaffirmation vs downgrade
    # 3b. Third-party acquisition vs intra-group vs slump sale / disinvestment
    # 3c. SAST open offer exemption vs routine Reg 29/31 disclosures
    edge_cases = [
        {
            "case": "3a. Credit Rating Upgrade",
            "desc": "Credit Rating",
            "text": "CRISIL has upgraded the long-term bank facilities rating to CRISIL AA+ from CRISIL AA.",
            "expected_state": "CATALYST",
            "expected_mat": 1,
            "expected_cat": "Credit Rating (Upgrade)",
        },
        {
            "case": "3a. Credit Rating Reaffirmation",
            "desc": "Credit Rating",
            "text": "ICRA has reaffirmed the credit rating of ICRA A1+ for commercial paper.",
            "expected_state": "NONE",
            "expected_mat": 0,
            "expected_cat": "Credit Rating (Reaffirmation)",
        },
        {
            "case": "3a. Credit Rating Downgrade",
            "desc": "Credit Rating",
            "text": "Care Ratings has downgraded the long term debt instrument to CARE BBB- with negative outlook.",
            "expected_state": "CATALYST",
            "expected_mat": 0,
            "expected_cat": "Credit Rating (Downgrade)",
        },
        {
            "case": "3b. Intra-Group / Subsidiary Investment",
            "desc": "Acquisition",
            "text": "Investment in wholly owned subsidiary company to set up greenfield unit.",
            "expected_state": "CATALYST",
            "expected_mat": 0,
            "expected_cat": "Acquisition (Intra-Group/JV)",
        },
        {
            "case": "3b. Disinvestment / Slump Sale",
            "desc": "Acquisition",
            "text": "Execution of definitive agreement for slump sale and divestment of chemical division.",
            "expected_state": "CATALYST",
            "expected_mat": 0,
            "expected_cat": "Disinvestment",
        },
        {
            "case": "3c. SAST Open Offer (Reg 3/4/18)",
            "desc": "Takeover Regulations",
            "text": "Detailed public statement and open offer under Regulation 3(1) and 4 of SEBI SAST Regulations.",
            "expected_state": "CATALYST",
            "expected_mat": 1,
            "expected_cat": "Acquisition (Third-Party)",
        },
        {
            "case": "3c. Routine SAST Reg 29/31 Disclosure",
            "desc": "Takeover Regulations",
            "text": "Disclosure under Regulation 31(1) and 31(2) of SEBI SAST Regulations regarding release of pledge.",
            "expected_state": "NONE",
            "expected_mat": 0,
            "expected_cat": "Routine Disclosure",
        },
    ]

    lines = []
    lines.append("=" * 115)
    lines.append(f"CLASSIFIER-V3 AUDIT: 4 REGRADED ROWS & DIRECTIVE 3 EDGE CASES | COMMIT: {head_commit}")
    lines.append("=" * 115)
    lines.append("Protocol: Deterministic TEXT-ONLY (desc + attchmntText). Zero PDF extraction. Zero network requests.\n")

    lines.append("1. AUDIT OF 4 REGRADED MISMATCH ROWS (DIRECTIVE 3):")
    lines.append("-" * 115)
    all_passed = True
    for r in rows:
        st, mat, cat = classify_catalyst_v3(desc=r["desc"], text=r["text"])
        ok = (st == r["expected_state"] and mat == r["expected_mat"] and cat == r["expected_cat"])
        if not ok:
            all_passed = False
        status_str = "PASS" if ok else "FAIL"
        lines.append(f"SYMBOL: {r['symbol']} | Status: {status_str}")
        lines.append(f"  Exchange desc: {r['desc']}")
        lines.append(f"  attchmntText:  {r['text']}")
        lines.append(f"  Classifier-v3: state={st}, is_material={mat}, category={cat}")
        lines.append(f"  Expected:      state={r['expected_state']}, is_material={r['expected_mat']}, category={r['expected_cat']}")
        lines.append(f"  Rationale:     {r['rationale']}")
        lines.append("-" * 115)

    lines.append("\n2. AUDIT OF DIRECTIVE 3 BOUNDARY RULES & EDGE CASES:")
    lines.append("-" * 115)
    for ec in edge_cases:
        st, mat, cat = classify_catalyst_v3(desc=ec["desc"], text=ec["text"])
        ok = (st == ec["expected_state"] and mat == ec["expected_mat"] and cat == ec["expected_cat"])
        if not ok:
            all_passed = False
        status_str = "PASS" if ok else "FAIL"
        lines.append(f"Test Case: {ec['case']} | Status: {status_str}")
        lines.append(f"  Inputs:        desc='{ec['desc']}' | text='{ec['text']}'")
        lines.append(f"  Classifier-v3: state={st}, is_material={mat}, category={cat}")
        lines.append(f"  Expected:      state={ec['expected_state']}, is_material={ec['expected_mat']}, category={ec['expected_cat']}")
        lines.append("-" * 115)

    lines.append(f"\nOVERALL AUDIT RESULT: {'ALL PASS' if all_passed else 'FAILURES DETECTED'}")
    lines.append("=" * 115)

    out_text = "\n".join(lines)
    print(out_text)
    with open(out_file, "w", encoding="utf-8") as fp:
        fp.write(out_text)
    print(f"\nSaved classifier-v3 audit output to: {out_file}")

if __name__ == "__main__":
    run()
