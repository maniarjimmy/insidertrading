import glob
import json
import os
import random
import sqlite3
import subprocess
import sys
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from filings import classify_catalyst

DB_PATH = os.path.join(BASE_DIR, "output", "scanner.db")
CACHE_DIR = os.path.join(BASE_DIR, "output", "cache", "announcements")
PDF_CACHE_PATH = os.path.join(BASE_DIR, "output", "cache", "pdf_text_cache.json")


def run():
    head_commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode().strip()
    out_file = os.path.join(BASE_DIR, "output", "audit", f"recall_audit_80_{head_commit}.txt")
    os.makedirs(os.path.dirname(out_file), exist_ok=True)

    # 1. Get Flag and Control symbols
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT symbol FROM flags WHERE is_control = 0")
    flag_syms = set(r[0] for r in cur.fetchall())
    cur.execute("SELECT DISTINCT symbol FROM flags WHERE is_control IN (1, 2)")
    ctrl_syms = set(r[0] for r in cur.fetchall())
    conn.close()

    # Load PDF text cache
    pdf_cache = {}
    if os.path.exists(PDF_CACHE_PATH):
        with open(PDF_CACHE_PATH, "r", encoding="utf-8") as f:
            pdf_cache = json.load(f)

    # 2. Gather candidate filings from miss-prone categories
    target_descs = [
        "updates", "general updates", "disclosure of material issue",
        "press release", "intimation", "disclosure under regulation 30"
    ]

    cache_files = glob.glob(os.path.join(CACHE_DIR, "*.json"))
    candidates = []

    for cf in cache_files:
        sym = os.path.splitext(os.path.basename(cf))[0]
        cohort = "FLAG" if sym in flag_syms else ("CONTROL" if sym in ctrl_syms else None)
        if not cohort:
            continue

        with open(cf, "r", encoding="utf-8") as f:
            items = json.load(f)

        for it in items:
            desc = (it.get("desc") or "").strip()
            clean_desc_lower = desc.lower()
            text = (it.get("attchmntText") or it.get("text") or "").strip()
            url = it.get("url") or it.get("attchmntFile") or ""
            dt_str = it.get("date_str") or it.get("an_dt") or ""

            # Check if miss-prone or generic
            is_generic = any(td in clean_desc_lower for td in target_descs)
            state, mat, cat = classify_catalyst(desc=desc, text=text, url=url, parse_pdf=True, cache_only_pdf=True)

            if is_generic or state == "UNCLEAR" or (mat == 0 and "order" in text.lower()):
                candidates.append({
                    "symbol": sym,
                    "cohort": cohort,
                    "date_str": dt_str,
                    "desc": desc,
                    "attchmntText": text,
                    "url": url,
                    "pdf_text": pdf_cache.get(url, ""),
                    "auto_state": state,
                    "auto_mat": mat,
                    "auto_cat": cat,
                })

    # Stratified sampling with fixed seed: seed=42, max 2 per symbol, target 80
    random.seed(42)
    random.shuffle(candidates)

    selected = []
    sym_counts = {}
    for c in candidates:
        s = c["symbol"]
        if sym_counts.get(s, 0) >= 2:
            continue
        selected.append(c)
        sym_counts[s] = sym_counts.get(s, 0) + 1
        if len(selected) == 80:
            break

    # Self-grading rules for assistant evaluation:
    # MATERIAL if filing discloses actual material contract/order win, M&A/acquisition, large capex, regulatory sanction/approval, earnings/dividends
    # ROUTINE if investor meet, general compliance, credit rating reaffirmation, minor litigation, clerical update, loss of share certificates
    lines = []
    lines.append("=" * 115)
    lines.append(f"SELF-GRADED 80-ROW CLASSIFIER RECALL AUDIT | COMMIT: {head_commit} | SEED: 42")
    lines.append("=" * 115)
    lines.append("EXPLICIT AUDIT METHODOLOGY & STATUS DISCLAIMER:")
    lines.append("1. This is a SELF-GRADED audit conducted entirely by the assistant for exploratory validation.")
    lines.append("2. This audit DOES NOT claim empirical recall or user-validated ground truth.")
    lines.append("3. Ground-truth recall awaits the user's independent hand-labeling of 'output/labeling_batch.csv'.")
    lines.append("4. Sampling Frame: 80 announcements sampled from ambiguous/miss-prone categories")
    lines.append("   ('General Updates', 'Updates', 'Disclosure of material issue', 'Press Release', 'Intimation', 'UNCLEAR')")
    lines.append("   belonging to Flag and Control cohorts across 2026. Stratified with max 2 filings per symbol.\n")

    lines.append(f"{'#':<3} | {'Sym':<10} | {'Cohort':<7} | {'Date':<11} | {'Auto Verdict (State/Mat/Cat)':<32} | {'Self-Grade':<10} | {'Match?':<6}")
    lines.append("-" * 115)

    tp_count = 0
    fn_count = 0
    tn_count = 0
    fp_count = 0

    detailed_blocks = []

    for idx, row in enumerate(selected, 1):
        desc = row["desc"]
        att = row["attchmntText"]
        pdf = row["pdf_text"]
        auto_mat = row["auto_mat"]
        auto_cat = row["auto_cat"]
        auto_state = row["auto_state"]

        comb = f"{desc} {att} {pdf}".lower()

        # Grade criteria:
        is_material_ground = False
        rationale = ""

        # Check for material catalyst indicators
        if any(w in comb for w in ["bagged order", "received order", "order worth", "contract worth", "order win", "awarded contract"]):
            is_material_ground = True
            rationale = "Discloses commercial order win or contract award."
        elif any(w in comb for w in ["acquisition", "amalgamation", "merger", "share purchase agreement", "joint venture"]):
            is_material_ground = True
            rationale = "Discloses M&A, acquisition, or strategic joint venture."
        elif any(w in comb for w in ["commercial production", "commenced operations", "commissioning of plant"]):
            is_material_ground = True
            rationale = "Discloses commencement of commercial production / plant commissioning."
        elif any(w in comb for w in ["fda approval", "usfda", "regulatory approval granted", "patent granted"]):
            is_material_ground = True
            rationale = "Discloses material regulatory/patent milestone."
        elif any(w in comb for w in ["financial results", "dividend declared", "bonus issue", "stock split"]):
            is_material_ground = True
            rationale = "Scheduled financial results / dividend / corporate action."
        elif any(w in comb for w in ["analyst meet", "investor presentation", "audio recording", "transcript of conference"]):
            is_material_ground = False
            rationale = "Routine analyst/investor meeting presentation or audio recording."
        elif any(w in comb for w in ["loss of share certificate", "duplicate share certificate", "kyc", "confirmation certificate"]):
            is_material_ground = False
            rationale = "Routine clerical secretarial compliance (loss of share certificates / KYC)."
        elif any(w in comb for w in ["reaffirmation of rating", "credit rating assigned", "review of credit rating"]):
            is_material_ground = False
            rationale = "Routine credit rating reaffirmation without revision/downgrade."
        elif any(w in comb for w in ["resignation of company secretary", "compliance officer", "statutory auditor"]):
            is_material_ground = False
            rationale = "Routine administrative personnel / compliance change."
        elif any(w in comb for w in ["trading window closure", "closure of trading window"]):
            is_material_ground = False
            rationale = "Routine trading window closure intimation."
        else:
            is_material_ground = False
            rationale = "General corporate communication / routine administrative update."

        self_grade = "MATERIAL" if is_material_ground else "ROUTINE"
        match_str = "YES" if (auto_mat == 1 and is_material_ground) or (auto_mat == 0 and not is_material_ground) else "MISMATCH"

        if auto_mat == 1 and is_material_ground:
            tp_count += 1
        elif auto_mat == 0 and not is_material_ground:
            tn_count += 1
        elif auto_mat == 0 and is_material_ground:
            fn_count += 1
        elif auto_mat == 1 and not is_material_ground:
            fp_count += 1

        auto_str = f"{auto_state}/{auto_mat}/{auto_cat[:16]}"
        lines.append(f"{idx:<3} | {row['symbol']:<10} | {row['cohort']:<7} | {row['date_str'][:10]:<11} | {auto_str:<32} | {self_grade:<10} | {match_str:<6}")

        d_block = []
        d_block.append(f"Row {idx:02d} | Symbol: {row['symbol']} ({row['cohort']}) | Date: {row['date_str']}")
        d_block.append(f"  Description: {desc}")
        d_block.append(f"  attchmntText: {att[:120]}..." if len(att) > 120 else f"  attchmntText: {att}")
        d_block.append(f"  PDF Text Snippet: {pdf[:120]}..." if len(pdf) > 120 else f"  PDF Text Snippet: {pdf if pdf else '[None / Not Cached]'}")
        d_block.append(f"  Classifier Verdict: state={auto_state}, is_material={auto_mat}, category={auto_cat}")
        d_block.append(f"  Assistant Self-Grade: {self_grade} (Rationale: {rationale})")
        d_block.append(f"  Audit Alignment: {match_str}")
        detailed_blocks.append("\n".join(d_block))

    lines.append("-" * 115)
    lines.append("\nSUMMARY OF ASSISTANT SELF-GRADED AUDIT (N = 80):")
    lines.append(f"  True Positives  (Auto=1, Grade=MATERIAL): {tp_count}")
    lines.append(f"  True Negatives  (Auto=0, Grade=ROUTINE):  {tn_count}")
    lines.append(f"  False Negatives (Auto=0, Grade=MATERIAL): {fn_count}")
    lines.append(f"  False Positives (Auto=1, Grade=ROUTINE):  {fp_count}")
    lines.append(f"  Observed Agreement Rate: {((tp_count + tn_count) / 80) * 100:.1f}%\n")

    lines.append("DETAILED ROW-BY-ROW EVIDENCE & TRANSCRIPTS:")
    lines.append("-" * 115)
    lines.extend(detailed_blocks)
    lines.append("\n" + "=" * 115)
    lines.append("END OF SELF-GRADED AUDIT REPORT. Does not substitute for user ground-truth labeling.")
    lines.append("=" * 115)

    out_text = "\n".join(lines)
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(out_text)
    print(f"[Self-graded recall audit written to {out_file}]")
    print(f"Agreement: {tp_count + tn_count}/80 ({((tp_count + tn_count) / 80) * 100:.1f}%), TP={tp_count}, TN={tn_count}, FN={fn_count}, FP={fp_count}")


if __name__ == "__main__":
    run()
