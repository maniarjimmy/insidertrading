"""
Export 40 New Filings for Manual Blind Labeling (Item 2a)
Draws 40 fresh filings (28 flagged group, 12 control group)
Exported to output/labeling_batch.csv WITHOUT classifier labels for blind user annotation.
"""

import json
import os
import random
import sqlite3
import pandas as pd

OUTPUT_CSV = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output", "labeling_batch.csv")
FIXTURES_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tests", "fixtures", "filings_fixtures.json")
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output", "scanner.db")


def generate_labeling_batch():
    with open(FIXTURES_FILE, "r", encoding="utf-8") as f:
        existing_fixtures = json.load(f)
    existing_texts = {x["text"][:35].lower() for x in existing_fixtures}

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 1. Candidate flagged filings (is_control = 0)
    cur.execute("""
        SELECT DISTINCT f.symbol, f.company, o.announcement_date, o.announcement_type, o.announcement_title, o.announcement_url
        FROM outcomes o
        JOIN flags f ON o.flag_id = f.id
        WHERE f.is_control = 0 AND o.announcement_title IS NOT NULL AND length(trim(o.announcement_title)) > 15
        ORDER BY f.id DESC
    """)
    flagged_rows = cur.fetchall()

    # 2. Candidate control filings (is_control IN (1, 2))
    cur.execute("""
        SELECT DISTINCT f.symbol, f.company, o.announcement_date, o.announcement_type, o.announcement_title, o.announcement_url
        FROM outcomes o
        JOIN flags f ON o.flag_id = f.id
        WHERE f.is_control IN (1, 2) AND o.announcement_title IS NOT NULL AND length(trim(o.announcement_title)) > 15
        ORDER BY f.id DESC
    """)
    control_rows = cur.fetchall()

    # Deduplicate and filter out fixtures
    def clean_pool(rows):
        seen = set()
        clean = []
        for r in rows:
            sym, comp, adt, atype, atitle, aurl = r
            k = (sym, atitle[:35].lower())
            if k[1] in existing_texts or k in seen:
                continue
            seen.add(k)
            clean.append({
                "symbol": sym,
                "company": comp,
                "date": adt,
                "desc": atype,
                "text": atitle,
                "attachment_url": aurl,
            })
        return clean

    flagged_pool = clean_pool(flagged_rows)
    control_pool = clean_pool(control_rows)

    # Deterministic sampling
    rng = random.Random(2026)
    rng.shuffle(flagged_pool)
    rng.shuffle(control_pool)

    # 28 from flagged, 12 from control = 40
    sampled_flagged = flagged_pool[:28]
    sampled_control = control_pool[:12]

    batch = []
    idx = 1
    for item in sampled_flagged:
        batch.append({
            "id": idx,
            "cohort": "FLAGGED",
            "symbol": item["symbol"],
            "company": item["company"],
            "date": item["date"],
            "desc": item["desc"],
            "text": item["text"],
            "attachment_url": item["attachment_url"],
            "user_label": "",   # Empty for blind user labeling: CATALYST / UNCLEAR / NONE
            "user_notes": "",   # Empty for user notes
        })
        idx += 1

    for item in sampled_control:
        batch.append({
            "id": idx,
            "cohort": "CONTROL",
            "symbol": item["symbol"],
            "company": item["company"],
            "date": item["date"],
            "desc": item["desc"],
            "text": item["text"],
            "attachment_url": item["attachment_url"],
            "user_label": "",
            "user_notes": "",
        })
        idx += 1

    # Shuffle the batch so the user receives a randomized sequence
    rng.shuffle(batch)
    # Re-index
    for i, b in enumerate(batch, 1):
        b["id"] = i

    df = pd.DataFrame(batch)
    os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")
    print(f"Exported {len(df)} unlabelled filings to {OUTPUT_CSV}")
    print(f"Stratification: {sum(df['cohort'] == 'FLAGGED')} FLAGGED, {sum(df['cohort'] == 'CONTROL')} CONTROL")


if __name__ == "__main__":
    generate_labeling_batch()
