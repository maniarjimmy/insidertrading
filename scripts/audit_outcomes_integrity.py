import csv
import io
import json
import os
import re
import sqlite3
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "output", "scanner.db")
CACHE_FILE = os.path.join(BASE_DIR, "output", "cache", "announcements", "MAZDOCK.json")
PDF_CACHE_PATH = os.path.join(BASE_DIR, "output", "cache", "pdf_text_cache.json")


def run():
    head_commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode().strip()
    out_file = os.path.join(BASE_DIR, "output", "audit", f"outcomes_diff_{head_commit}.txt")
    os.makedirs(os.path.dirname(out_file), exist_ok=True)

    lines = []
    lines.append("=" * 115)
    lines.append(f"OUTCOMES INTEGRITY & MAZDOCK AUDIT (3cdcdca VS CURRENT SCANNER.DB) | COMMIT: {head_commit}")
    lines.append("=" * 115)

    # 1. Parse commit 3cdcdca output/scanner.sql
    raw_sql = subprocess.check_output(["git", "show", "3cdcdca:output/scanner.sql"]).decode("utf-8")
    orig_outcomes = {}

    for line in raw_sql.splitlines():
        if 'INSERT INTO "outcomes"' in line:
            m = re.search(r'\((.*)\);', line)
            if m:
                reader = csv.reader(io.StringIO(m.group(1)), quotechar="'", skipinitialspace=True)
                for row in reader:
                    oid = int(row[0])
                    fid = int(row[1])
                    h = int(row[2])
                    atype = row[8] if row[8] != 'NULL' else None
                    ismat = int(row[9])
                    orig_outcomes[oid] = {
                        "id": oid, "flag_id": fid, "horizon": h,
                        "announcement_type": atype, "is_material": ismat
                    }

    lines.append(f"Original Outcomes in commit 3cdcdca: {len(orig_outcomes)} rows")

    # 2. Query current scanner.db
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT id, flag_id, horizon_days, announcement_type, is_material FROM outcomes")
    curr_outcomes = {r["id"]: dict(r) for r in cur.fetchall()}

    lines.append(f"Current Outcomes in scanner.db:      {len(curr_outcomes)} rows\n")

    # 3. Compute Diff
    unchanged = 0
    zero_to_one = []
    one_to_zero = []
    type_changes_only = []

    for oid, o in orig_outcomes.items():
        c = curr_outcomes.get(oid)
        if not c:
            continue
        o_mat = o["is_material"]
        c_mat = c["is_material"]
        o_type = o["announcement_type"]
        c_type = c["announcement_type"]

        if o_mat == c_mat and o_type == c_type:
            unchanged += 1
        elif o_mat == 0 and c_mat == 1:
            zero_to_one.append((oid, o["flag_id"], o["horizon"], o_type, c_type))
        elif o_mat == 1 and c_mat == 0:
            one_to_zero.append((oid, o["flag_id"], o["horizon"], o_type, c_type))
        else:
            type_changes_only.append((oid, o["flag_id"], o["horizon"], o_type, c_type, o_mat))

    lines.append("OUTCOMES DIFF SUMMARY (3cdcdca -> CURRENT):")
    lines.append(f"  Unchanged rows:                                     {unchanged:,}")
    lines.append(f"  Promoted to Material (is_material 0 -> 1):          {len(zero_to_one)}")
    lines.append(f"  Demoted to Non-Material (is_material 1 -> 0):       {len(one_to_zero)}")
    lines.append(f"  Category Name Changed Only (is_material unchanged): {len(type_changes_only)}\n")

    if zero_to_one:
        lines.append("PROMOTED ROWS (is_material 0 -> 1):")
        lines.append(f"{'ID':<6} | {'Flag ID':<8} | {'Horizon':<8} | {'Original Type (3cdcdca)':<28} | {'Current Type'}")
        lines.append("-" * 80)
        for row in zero_to_one[:20]:
            lines.append(f"{row[0]:<6} | {row[1]:<8} | {row[2]:<8} | {str(row[3]):<28} | {row[4]}")
        if len(zero_to_one) > 20:
            lines.append(f"... and {len(zero_to_one) - 20} more rows")
        lines.append("")

    if one_to_zero:
        lines.append("DEMOTED ROWS (is_material 1 -> 0):")
        lines.append(f"{'ID':<6} | {'Flag ID':<8} | {'Horizon':<8} | {'Original Type (3cdcdca)':<28} | {'Current Type'}")
        lines.append("-" * 80)
        for row in one_to_zero:
            lines.append(f"{row[0]:<6} | {row[1]:<8} | {row[2]:<8} | {str(row[3]):<28} | {row[4]}")
        lines.append("")

    # 4. MAZDOCK Outcome ID 105 Forensic Inspection
    lines.append("=" * 115)
    lines.append("FORENSIC INSPECTION OF OUTCOME ID 105 (MAZDOCK):")
    cur.execute("""
        SELECT o.id, o.flag_id, f.symbol, f.scan_date, o.horizon_days, o.announcement_type, o.is_material,
               o.entry_price, o.forward_return, o.benchmark_return, o.excess_return,
               o.announcement_date, o.announcement_title, o.announcement_url
        FROM outcomes o
        JOIN flags f ON o.flag_id = f.id
        WHERE o.id = 105
    """)
    o105 = dict(cur.fetchone())
    for k, v in o105.items():
        lines.append(f"  {k:<20}: {v}")

    # Inspect cached announcement for MAZDOCK around March 18, 2026
    att_text = ""
    url = ""
    desc = ""
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as fp:
            data = json.load(fp)
            for it in data:
                dstr = it.get("date_str", "")
                if "2026-03-18" in dstr or "18-03-2026" in dstr or "18-Mar-2026" in dstr:
                    desc = it.get("desc", "")
                    att_text = it.get("attchmntText", "")
                    url = it.get("url", "")
                    break

    lines.append("\nEXACT EXCHANGE ANNOUNCEMENT FOR MAZDOCK ON 18-MAR-2026:")
    lines.append(f"  Description (desc): {desc}")
    lines.append(f"  attchmntText:       '{att_text}'")
    lines.append(f"  Attachment URL:     {url}")

    # Check PDF cache
    pdf_text = ""
    if os.path.exists(PDF_CACHE_PATH):
        with open(PDF_CACHE_PATH, "r", encoding="utf-8") as fp:
            pdf_data = json.load(fp)
            pdf_text = pdf_data.get(url, "")

    lines.append(f"  PDF Text Snippet:   {pdf_text[:300]}...\n" if len(pdf_text) > 300 else f"  PDF Text: {pdf_text}\n")

    # Reconciliation and Retraction
    lines.append("RETRACTION & RECONCILIATION:")
    lines.append("1. Comparison of Claims:")
    lines.append("   - Earlier Report: 'single PSV for SCI'")
    lines.append("   - Subsequent Report: 'Indian Navy/SCI container ship Rs 1,072 Cr'")
    lines.append("2. Factual Evidence from Filing & PDF:")
    lines.append("   - The filing title is: 'Mazagon Dock Shipbuilders Limited has informed the Exchange regarding a press release dated March 18, 2026, titled Mazagon Dock signs contract with SCI for design, construction and delivery of one offshore vessel.'")
    lines.append("   - The PDF text explicitly states: 'Mazagon Dock Shipbuilders Limited (MDL) has signed an agreement with Shipping Corporation of India (SCI) for design, building and delivery of one Platform Support Vessel (PSV) / Multi-Purpose Support Vessel.'")
    lines.append("   - There is NO mention of 'Indian Navy' in this contract; and it is an Offshore Platform Support Vessel (PSV), NOT a 'container ship'.")
    lines.append("3. Formal Retraction: The phrase 'Indian Navy/SCI container ship Rs 1,072 Cr' is FACTUALLY ERRONEOUS and is HEREBY RETRACTED.")
    lines.append("   The earlier description ('single PSV for SCI') is the FACTUALLY ACCURATE and SUPPORTED record.")
    lines.append("=" * 115)

    conn.close()

    out_text = "\n".join(lines)
    print(out_text)
    with open(out_file, "w", encoding="utf-8") as fp:
        fp.write(out_text)
    print(f"\n[Outcomes diff written to {out_file}]")


if __name__ == "__main__":
    run()
