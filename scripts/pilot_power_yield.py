import sqlite3
import pandas as pd
import json, os
from datetime import datetime, date, timedelta

DB_PATH = "output/scanner.db"
CACHE_DIR = "output/cache/announcements"

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Check monthly counts in flags
cur.execute("""
    SELECT substr(scan_date, 1, 7) as ym, count(*)
    FROM flags
    WHERE is_control = 0
    GROUP BY ym
    ORDER BY ym
""")
print("Real flags by month:", cur.fetchall())

# Let's run a pilot on March 2026 (2026-03) or April 2026 (2026-04)
for pilot_m in ["2026-03", "2026-04"]:
    cur.execute(f"""
        SELECT f.id, f.scan_date, f.symbol, f.company, f.catalyst_state
        FROM flags f
        JOIN outcomes o ON f.id = o.flag_id
        WHERE f.is_control = 0 AND o.horizon_days = 10 AND o.entry_price IS NOT NULL
          AND f.scan_date LIKE '{pilot_m}%'
        GROUP BY f.id
        ORDER BY f.scan_date, f.id
    """)
    flags = [dict(r) for r in cur.fetchall()]

    cur.execute(f"""
        SELECT f.id, f.scan_date, f.symbol, f.company
        FROM flags f
        JOIN outcomes o ON f.id = o.flag_id
        WHERE f.is_control = 2 AND o.horizon_days = 10 AND o.entry_price IS NOT NULL
          AND f.scan_date LIKE '{pilot_m}%'
        GROUP BY f.id
        ORDER BY f.scan_date, f.id
    """)
    ctrls = [dict(r) for r in cur.fetchall()]
    
    # Load announcements cache
    def get_ann(sym):
        cp = os.path.join(CACHE_DIR, f"{sym}.json")
        if os.path.exists(cp):
            with open(cp, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    # Check retention: flag has no pre-move catalyst (3-day pre-move window [T-3, T])
    clean_flags = []
    for fl in flags:
        sdate = datetime.strptime(fl["scan_date"].split()[0], "%Y-%m-%d").date()
        ann = get_ann(fl["symbol"])
        has_pre = False
        for a in ann:
            # check date
            ds = a.get("date_str")
            if ds:
                try:
                    # Parse date
                    dt = datetime.strptime(ds.split()[0], "%d-%b-%Y").date() if "-" in ds and len(ds.split()[0]) >= 10 else None
                except Exception:
                    try:
                        dt = datetime.strptime(ds.split()[0], "%Y-%m-%d").date()
                    except Exception:
                        dt = None
                if dt and (sdate - timedelta(days=3)) <= dt <= sdate:
                    if a.get("is_material") == 1:
                        has_pre = True
                        break
        if not has_pre:
            clean_flags.append(fl)

    # Check unique controls without pre-move catalyst
    clean_ctrls = []
    used_ctrl_syms = set()
    for c in ctrls:
        if c["symbol"] in used_ctrl_syms:
            continue
        sdate = datetime.strptime(c["scan_date"].split()[0], "%Y-%m-%d").date()
        ann = get_ann(c["symbol"])
        has_pre = False
        for a in ann:
            ds = a.get("date_str")
            if ds:
                try:
                    dt = datetime.strptime(ds.split()[0], "%d-%b-%Y").date() if "-" in ds and len(ds.split()[0]) >= 10 else None
                except Exception:
                    try:
                        dt = datetime.strptime(ds.split()[0], "%Y-%m-%d").date()
                    except Exception:
                        dt = None
                if dt and (sdate - timedelta(days=3)) <= dt <= sdate:
                    if a.get("is_material") == 1:
                        has_pre = True
                        break
        if not has_pre:
            used_ctrl_syms.add(c["symbol"])
            clean_ctrls.append(c)

    print(f"\n--- Pilot Month {pilot_m} ---")
    print(f"Raw flags: {len(flags)}")
    print(f"Clean flags (no pre-move catalyst): {len(clean_flags)} ({len(clean_flags)/len(flags)*100:.1f}%)")
    print(f"Raw controls: {len(ctrls)}")
    print(f"Unique clean controls: {len(clean_ctrls)}")
    pair_yield = min(len(clean_flags), len(clean_ctrls))
    print(f"Clean paired yield: {pair_yield} pairs from {len(flags)} raw flags (Retention: {pair_yield/len(flags)*100:.1f}%)")

conn.close()
