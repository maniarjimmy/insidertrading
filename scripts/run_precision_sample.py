import json
import os
import random
import sqlite3
import pandas as pd

DB_PATH = "output/scanner.db"
CACHE_DIR = "output/cache/announcements"
UNIVERSE_CSV = "data/nifty500.csv"

# Load universe to ensure rank 210-500
univ = pd.read_csv(UNIVERSE_CSV)
rank_col = "Rank" if "Rank" in univ.columns else "rank"
univ_mid_small = set(univ[(univ[rank_col] >= 210) & (univ[rank_col] <= 500)]["Symbol"])

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Query material outcomes from DB
cur.execute("""
    SELECT o.id AS outcome_id, o.flag_id, f.symbol, f.company, f.is_control,
           o.horizon_days, o.announcement_date, o.announcement_type,
           o.announcement_title, o.announcement_url
    FROM outcomes o
    JOIN flags f ON o.flag_id = f.id
    WHERE o.is_material = 1 AND o.announcement_url IS NOT NULL AND o.announcement_url != ''
    ORDER BY o.id
""")
rows = [dict(r) for r in cur.fetchall()]
conn.close()

# Deduplicate strictly by (symbol, announcement_url) and ensure symbol in mid/small universe
seen_urls = set()
unique_filings = []

for r in rows:
    sym = r["symbol"]
    if sym not in univ_mid_small:
        continue
    url = r["announcement_url"].strip()
    if not url or url in seen_urls:
        continue
    seen_urls.add(url)
    unique_filings.append(r)

print(f"Total material outcome rows in DB: {len(rows)}")
print(f"Unique material filings within mid/small universe (rank 210-500): {len(unique_filings)}")

SEED = 42
print(f"Seeded random sample with seed = {SEED}")
rng = random.Random(SEED)
sample_20 = rng.sample(unique_filings, 20)

results = []
for idx, item in enumerate(sample_20, 1):
    sym = item["symbol"]
    att_url = item["announcement_url"]
    cache_path = os.path.join(CACHE_DIR, f"{sym}.json")
    attchmnt_text = ""
    desc = item["announcement_type"] or ""
    
    # Try finding in cache
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                ann_list = json.load(f)
                for a in ann_list:
                    if a.get("url") == att_url or (att_url.split('/')[-1] and att_url.split('/')[-1] in a.get("url", "")):
                        attchmnt_text = a.get("text", "")
                        if not desc:
                            desc = a.get("desc", "")
                        break
        except Exception:
            pass
            
    # If not in cache or empty, fall back to announcement_title or fetch text
    if not attchmnt_text:
        attchmnt_text = item.get("announcement_title", "")

    results.append({
        "sample_num": idx,
        "outcome_id": item["outcome_id"],
        "flag_id": item["flag_id"],
        "symbol": sym,
        "company": item["company"],
        "is_control": item["is_control"],
        "announcement_date": item["announcement_date"],
        "announcement_type": desc,
        "announcement_title": item["announcement_title"],
        "announcement_url": att_url,
        "attchmnt_text": attchmnt_text,
    })

print("\n" + "="*80)
print("RAW SCRIPT RESULT: 20 MATERIAL-CLASSIFIED FILINGS (SEED = 42)")
print("="*80)
for r in results:
    cohort = "FLAG" if r["is_control"] == 0 else "CONTROL"
    print(f"\n[{r['sample_num']}] Outcome ID: {r['outcome_id']} | Flag ID: {r['flag_id']} | Cohort: {cohort}")
    print(f"    Symbol: {r['symbol']} ({r['company']})")
    print(f"    Date: {r['announcement_date']} | Category: {r['announcement_type']}")
    print(f"    Title/Headline: {r['announcement_title']}")
    print(f"    URL: {r['announcement_url']}")
    print(f"    attchmntText: {r['attchmnt_text']}")
