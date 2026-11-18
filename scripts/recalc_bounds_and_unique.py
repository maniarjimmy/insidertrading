import os
import sys
import json
import sqlite3
from datetime import date, datetime, timedelta
import pandas as pd
from scipy.stats import binomtest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from filings import fetch_corporate_filings, classify_catalyst, parse_filing_datetime
from holidays import get_next_trading_day, parse_date

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output", "scanner.db")
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output", "cache", "announcements")
os.makedirs(CACHE_DIR, exist_ok=True)

_MEM_CACHE = {}

def get_announcements(sym):
    if sym in _MEM_CACHE:
        return _MEM_CACHE[sym]
    cache_file = os.path.join(CACHE_DIR, f"{sym}.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                items = json.load(f)
                for item in items:
                    if item.get("date_str"):
                        item["dt"] = parse_filing_datetime(item["date_str"])
                _MEM_CACHE[sym] = items
                return items
        except Exception:
            pass

    ann = fetch_corporate_filings(sym, date(2026, 1, 1), date(2026, 6, 10))
    _MEM_CACHE[sym] = ann
    try:
        serializable = []
        for a in ann:
            c = dict(a)
            if "dt" in c:
                c["dt"] = None
            serializable.append(c)
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(serializable, f)
    except Exception:
        pass
    return ann


def evaluate_pairs(unclear_is_material: bool = False, enforce_unique_controls: bool = False):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT f.id, f.scan_date, f.symbol, f.company, f.catalyst_state
        FROM flags f
        JOIN outcomes o ON f.id = o.flag_id
        WHERE f.is_control = 0 AND o.horizon_days = 10 AND o.entry_price IS NOT NULL
        ORDER BY f.scan_date, f.id
    """)
    flags = [dict(r) for r in cur.fetchall()]

    cur.execute("""
        SELECT f.id, f.scan_date, f.symbol, f.company
        FROM flags f
        JOIN outcomes o ON f.id = o.flag_id
        WHERE f.is_control = 2 AND o.horizon_days = 10 AND o.entry_price IS NOT NULL
        ORDER BY f.scan_date, f.id
    """)
    ctrl_rows = [dict(r) for r in cur.fetchall()]

    ctrl_by_date = {}
    for c in ctrl_rows:
        sdate = c["scan_date"].split(" ")[0]
        ctrl_by_date.setdefault(sdate, []).append(c)

    used_ctrl_ids = set()
    used_unique_ctrl_syms = set()
    pairs = []

    for flag in flags:
        sdate_str = flag["scan_date"].split(" ")[0]
        flag_sym = flag["symbol"]
        scan_dt = parse_date(sdate_str)
        t_minus_3 = scan_dt - timedelta(days=4)
        t_plus_10 = get_next_trading_day(scan_dt, 10)

        # Flag filings evaluation
        flag_ann = get_announcements(flag_sym)
        flag_pre = False
        flag_fwd_all = False
        flag_fwd_unsched = False

        for a in flag_ann:
            adt = a.get("dt")
            if not adt:
                continue
            adate = adt.date() if isinstance(adt, datetime) else adt

            if unclear_is_material:
                is_mat = 1 if a.get("catalyst_state") in ("CATALYST", "UNCLEAR") else 0
            else:
                is_mat = 1 if a.get("is_material") == 1 else 0

            cat = a.get("category", "")
            is_unsched = (cat not in ("Financial Results", "Board Meeting")) if is_mat else False

            if t_minus_3 <= adate <= scan_dt:
                if is_mat:
                    flag_pre = True
            elif scan_dt < adate <= t_plus_10:
                if is_mat:
                    flag_fwd_all = True
                    if is_unsched:
                        flag_fwd_unsched = True

        # Find control
        candidate_ctrls = ctrl_by_date.get(sdate_str, [])
        matched_c = None
        for c in candidate_ctrls:
            c_sym = c["symbol"]
            if c_sym == flag_sym:
                continue
            if enforce_unique_controls:
                if c_sym not in used_unique_ctrl_syms:
                    matched_c = c
                    used_unique_ctrl_syms.add(c_sym)
                    break
            else:
                if c["id"] not in used_ctrl_ids:
                    matched_c = c
                    used_ctrl_ids.add(c["id"])
                    break

        if not matched_c and not enforce_unique_controls and candidate_ctrls:
            matched_c = candidate_ctrls[0]

        if not matched_c:
            continue

        ctrl_sym = matched_c["symbol"]
        ctrl_ann = get_announcements(ctrl_sym)
        ctrl_pre = False
        ctrl_fwd_all = False
        ctrl_fwd_unsched = False

        for a in ctrl_ann:
            adt = a.get("dt")
            if not adt:
                continue
            adate = adt.date() if isinstance(adt, datetime) else adt

            if unclear_is_material:
                is_mat = 1 if a.get("catalyst_state") in ("CATALYST", "UNCLEAR") else 0
            else:
                is_mat = 1 if a.get("is_material") == 1 else 0

            cat = a.get("category", "")
            is_unsched = (cat not in ("Financial Results", "Board Meeting")) if is_mat else False

            if t_minus_3 <= adate <= scan_dt:
                if is_mat:
                    ctrl_pre = True
            elif scan_dt < adate <= t_plus_10:
                if is_mat:
                    ctrl_fwd_all = True
                    if is_unsched:
                        ctrl_fwd_unsched = True

        pairs.append({
            "flag_sym": flag_sym,
            "ctrl_sym": ctrl_sym,
            "flag_pre": flag_pre,
            "ctrl_pre": ctrl_pre,
            "flag_fwd_all": flag_fwd_all,
            "ctrl_fwd_all": ctrl_fwd_all,
            "flag_fwd_unsched": flag_fwd_unsched,
            "ctrl_fwd_unsched": ctrl_fwd_unsched,
        })

    df = pd.DataFrame(pairs)
    clean = df[(~df["flag_pre"]) & (~df["ctrl_pre"])].copy()

    def calc(sub, f_col, c_col):
        N = len(sub)
        yf = sub[f_col].astype(int)
        yc = sub[c_col].astype(int)
        n10 = int(((yf == 1) & (yc == 0)).sum())
        n01 = int(((yf == 0) & (yc == 1)).sum())
        n11 = int(((yf == 1) & (yc == 1)).sum())
        n00 = int(((yf == 0) & (yc == 0)).sum())
        pf = yf.sum() / N if N else 0
        pc = yc.sum() / N if N else 0
        lift = pf / pc if pc > 0 else 1.0
        odds = n10 / n01 if n01 > 0 else (float("inf") if n10 > 0 else 1.0)
        b = binomtest(n10, n10 + n01, 0.5) if (n10 + n01) > 0 else None
        pval = b.pvalue if b else 1.0
        return {
            "N": N,
            "pf": round(pf * 100, 2),
            "pc": round(pc * 100, 2),
            "lift": round(lift, 2),
            "n11": n11, "n10": n10, "n01": n01, "n00": n00,
            "odds": round(odds, 2) if odds != float("inf") else "inf",
            "p_val": round(pval, 4)
        }

    return {
        "total_pairs": len(df),
        "clean_N": len(clean),
        "all_mat": calc(clean, "flag_fwd_all", "ctrl_fwd_all"),
        "unsched": calc(clean, "flag_fwd_unsched", "ctrl_fwd_unsched"),
    }


if __name__ == "__main__":
    print("=== RE-RUNNING PAIRED ANALYSIS: SENSITIVITY BOUNDS & UNIQUE CONTROLS ===", flush=True)

    # 1. Baseline: UNCLEAR as Non-Material
    b_base = evaluate_pairs(unclear_is_material=False, enforce_unique_controls=False)
    print("\n1. BASELINE (UNCLEAR as Non-Material, Per-Date Matched Controls):", flush=True)
    print(f"   Clean Pairs: N = {b_base['clean_N']}")
    print(f"   All Material:       Flag {b_base['all_mat']['pf']}% vs Ctrl {b_base['all_mat']['pc']}% | Lift {b_base['all_mat']['lift']}x | Odds {b_base['all_mat']['odds']} | n10={b_base['all_mat']['n10']}, n01={b_base['all_mat']['n01']} | p = {b_base['all_mat']['p_val']}")
    print(f"   Unscheduled Only:   Flag {b_base['unsched']['pf']}% vs Ctrl {b_base['unsched']['pc']}% | Lift {b_base['unsched']['lift']}x | Odds {b_base['unsched']['odds']} | n10={b_base['unsched']['n10']}, n01={b_base['unsched']['n01']} | p = {b_base['unsched']['p_val']}")

    # 2. Bound A: UNCLEAR as Material (Upper Bound)
    b_unclear_mat = evaluate_pairs(unclear_is_material=True, enforce_unique_controls=False)
    print("\n2. BOUND A (UNCLEAR as Material - Broad Materiality Upper Bound):", flush=True)
    print(f"   Clean Pairs: N = {b_unclear_mat['clean_N']}")
    print(f"   All Material:       Flag {b_unclear_mat['all_mat']['pf']}% vs Ctrl {b_unclear_mat['all_mat']['pc']}% | Lift {b_unclear_mat['all_mat']['lift']}x | Odds {b_unclear_mat['all_mat']['odds']} | n10={b_unclear_mat['all_mat']['n10']}, n01={b_unclear_mat['all_mat']['n01']} | p = {b_unclear_mat['all_mat']['p_val']}")
    print(f"   Unscheduled Only:   Flag {b_unclear_mat['unsched']['pf']}% vs Ctrl {b_unclear_mat['unsched']['pc']}% | Lift {b_unclear_mat['unsched']['lift']}x | Odds {b_unclear_mat['unsched']['odds']} | n10={b_unclear_mat['unsched']['n10']}, n01={b_unclear_mat['unsched']['n01']} | p = {b_unclear_mat['unsched']['p_val']}")

    # 3. Strictly Unique Controls (Without Replacement Across All Dates)
    b_unique = evaluate_pairs(unclear_is_material=False, enforce_unique_controls=True)
    print("\n3. STRICTLY UNIQUE CONTROLS (Sampled Without Replacement Across All Scan Dates):", flush=True)
    print(f"   Clean Pairs: N = {b_unique['clean_N']}")
    print(f"   All Material:       Flag {b_unique['all_mat']['pf']}% vs Ctrl {b_unique['all_mat']['pc']}% | Lift {b_unique['all_mat']['lift']}x | Odds {b_unique['all_mat']['odds']} | n10={b_unique['all_mat']['n10']}, n01={b_unique['all_mat']['n01']} | p = {b_unique['all_mat']['p_val']}")
    print(f"   Unscheduled Only:   Flag {b_unique['unsched']['pf']}% vs Ctrl {b_unique['unsched']['pc']}% | Lift {b_unique['unsched']['lift']}x | Odds {b_unique['unsched']['odds']} | n10={b_unique['unsched']['n10']}, n01={b_unique['unsched']['n01']} | p = {b_unique['unsched']['p_val']}")
