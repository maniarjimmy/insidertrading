import json
import os
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from filings import classify_catalyst_v2

CACHE_DIR = os.path.join(BASE_DIR, "output", "cache", "announcements")


def run():
    head_commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode().strip()
    out_file = os.path.join(BASE_DIR, "output", "audit", f"recall_mismatches_4_{head_commit}.txt")
    os.makedirs(os.path.dirname(out_file), exist_ok=True)

    targets = [
        {"symbol": "ACMESOLAR", "date": "2026-05-09"},
        {"symbol": "HFCL", "date": "2026-02-10"},
        {"symbol": "IKS", "date": "2026-04-23"},
        {"symbol": "TRITURBINE", "date": "2026-02-05"},
    ]

    lines = []
    lines.append("=" * 115)
    lines.append(f"AUDIT OF 4 MISMATCH ROWS FROM 80-ROW SELF-GRADED SAMPLE | COMMIT: {head_commit}")
    lines.append("=" * 115)
    lines.append("Status Notice: Self-graded exploration by assistant. No empirical recall claimed.\n")

    for t in targets:
        sym = t["symbol"]
        dt_sub = t["date"]
        cache_path = os.path.join(CACHE_DIR, f"{sym}.json")
        matched = None
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as fp:
                items = json.load(fp)
                for it in items:
                    dstr = it.get("date_str", "")
                    if dt_sub in dstr:
                        matched = it
                        break

        lines.append(f"SYMBOL: {sym} | Target Date: {dt_sub}")
        if not matched:
            lines.append("  [Record not found in cache]")
            lines.append("-" * 115)
            continue

        desc = matched.get("desc", "")
        att = matched.get("attchmntText", "")
        url = matched.get("url", "")

        state_v2, mat_v2, cat_v2 = classify_catalyst_v2(desc=desc, text=att)

        lines.append(f"  Description (desc): {desc}")
        lines.append(f"  attchmntText:       {att}")
        lines.append(f"  Attachment URL:     {url}")
        lines.append(f"  v2 Verdict:         State={state_v2}, is_material={mat_v2}, Category={cat_v2}")

        # Diagnosis of discrepancy
        if sym == "ACMESOLAR":
            lines.append("  Assistant Grade:    MATERIAL (Discloses project commissioning / commercial capacity addition)")
            lines.append("  Root Cause of Miss: The exchange 'desc' is 'Updates' and attchmntText describes operational")
            lines.append("                      synchronization of solar capacity, missed by strict v2 text patterns.")
        elif sym == "HFCL":
            lines.append("  Assistant Grade:    MATERIAL (Discloses commercial order win for optical fiber cables)")
            lines.append("  Root Cause of Miss: The exchange 'desc' is 'Updates' and attchmntText mentions 'advance purchase order'")
            lines.append("                      which was not captured under standard 'order win' pattern.")
        elif sym == "IKS":
            lines.append("  Assistant Grade:    ROUTINE (Internal restructuring / step-down subsidiary incorporation)")
            lines.append("  Root Cause of FP:   Filing contains 'Acquisition' in desc, so classifier flagged it as CATALYST/1,")
            lines.append("                      whereas the content was a nominal internal subsidiary creation.")
        elif sym == "TRITURBINE":
            lines.append("  Assistant Grade:    ROUTINE (Intimation of board meeting schedule without actual dividend/results declared)")
            lines.append("  Root Cause of FP:   Filing desc is 'Board Meeting', which classifier marks CATALYST/1/Board Meeting,")
            lines.append("                      whereas assistant self-grade considered advance meeting intimations as routine.")

        lines.append("-" * 115)

    out_text = "\n".join(lines)
    print(out_text)
    with open(out_file, "w", encoding="utf-8") as fp:
        fp.write(out_text)
    print(f"\n[4 Mismatch rows audit written to {out_file}]")


if __name__ == "__main__":
    run()
