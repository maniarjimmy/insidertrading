import json
import os
import random
import sqlite3
import pandas as pd

DB_PATH = "output/scanner.db"
CACHE_DIR = "output/cache/announcements"
UNIVERSE_CSV = "data/nifty500.csv"

univ = pd.read_csv(UNIVERSE_CSV)
rank_col = "Rank" if "Rank" in univ.columns else "rank"
univ_mid_small = set(univ[(univ[rank_col] >= 210) & (univ[rank_col] <= 500)]["Symbol"])

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

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

SEED = 42
rng = random.Random(SEED)
sample_20 = rng.sample(unique_filings, 20)

for idx, item in enumerate(sample_20, 1):
    sym = item["symbol"]
    att_url = item["announcement_url"]
    cache_path = os.path.join(CACHE_DIR, f"{sym}.json")
    attchmnt_text = ""
    desc = item["announcement_type"] or ""
    
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
            
    if not attchmnt_text:
        attchmnt_text = item.get("announcement_title", "")

    cohort = "FLAG" if item["is_control"] == 0 else "CONTROL"
    print(f"ROW_{idx}: outcome_id={item['outcome_id']}, flag_id={item['flag_id']}, symbol={sym}, cohort={cohort}")
    print(f"  date={item['announcement_date']}, category={desc}")
    print(f"  url={att_url}")
    print(f"  text={attchmnt_text}")
    print()
