import os
import sys
import random
import sqlite3
import pandas as pd

db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output", "scanner.db")
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Query material outcomes for Flag cohort (is_control = 0)
cur.execute("""
    SELECT DISTINCT f.symbol, f.company, o.announcement_date, o.announcement_type, o.announcement_title, o.announcement_url
    FROM outcomes o
    JOIN flags f ON o.flag_id = f.id
    WHERE f.is_control = 0 AND o.is_material = 1 AND o.horizon_days = 10 AND o.announcement_title IS NOT NULL
    ORDER BY f.symbol, o.announcement_date
""")
flag_rows = [dict(r) for r in cur.fetchall()]

# Query material outcomes for Control cohort (is_control = 2)
cur.execute("""
    SELECT DISTINCT f.symbol, f.company, o.announcement_date, o.announcement_type, o.announcement_title, o.announcement_url
    FROM outcomes o
    JOIN flags f ON o.flag_id = f.id
    WHERE f.is_control = 2 AND o.is_material = 1 AND o.horizon_days = 10 AND o.announcement_title IS NOT NULL
    ORDER BY f.symbol, o.announcement_date
""")
ctrl_rows = [dict(r) for r in cur.fetchall()]

print(f"Available Flag material rows: {len(flag_rows)}, Control material rows: {len(ctrl_rows)}")

# Seeded stratified sampling (seed=42)
rng = random.Random(42)

# Sample 10 unique symbols from Flag cohort
flag_by_sym = {}
for r in flag_rows:
    flag_by_sym.setdefault(r["symbol"], []).append(r)

sampled_flag_syms = sorted(rng.sample(list(flag_by_sym.keys()), 10))
sampled_flag = [rng.choice(flag_by_sym[sym]) for sym in sampled_flag_syms]

# Sample 10 unique symbols from Control cohort
ctrl_by_sym = {}
for r in ctrl_rows:
    ctrl_by_sym.setdefault(r["symbol"], []).append(r)

sampled_ctrl_syms = sorted(rng.sample(list(ctrl_by_sym.keys()), 10))
sampled_ctrl = [rng.choice(ctrl_by_sym[sym]) for sym in sampled_ctrl_syms]

records = []
for i, r in enumerate(sampled_flag, 1):
    r["audit_id"] = i
    r["cohort"] = "Flag"
    records.append(r)

for i, r in enumerate(sampled_ctrl, 11):
    r["audit_id"] = i
    r["cohort"] = "Control"
    records.append(r)

for r in records:
    print(f"\n#{r['audit_id']} [{r['cohort']}] {r['symbol']} ({r['company']}) | Date: {r['announcement_date']} | Cat: {r['announcement_type']}")
    print(f"   Title: {r['announcement_title'][:140]}")
    print(f"   URL:   {r['announcement_url']}")
