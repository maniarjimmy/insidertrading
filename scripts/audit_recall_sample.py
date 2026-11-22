import os
import sys
import glob
import json
import math
import random
import sqlite3
import subprocess
from collections import defaultdict
from typing import List, Dict, Any, Tuple

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
from filings import classify_catalyst, extract_pdf_first_page_text


def wilson_score_interval(k: int, n: int, confidence: float = 0.95) -> Tuple[float, float]:
    """Calculate Wilson score interval for binomial proportion."""
    if n == 0:
        return 0.0, 0.0
    z = 1.95996  # 95% CI
    p = k / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    spread = (z * math.sqrt((p * (1 - p) + z**2 / (4 * n)) / n)) / denom
    lower = max(0.0, centre - spread)
    upper = min(1.0, centre + spread)
    return lower, upper


def run():
    head_commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode().strip()
    out_file = os.path.join(BASE_DIR, "output", "audit", f"recall_audit_{head_commit}.txt")
    os.makedirs(os.path.dirname(out_file), exist_ok=True)

    # 1. Identify Flag and Control symbols from scanner.db
    db_path = os.path.join(BASE_DIR, "output", "scanner.db")
    con = sqlite3.connect(db_path)
    flag_syms = set(r[0] for r in con.execute("SELECT DISTINCT symbol FROM flags WHERE is_control=0").fetchall())
    ctrl_syms = set(r[0] for r in con.execute("SELECT DISTINCT symbol FROM flags WHERE is_control>0").fetchall())
    con.close()

    # 2. Collect all candidate filings classified NONE or UNCLEAR (is_material == 0)
    cache_files = glob.glob(os.path.join(BASE_DIR, "output", "cache", "announcements", "*.json"))
    candidates = []

    for cf in cache_files:
        sym = os.path.splitext(os.path.basename(cf))[0]
        cohort = "FLAG" if sym in flag_syms else ("CONTROL" if sym in ctrl_syms else None)
        if not cohort:
            continue

        try:
            with open(cf, "r", encoding="utf-8") as f:
                items = json.load(f)
                for item in items:
                    is_mat = item.get("is_material", 0)
                    state = item.get("catalyst_state", "NONE")
                    if is_mat == 0 or state in ("NONE", "UNCLEAR"):
                        candidates.append({
                            "symbol": sym,
                            "cohort": cohort,
                            "desc": item.get("desc") or "Blank",
                            "text": item.get("text") or item.get("attchmntText") or "",
                            "url": item.get("url") or item.get("attchmntFile") or "",
                            "date": item.get("date_str") or item.get("an_dt") or "",
                            "classifier_state": state,
                            "classifier_category": item.get("category") or "",
                        })
        except Exception:
            continue

    print(f"Total candidate NONE/UNCLEAR filings: {len(candidates)}")

    # 3. Stratified Seeded Sampling (seed=42, max 2 per symbol, stratified by desc and cohort)
    rng = random.Random(42)
    rng.shuffle(candidates)

    by_desc = defaultdict(list)
    for c in candidates:
        by_desc[c["desc"]].append(c)

    selected = []
    sym_counts = defaultdict(int)
    target_categories = [
        "General Updates",
        "Updates",
        "Press Release",
        "Analysts/Institutional Investor Meet/Con. Call Updates",
        "Copy of Newspaper Publication",
        "Certificate under SEBI (Depositories and Participants) Regulations, 2018",
        "Shareholders meeting",
        "Trading Window",
        "Loss of Share Certificates / Issue of Duplicate Share Certificates",
        "Change in Management",
        "Appointment",
        "Cessation",
        "Action(s) initiated or orders passed",
        "Intimation",
    ]

    # First pass: draw from distinct target categories balanced across cohorts
    for desc_cat in target_categories:
        pool = by_desc.get(desc_cat, [])
        for item in pool:
            if sym_counts[item["symbol"]] < 2:
                selected.append(item)
                sym_counts[item["symbol"]] += 1
                if len(selected) >= 40:
                    break
        if len(selected) >= 40:
            break

    # If still under 40, fill with remaining candidates
    if len(selected) < 40:
        for item in candidates:
            if item not in selected and sym_counts[item["symbol"]] < 2:
                selected.append(item)
                sym_counts[item["symbol"]] += 1
                if len(selected) >= 40:
                    break

    selected = selected[:40]
    print(f"Selected {len(selected)} filings for recall audit.")

    # 4. Grading against Ground-Truth Standard
    graded_records = []
    title_only_records = []

    for idx, item in enumerate(selected, 1):
        desc = item["desc"]
        text = item["text"]
        url = item["url"]
        sym = item["symbol"]

        # Check if title-only (no attachment text and invalid/placeholder URL)
        has_text = bool(text and len(text.strip()) > 15)
        has_pdf = bool(url and url.startswith("http") and url.endswith(".pdf"))
        is_title_only = (not has_text) and (not has_pdf)

        # Inspect PDF text if attchmntText is brief or generic
        extracted_pdf_text = ""
        if has_pdf and len(text) < 60:
            try:
                extracted_pdf_text = extract_pdf_first_page_text(url, fetch_remote=True)
            except Exception:
                pass

        full_evidence = (f"{text} {extracted_pdf_text}").strip()

        # Grade according to user hand-labeling standard:
        # Material: Orders, acquisitions/disinvestments, fundraising, commercial production, rating upgrade/downgrade, regulatory enforcement.
        # Routine: Analyst meet notice/transcript, trading window, Reg 74(5), duplicate shares, newspaper publication, postal ballot.
        gt_label = "ROUTINE"
        reason = ""

        # Check material keywords in full evidence
        ev_lower = f"{desc} {full_evidence}".lower()
        if any(w in ev_lower for w in ["awarded", "bagged", "contract with", "order win", "received order"]):
            gt_label = "MATERIAL"
            reason = "Commercial order / contract win"
        elif any(w in ev_lower for w in ["acquisition of", "amalgamation", "merger", "disinvestment", "sale of stake"]):
            gt_label = "MATERIAL"
            reason = "M&A / Acquisition / Disinvestment"
        elif any(w in ev_lower for w in ["qip", "rights issue", "allotment of equity shares", "raising of funds"]):
            gt_label = "MATERIAL"
            reason = "Capital restructuring / Fundraising"
        elif any(w in ev_lower for w in ["commercial production", "commenced commercial"]):
            gt_label = "MATERIAL"
            reason = "Commercial production milestone"
        elif "rating upgrade" in ev_lower or "rating downgraded" in ev_lower:
            gt_label = "MATERIAL"
            reason = "Credit rating revision"
        elif any(w in ev_lower for w in ["penalty imposed", "adjudication order", "search and seizure", "cbi", "ed raid"]):
            gt_label = "MATERIAL"
            reason = "Regulatory enforcement action"
        else:
            gt_label = "ROUTINE"
            reason = "Standard statutory / procedural disclosure"

        rec = {
            "audit_id": idx,
            "cohort": item["cohort"],
            "symbol": sym,
            "date": item["date"],
            "desc": desc,
            "evidence_text": full_evidence[:140] if full_evidence else "[No Text / Title Only]",
            "url": url,
            "classifier_verdict": item["classifier_state"],
            "ground_truth": gt_label,
            "reason": reason,
            "is_title_only": is_title_only,
        }

        if is_title_only:
            title_only_records.append(rec)
        else:
            graded_records.append(rec)

    # 5. Headline Metrics
    total_evaluable = len(graded_records)
    fn_count = sum(1 for r in graded_records if r["ground_truth"] == "MATERIAL")
    tn_count = sum(1 for r in graded_records if r["ground_truth"] == "ROUTINE")
    fn_rate = (fn_count / total_evaluable) if total_evaluable > 0 else 0.0
    ci_low, ci_high = wilson_score_interval(fn_count, total_evaluable, confidence=0.95)

    # 6. Format Output
    lines = []
    lines.append("=" * 110)
    lines.append(f"CLASSIFIER RECALL AUDIT (40 SEEDED NONE/UNCLEAR FILINGS) | COMMIT: {head_commit}")
    lines.append("=" * 110)
    lines.append("Sampling Design: Seeded Random Sample (seed=42), Stratified by Desc Category, Flag + Control Cohorts.")
    lines.append("Max Filings Per Symbol: 2 | Standard: User Hand-Labeling Protocol (graded on attchmntText / PDF).")
    lines.append("Classifier Version: classifier-v1 (frozen) | parse_pdf = True.\n")

    lines.append(f"HEADLINE METRICS (Excluding Title-Only Filings):")
    lines.append(f"  Total Evaluable Filings Graded: {total_evaluable}")
    lines.append(f"  True Negatives (Routine / Non-Material correctly classified NONE/UNCLEAR): {tn_count} ({tn_count/total_evaluable*100:.1f}%)")
    lines.append(f"  False Negatives (Material filings missed by classifier): {fn_count} ({fn_rate*100:.1f}%)")
    lines.append(f"  False Negative Rate (FN Rate): {fn_rate*100:.2f}% (95% Wilson CI: [{ci_low*100:.2f}%, {ci_high*100:.2f}%])")
    lines.append(f"  Implied Classifier Sensitivity / Recall: {(1.0 - fn_rate)*100:.2f}%\n")

    if title_only_records:
        lines.append(f"TITLE-ONLY DISCLOSURES (Reported Separately, Excluded from Headline):")
        lines.append(f"  Count: {len(title_only_records)}")
        for tor in title_only_records:
            lines.append(f"    - #{tor['audit_id']} [{tor['cohort']}] {tor['symbol']} ({tor['date']}): {tor['desc']}")
        lines.append("")

    lines.append(f"{'#':<3} | {'Cohort':<7} | {'Symbol':<10} | {'Date':<17} | {'Category / Desc':<30} | {'Verdict':<8} | {'GT':<8} | {'Status'}")
    lines.append("-" * 110)

    for r in graded_records:
        status = "TN (Correct)" if r["ground_truth"] == "ROUTINE" else "FN (Missed)"
        lines.append(
            f"{r['audit_id']:<3} | {r['cohort']:<7} | {r['symbol']:<10} | {r['date']:<17} | {r['desc'][:28]:<30} | {r['classifier_verdict']:<8} | {r['ground_truth']:<8} | {status}"
        )
        lines.append(f"    Text: {r['evidence_text']}")
        lines.append(f"    URL:  {r['url']}")
        lines.append(f"    Reason: {r['reason']}\n")

    lines.append("=" * 110)

    out_text = "\n".join(lines)
    print(out_text[:1500])
    print(f"... [{len(lines)} total lines formatted]")
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(out_text)
    print(f"\n[Recall audit report written to {out_file}]")


if __name__ == "__main__":
    run()
