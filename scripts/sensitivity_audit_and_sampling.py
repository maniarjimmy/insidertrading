"""
Run sensitivity analysis (3-day vs 10-day pre-move), precision audit,
and 24-month UDDiP/MTO availability sampling.
"""
import os
import sys
import math
import random
import sqlite3
from datetime import date, datetime, timedelta
from typing import Any, Dict, List
import pandas as pd
import requests
from scipy.stats import binomtest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from filings import classify_catalyst, fetch_corporate_filings
from holidays import get_next_trading_day, parse_date, is_trading_day

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output", "scanner.db")

_SYMBOL_ANNOUNCEMENTS_CACHE: Dict[str, List[Dict[str, Any]]] = {}

def get_announcements(symbol: str) -> List[Dict[str, Any]]:
    if symbol in _SYMBOL_ANNOUNCEMENTS_CACHE:
        return _SYMBOL_ANNOUNCEMENTS_CACHE[symbol]
    ann = fetch_corporate_filings(symbol, date(2026, 1, 1), date(2026, 6, 10))
    _SYMBOL_ANNOUNCEMENTS_CACHE[symbol] = ann
    return ann

def run_sensitivity():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT f.id, f.scan_date, f.symbol, f.company, f.catalyst_state, f.score,
               o.entry_price, o.forward_return
        FROM flags f
        JOIN outcomes o ON f.id = o.flag_id
        WHERE f.is_control = 0 AND o.horizon_days = 10 AND o.entry_price IS NOT NULL
        ORDER BY f.scan_date, f.id
    """)
    flags = [dict(r) for r in cur.fetchall()]

    cur.execute("""
        SELECT f.id, f.scan_date, f.symbol, f.company,
               o.entry_price, o.forward_return
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

    results = {}

    for pre_days in [3, 10]:
        pairs = []
        used_ctrl = set()

        for flag in flags:
            sdate_str = flag["scan_date"].split(" ")[0]
            flag_sym = flag["symbol"]
            scan_dt = parse_date(sdate_str)
            t_pre = scan_dt - timedelta(days=pre_days)
            t_plus_10 = get_next_trading_day(scan_dt, 10)

            # Map legacy status
            legacy_status = "news_driven" if flag.get("catalyst_state") == "CATALYST" else "unexplained"

            flag_ann = get_announcements(flag_sym)
            flag_pre_cat = False
            flag_fwd_all = False
            flag_fwd_sched = False
            flag_fwd_unsched = False

            for a in flag_ann:
                adt = a.get("dt")
                if not adt:
                    continue
                adate = adt.date() if isinstance(adt, datetime) else adt
                if t_pre <= adate <= scan_dt:
                    if a.get("is_material") == 1:
                        flag_pre_cat = True
                elif scan_dt < adate <= t_plus_10:
                    if a.get("is_material") == 1:
                        flag_fwd_all = True
                        cat = a.get("category", "")
                        if cat in ("Financial Results", "Board Meeting"):
                            flag_fwd_sched = True
                        else:
                            flag_fwd_unsched = True

            date_ctrls = ctrl_by_date.get(sdate_str, [])
            matched_c = None
            for c in date_ctrls:
                if c["id"] not in used_ctrl and c["symbol"] != flag_sym:
                    matched_c = c
                    used_ctrl.add(c["id"])
                    break
            if not matched_c and date_ctrls:
                matched_c = date_ctrls[0]
            if not matched_c:
                continue

            ctrl_sym = matched_c["symbol"]
            ctrl_ann = get_announcements(ctrl_sym)
            ctrl_pre_cat = False
            ctrl_fwd_all = False
            ctrl_fwd_sched = False
            ctrl_fwd_unsched = False

            for a in ctrl_ann:
                adt = a.get("dt")
                if not adt:
                    continue
                adate = adt.date() if isinstance(adt, datetime) else adt
                if t_pre <= adate <= scan_dt:
                    if a.get("is_material") == 1:
                        ctrl_pre_cat = True
                elif scan_dt < adate <= t_plus_10:
                    if a.get("is_material") == 1:
                        ctrl_fwd_all = True
                        cat = a.get("category", "")
                        if cat in ("Financial Results", "Board Meeting"):
                            ctrl_fwd_sched = True
                        else:
                            ctrl_fwd_unsched = True

            pairs.append({
                "id": flag["id"],
                "scan_date": sdate_str,
                "symbol": flag_sym,
                "legacy_status": legacy_status,
                "flag_pre_cat": flag_pre_cat,
                "ctrl_pre_cat": ctrl_pre_cat,
                "flag_fwd_all": flag_fwd_all,
                "ctrl_fwd_all": ctrl_fwd_all,
                "flag_fwd_sched": flag_fwd_sched,
                "ctrl_fwd_sched": ctrl_fwd_sched,
                "flag_fwd_unsched": flag_fwd_unsched,
                "ctrl_fwd_unsched": ctrl_fwd_unsched,
            })

        df = pd.DataFrame(pairs)
        clean = df[(~df["flag_pre_cat"]) & (~df["ctrl_pre_cat"])].copy()

        def calc_metrics(sub_df, f_col, c_col):
            N = len(sub_df)
            y_f = sub_df[f_col].astype(int)
            y_c = sub_df[c_col].astype(int)
            n10 = int(((y_f == 1) & (y_c == 0)).sum())
            n01 = int(((y_f == 0) & (y_c == 1)).sum())
            n11 = int(((y_f == 1) & (y_c == 1)).sum())
            n00 = int(((y_f == 0) & (y_c == 0)).sum())
            f_pos = int(y_f.sum())
            c_pos = int(y_c.sum())
            p_f = f_pos / N if N else 0
            p_c = c_pos / N if N else 0
            lift = p_f / p_c if p_c > 0 else 1.0
            odds = n10 / n01 if n01 > 0 else (float("inf") if n10 > 0 else 1.0)
            
            # McNemar chi-square
            mcnemar_stat = ((abs(n10 - n01) - 1)**2) / (n10 + n01) if (n10 + n01) > 0 else 0
            # Exact binomial sign test
            b_test = binomtest(n10, n10 + n01, 0.5) if (n10 + n01) > 0 else None
            p_val = b_test.pvalue if b_test else 1.0

            return {
                "N": N, "f_pos": f_pos, "c_pos": c_pos,
                "p_f": round(p_f * 100, 2), "p_c": round(p_c * 100, 2),
                "lift": round(lift, 2),
                "n11": n11, "n10": n10, "n01": n01, "n00": n00,
                "odds": round(odds, 2) if odds != float("inf") else "inf",
                "mcnemar_stat": round(mcnemar_stat, 2),
                "p_val": round(p_val, 4)
            }

        conf = pd.crosstab(
            df["legacy_status"],
            df["flag_pre_cat"].map({True: "Filing Catalyst", False: "Filing Unexplained"}),
            rownames=["Legacy News"],
            colnames=["Filings Pre-Move"]
        )

        results[pre_days] = {
            "total_N": len(df),
            "clean_N": len(clean),
            "conf": conf,
            "stats_all": calc_metrics(clean, "flag_fwd_all", "ctrl_fwd_all"),
            "stats_unsched": calc_metrics(clean, "flag_fwd_unsched", "ctrl_fwd_unsched"),
        }

    return results

def audit_precision_filings():
    """Select 15 filings marked material by the classifier across different symbols/dates."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT DISTINCT symbol FROM flags WHERE is_control = 0 LIMIT 40")
    symbols = [r["symbol"] for r in cur.fetchall()]

    material_filings = []
    for sym in symbols:
        ann = get_announcements(sym)
        for a in ann:
            if a.get("is_material") == 1:
                material_filings.append(a)
                if len(material_filings) >= 25:
                    break
        if len(material_filings) >= 25:
            break

    # Sample 15 distinct
    rng = random.Random(123)
    sample_15 = rng.sample(material_filings, min(15, len(material_filings)))
    return sample_15

def sample_24_month_availability():
    """Sample >= 20 random trading dates across 24 months (Nov 2024 - Nov 2026)."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "*/*"
    }

    # Generate all candidate dates
    start_date = date(2024, 11, 1)
    end_date = date(2026, 11, 15)
    cur_date = start_date

    candidates = []
    while cur_date <= end_date:
        if is_trading_day(cur_date):
            candidates.append(cur_date)
        cur_date += timedelta(days=1)

    rng = random.Random(777)
    sampled_dates = sorted(rng.sample(candidates, 24))

    results = []
    for d in sampled_dates:
        ymd = d.strftime("%Y%m%d")
        dmy = d.strftime("%d%m%Y")

        uddip_url = f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{ymd}_F_0000.csv.zip"
        mto_url = f"https://nsearchives.nseindia.com/archives/equities/mto/MTO_{dmy}.DAT"

        u_status = None
        m_status = None

        try:
            r_u = requests.head(uddip_url, headers=headers, timeout=10)
            u_status = r_u.status_code
        except Exception as e:
            u_status = f"Err: {type(e).__name__}"

        try:
            r_m = requests.head(mto_url, headers=headers, timeout=10)
            m_status = r_m.status_code
        except Exception as e:
            m_status = f"Err: {type(e).__name__}"

        results.append({
            "date": d.isoformat(),
            "uddip_url": uddip_url,
            "uddip_status": u_status,
            "mto_url": mto_url,
            "mto_status": m_status,
        })

    return results

if __name__ == "__main__":
    print("Executing sensitivity analysis...")
    sens = run_sensitivity()
    print("\n" + "="*80)
    print("SENSITIVITY ANALYSIS RESULTS")
    print("="*80)
    for days, d in sens.items():
        print(f"\n--- PRE-MOVE WINDOW: {days} DAYS ---")
        print(f"Total Flags: {d['total_N']}, Clean Unexplained Pairs: {d['clean_N']}")
        print("\nConfusion Matrix (Legacy News vs Filings):")
        print(d["conf"])
        print("\nAll Forward Material Catalysts:")
        for k, v in d["stats_all"].items():
            print(f"  {k}: {v}")
        print("\nUnscheduled-Material Catalysts Only:")
        for k, v in d["stats_unsched"].items():
            print(f"  {k}: {v}")

    print("\n" + "="*80)
    print("PRECISION AUDIT: 15 MATERIAL FILINGS")
    print("="*80)
    mat_filings = audit_precision_filings()
    for idx, f in enumerate(mat_filings, 1):
        dt_str = f.get('dt').strftime('%Y-%m-%d') if f.get('dt') else 'N/A'
        print(f"{idx}. [{f.get('symbol')}] Date: {dt_str} | Cat: {f.get('category')} | Reason: {f.get('match_reason')}")
        print(f"   Subject: {f.get('subject', '')[:100]}")
        print(f"   Attachment: {f.get('attachment_url')}")

    print("\n" + "="*80)
    print("24-MONTH AVAILABILITY SAMPLING (UDDiP & MTO)")
    print("="*80)
    samples = sample_24_month_availability()
    uddip_200 = sum(1 for s in samples if s['uddip_status'] == 200)
    mto_200 = sum(1 for s in samples if s['mto_status'] == 200)
    print(f"Total dates sampled: {len(samples)}")
    print(f"UDDiP Bhavcopy HTTP 200: {uddip_200}/{len(samples)} ({uddip_200/len(samples)*100:.1f}%)")
    print(f"MTO Delivery HTTP 200:   {mto_200}/{len(samples)} ({mto_200/len(samples)*100:.1f}%)")
    print("\nSample records:")
    for s in samples[:10]:
        print(f"  {s['date']}: UDDiP={s['uddip_status']}, MTO={s['mto_status']}")
