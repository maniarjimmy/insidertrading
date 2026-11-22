import json
import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 1. Inspect pdf_text_cache.json
pdf_cache_file = os.path.join(BASE_DIR, "output", "cache", "pdf_text_cache.json")
if os.path.exists(pdf_cache_file):
    pdf_cache = json.load(open(pdf_cache_file, encoding="utf-8"))
    print(f"pdf_text_cache.json exists, {len(pdf_cache)} entries")
else:
    pdf_cache = {}
    print("pdf_text_cache.json does NOT exist")

# 2. Check MAZDOCK outcome 105 in scanner.db
conn = sqlite3.connect(os.path.join(BASE_DIR, "output", "scanner.db"))
cur = conn.cursor()
cur.execute("PRAGMA table_info(outcomes)")
print("outcomes columns:", [col[1] for col in cur.fetchall()])
cur.execute("SELECT * FROM outcomes WHERE id = 105")
row105 = cur.fetchone()
print(f"Outcome 105 in scanner.db: {row105}")

# Check outcome 105 flag
if row105:
    cur.execute("SELECT * FROM flags WHERE id = ?", (row105[1],))
    flag105 = cur.fetchone()
    print(f"Flag for outcome 105: {flag105}")

# 3. Inspect announcements cache for MAZDOCK, TRITURBINE, ACMESOLAR, HFCL, IKS
for sym in ["MAZDOCK", "TRITURBINE", "ACMESOLAR", "HFCL", "IKS"]:
    cache_path = os.path.join(BASE_DIR, "output", "cache", "announcements", f"{sym}.json")
    if os.path.exists(cache_path):
        data = json.load(open(cache_path, encoding="utf-8"))
        print(f"\n=== {sym} ({len(data)} announcements) ===")
        for i, row in enumerate(data):
            desc = row.get("desc", "")
            att = row.get("attchmntText", "")
            dt = row.get("an_dt", "")
            url = row.get("attchmntFile", "")
            # check if url in pdf_cache
            pdf_in_cache = url in pdf_cache
            # filter or print all
            if sym == "MAZDOCK":
                if "18-Mar-2026" in dt or "SCI" in att or "Shipping" in att:
                    print(f"[{i}] {dt} | desc: {desc} | url: {url} | in_pdf_cache: {pdf_in_cache}")
                    print(f"     attchmntText: {att}")
                    if pdf_in_cache:
                        print(f"     pdf_text: {pdf_cache[url][:200]!r}")
            elif sym == "TRITURBINE":
                if "Feb-2026" in dt or "Dividend" in att or "Meeting" in desc:
                    print(f"[{i}] {dt} | desc: {desc} | url: {url} | in_pdf_cache: {pdf_in_cache}")
                    print(f"     attchmntText: {att}")
                    if pdf_in_cache:
                        print(f"     pdf_text: {pdf_cache[url][:200]!r}")
            else:
                # ACMESOLAR, HFCL, IKS
                print(f"[{i}] {dt} | desc: {desc} | url: {url} | in_pdf_cache: {pdf_in_cache}")
                print(f"     attchmntText: {att}")
                if pdf_in_cache:
                    print(f"     pdf_text: {pdf_cache[url][:200]!r}")
