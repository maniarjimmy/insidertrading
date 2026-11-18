"""
Rigorous Lift & Reclassification Engine (Item 1)
1. Reclassifies pre-move disclosures strictly BEFORE flag timestamps using Phase 2 classifier.
2. Compares unexplained flags against matched controls with no pre-scan catalyst.
3. Computes both paired (matched pairs) and unpaired statistical lift.
4. Splits outcomes into Scheduled (results, board meetings) vs Unscheduled-Material (orders, M&A, fund raising, rating, regulatory).
5. Computes cluster bootstrap confidence intervals by scan date (B=1000).
"""

from datetime import date, datetime, timedelta
import math
import os
import random
import sqlite3
import sys
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd

from filings import classify_catalyst, fetch_corporate_filings, parse_filing_datetime
from holidays import count_trading_days, get_next_trading_day, parse_date

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output", "scanner.db")

# Cache symbol announcements to avoid duplicate API requests
_SYMBOL_ANNOUNCEMENTS_CACHE: Dict[str, List[Dict[str, Any]]] = {}


def get_all_symbol_announcements(symbol: str) -> List[Dict[str, Any]]:
    """Fetch all 2026 announcements for a symbol with in-memory caching."""
    if symbol in _SYMBOL_ANNOUNCEMENTS_CACHE:
        return _SYMBOL_ANNOUNCEMENTS_CACHE[symbol]
    ann = fetch_corporate_filings(symbol, date(2026, 1, 1), date(2026, 6, 10))
    _SYMBOL_ANNOUNCEMENTS_CACHE[symbol] = ann
    return ann


def analyze_lift_methodology():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Fetch real flags with >= 10 trading days elapsed
    cur.execute("""
        SELECT f.id, f.scan_date, f.symbol, f.company, f.score, f.price_change, f.volume_ratio,
               o.entry_price, o.forward_return
        FROM flags f
        JOIN outcomes o ON f.id = o.flag_id
        WHERE f.is_control = 0 AND o.horizon_days = 10 AND o.entry_price IS NOT NULL
        ORDER BY f.scan_date, f.id
    """)
    flag_rows = [dict(r) for r in cur.fetchall()]

    # Fetch matched controls
    cur.execute("""
        SELECT f.id, f.scan_date, f.symbol, f.company,
               o.entry_price, o.forward_return
        FROM flags f
        JOIN outcomes o ON f.id = o.flag_id
        WHERE f.is_control = 2 AND o.horizon_days = 10 AND o.entry_price IS NOT NULL
        ORDER BY f.scan_date, f.id
    """)
    ctrl_rows = [dict(r) for r in cur.fetchall()]

    print(f"Loaded {len(flag_rows)} real resolved flags and {len(ctrl_rows)} matched control records.")

    # Index matched controls by scan_date
    ctrl_by_date: Dict[str, List[Dict[str, Any]]] = {}
    for c in ctrl_rows:
        sdate = c["scan_date"].split(" ")[0]
        ctrl_by_date.setdefault(sdate, []).append(c)

    # Process pairs
    pairs = []
    used_ctrl_ids = set()

    for flag in flag_rows:
        sdate_str = flag["scan_date"].split(" ")[0]
        flag_sym = flag["symbol"]
        scan_dt = parse_date(sdate_str)
        t_minus_3 = scan_dt - timedelta(days=4)
        t_plus_10 = get_next_trading_day(scan_dt, 10)

        # 1. Evaluate Flag pre-move disclosures and forward outcomes
        flag_ann = get_all_symbol_announcements(flag_sym)
        flag_pre_cat = False
        flag_fwd_all = False
        flag_fwd_scheduled = False
        flag_fwd_unscheduled = False
        flag_fwd_type = "None"

        for a in flag_ann:
            adt = a.get("dt")
            if not adt:
                continue
            adate = adt.date() if isinstance(adt, datetime) else adt

            # Pre-move check: [T-3 days, T] strictly on or before scan date
            if t_minus_3 <= adate <= scan_dt:
                if a.get("is_material") == 1:
                    flag_pre_cat = True

            # Forward outcome check: (T, T+10] strictly after scan date
            elif scan_dt < adate <= t_plus_10:
                if a.get("is_material") == 1:
                    flag_fwd_all = True
                    cat = a.get("category", "")
                    if cat in ("Financial Results", "Board Meeting"):
                        flag_fwd_scheduled = True
                    else:
                        flag_fwd_unscheduled = True
                    flag_fwd_type = cat

        # 2. Find corresponding matched control for this scan date
        date_controls = ctrl_by_date.get(sdate_str, [])
        matched_c = None
        for c in date_controls:
            if c["id"] not in used_ctrl_ids and c["symbol"] != flag_sym:
                matched_c = c
                used_ctrl_ids.add(c["id"])
                break
        if not matched_c and date_controls:
            matched_c = date_controls[0]

        if not matched_c:
            continue

        ctrl_sym = matched_c["symbol"]
        ctrl_ann = get_all_symbol_announcements(ctrl_sym)
        ctrl_pre_cat = False
        ctrl_fwd_all = False
        ctrl_fwd_scheduled = False
        ctrl_fwd_unscheduled = False
        ctrl_fwd_type = "None"

        for a in ctrl_ann:
            adt = a.get("dt")
            if not adt:
                continue
            adate = adt.date() if isinstance(adt, datetime) else adt

            if t_minus_3 <= adate <= scan_dt:
                if a.get("is_material") == 1:
                    ctrl_pre_cat = True
            elif scan_dt < adate <= t_plus_10:
                if a.get("is_material") == 1:
                    ctrl_fwd_all = True
                    cat = a.get("category", "")
                    if cat in ("Financial Results", "Board Meeting"):
                        ctrl_fwd_scheduled = True
                    else:
                        ctrl_fwd_unscheduled = True
                    ctrl_fwd_type = cat

        pairs.append({
            "scan_date": sdate_str,
            "flag_sym": flag_sym,
            "ctrl_sym": ctrl_sym,
            "flag_pre_catalyst": flag_pre_cat,
            "ctrl_pre_catalyst": ctrl_pre_cat,
            "flag_fwd_all": flag_fwd_all,
            "ctrl_fwd_all": ctrl_fwd_all,
            "flag_fwd_scheduled": flag_fwd_scheduled,
            "ctrl_fwd_scheduled": ctrl_fwd_scheduled,
            "flag_fwd_unscheduled": flag_fwd_unscheduled,
            "ctrl_fwd_unscheduled": ctrl_fwd_unscheduled,
            "flag_fwd_type": flag_fwd_type,
            "ctrl_fwd_type": ctrl_fwd_type,
        })

    pair_df = pd.DataFrame(pairs)
    print(f"Total matched pairs created: {len(pair_df)}")

    # ─────────────────────────────────────────────────────────────────────────
    # Requirement 1a & 1b: Unexplained flags vs Unexplained controls
    # ─────────────────────────────────────────────────────────────────────────
    # Flags with no pre-move catalyst strictly before scan timestamp
    unexplained_flags = pair_df[~pair_df["flag_pre_catalyst"]]
    print(f"\nUnexplained Movers (no pre-move filing catalyst): {len(unexplained_flags)} / {len(pair_df)}")

    # Truly unexplained comparison: Both flag and control had no pre-move catalyst
    clean_unexp_pairs = pair_df[(~pair_df["flag_pre_catalyst"]) & (~pair_df["ctrl_pre_catalyst"])].copy()
    print(f"Clean Unexplained Pairs (neither flag nor control had pre-move catalyst): {len(clean_unexp_pairs)}")

    # ─────────────────────────────────────────────────────────────────────────
    # Requirement 1c & 1d: Paired and Unpaired Lift by Category Split
    # ─────────────────────────────────────────────────────────────────────────
    def compute_lift_metrics(df_sample: pd.DataFrame, target_col_flag: str, target_col_ctrl: str) -> Dict[str, Any]:
        N = len(df_sample)
        if N == 0:
            return {}

        y_flag = df_sample[target_col_flag].astype(int)
        y_ctrl = df_sample[target_col_ctrl].astype(int)

        n_flag_pos = int(y_flag.sum())
        n_ctrl_pos = int(y_ctrl.sum())
        p_flag = n_flag_pos / N
        p_ctrl = n_ctrl_pos / N

        unpaired_lift = (p_flag / p_ctrl) if p_ctrl > 0 else 1.0

        # Unpaired Relative Risk 95% CI
        if n_flag_pos > 0 and n_ctrl_pos > 0:
            se_rr = math.sqrt((N - n_flag_pos)/(N * n_flag_pos) + (N - n_ctrl_pos)/(N * n_ctrl_pos))
            ci_rr_low = math.exp(math.log(unpaired_lift) - 1.96 * se_rr)
            ci_rr_high = math.exp(math.log(unpaired_lift) + 1.96 * se_rr)
        else:
            ci_rr_low, ci_rr_high = 0.0, 0.0

        # Paired Concordance / Discordance
        n11 = int(((y_flag == 1) & (y_ctrl == 1)).sum())
        n10 = int(((y_flag == 1) & (y_ctrl == 0)).sum())  # Flag yes, control no
        n01 = int(((y_flag == 0) & (y_ctrl == 1)).sum())  # Flag no, control yes
        n00 = int(((y_flag == 0) & (y_ctrl == 0)).sum())

        paired_diff = (n10 - n01) / N  # Risk difference
        paired_odds_ratio = (n10 / n01) if n01 > 0 else (float("inf") if n10 > 0 else 1.0)

        # McNemar test
        mcnemar_stat = ((abs(n10 - n01) - 1) ** 2) / (n10 + n01) if (n10 + n01) > 0 else 0.0

        return {
            "N": N,
            "flag_pos": n_flag_pos,
            "flag_precision": round(p_flag * 100.0, 2),
            "ctrl_pos": n_ctrl_pos,
            "ctrl_precision": round(p_ctrl * 100.0, 2),
            "unpaired_lift": round(unpaired_lift, 2),
            "unpaired_ci": [round(ci_rr_low, 2), round(ci_rr_high, 2)],
            "n11": n11,
            "n10": n10,
            "n01": n01,
            "n00": n00,
            "paired_diff_pct": round(paired_diff * 100.0, 2),
            "paired_odds_ratio": round(paired_odds_ratio, 2) if paired_odds_ratio != float("inf") else "inf",
            "mcnemar_stat": round(mcnemar_stat, 2),
        }

    # Compute for Clean Unexplained Pairs
    stats_all = compute_lift_metrics(clean_unexp_pairs, "flag_fwd_all", "ctrl_fwd_all")
    stats_sched = compute_lift_metrics(clean_unexp_pairs, "flag_fwd_scheduled", "ctrl_fwd_scheduled")
    stats_unsched = compute_lift_metrics(clean_unexp_pairs, "flag_fwd_unscheduled", "ctrl_fwd_unscheduled")

    # Also compute for All Unexplained Flags vs All Matched Controls (regardless of ctrl pre-cat)
    stats_unexp_vs_all_ctrl = compute_lift_metrics(unexplained_flags, "flag_fwd_all", "ctrl_fwd_all")
    stats_unsched_vs_all_ctrl = compute_lift_metrics(unexplained_flags, "flag_fwd_unscheduled", "ctrl_fwd_unscheduled")

    # ─────────────────────────────────────────────────────────────────────────
    # Requirement 1e: Cluster Bootstrap by Scan Date (B=1000)
    # ─────────────────────────────────────────────────────────────────────────
    scan_dates = clean_unexp_pairs["scan_date"].unique().tolist()
    B = 1000
    boot_lifts_all = []
    boot_lifts_unsched = []
    boot_diffs_all = []
    rng = random.Random(42)

    for _ in range(B):
        sample_dates = rng.choices(scan_dates, k=len(scan_dates))
        boot_df = pd.concat([clean_unexp_pairs[clean_unexp_pairs["scan_date"] == d] for d in sample_dates], ignore_index=True)

        if len(boot_df) == 0:
            continue

        # All material lift
        fl_all = boot_df["flag_fwd_all"].sum()
        ct_all = boot_df["ctrl_fwd_all"].sum()
        if ct_all > 0:
            boot_lifts_all.append(fl_all / ct_all)
            boot_diffs_all.append((fl_all - ct_all) / len(boot_df))

        # Unscheduled lift
        fl_uns = boot_df["flag_fwd_unscheduled"].sum()
        ct_uns = boot_df["ctrl_fwd_unscheduled"].sum()
        if ct_uns > 0:
            boot_lifts_unsched.append(fl_uns / ct_uns)

    ci_boot_lift_all = [round(np.percentile(boot_lifts_all, 2.5), 2), round(np.percentile(boot_lifts_all, 97.5), 2)] if boot_lifts_all else [0, 0]
    ci_boot_diff_all = [round(np.percentile(boot_diffs_all, 2.5) * 100, 2), round(np.percentile(boot_diffs_all, 97.5) * 100, 2)] if boot_diffs_all else [0, 0]
    ci_boot_lift_unsched = [round(np.percentile(boot_lifts_unsched, 2.5), 2), round(np.percentile(boot_lifts_unsched, 97.5), 2)] if boot_lifts_unsched else [0, 0]

    return {
        "pairs_count": len(clean_unexp_pairs),
        "unexplained_flags_count": len(unexplained_flags),
        "stats_all": stats_all,
        "stats_sched": stats_sched,
        "stats_unsched": stats_unsched,
        "stats_unexp_vs_all_ctrl": stats_unexp_vs_all_ctrl,
        "ci_boot_lift_all": ci_boot_lift_all,
        "ci_boot_diff_all": ci_boot_diff_all,
        "ci_boot_lift_unsched": ci_boot_lift_unsched,
    }


if __name__ == "__main__":
    res = analyze_lift_methodology()
    print("\n" + "=" * 75)
    print("  RIGOROUS LIFT METHODOLOGY REPORT (ITEM 1)")
    print("=" * 75)
    print(f"Clean Unexplained Pairs Evaluated: N = {res['pairs_count']}")

    print("\n1. All Forward Material Catalysts (Scheduled + Unscheduled):")
    st = res["stats_all"]
    print(f"   Flag Precision:       {st['flag_precision']}% ({st['flag_pos']}/{st['N']})")
    print(f"   Control Precision:    {st['ctrl_precision']}% ({st['ctrl_pos']}/{st['N']})")
    print(f"   Unpaired Lift:        {st['unpaired_lift']}x  (95% CI: {st['unpaired_ci']})")
    print(f"   Date-Clustered Lift:  95% Bootstrap CI: {res['ci_boot_lift_all']}")
    print(f"   Paired Discordance:   n10={st['n10']} (flag only), n01={st['n01']} (ctrl only), n11={st['n11']}, n00={st['n00']}")
    print(f"   Paired Risk Diff:     {st['paired_diff_pct']}% (95% Bootstrap CI: {res['ci_boot_diff_all']}%)")
    print(f"   Paired Odds Ratio:    {st['paired_odds_ratio']}")

    print("\n2. Scheduled Catalysts Only (Financial Results & Board Meetings):")
    st = res["stats_sched"]
    print(f"   Flag Precision:       {st['flag_precision']}% ({st['flag_pos']}/{st['N']})")
    print(f"   Control Precision:    {st['ctrl_precision']}% ({st['ctrl_pos']}/{st['N']})")
    print(f"   Lift:                 {st['unpaired_lift']}x  (Paired Odds Ratio: {st['paired_odds_ratio']})")

    print("\n3. Unscheduled-Material Catalysts Only (Orders, M&A, Fund Raise, Rating):")
    st = res["stats_unsched"]
    print(f"   Flag Precision:       {st['flag_precision']}% ({st['flag_pos']}/{st['N']})")
    print(f"   Control Precision:    {st['ctrl_precision']}% ({st['ctrl_pos']}/{st['N']})")
    print(f"   Unpaired Lift:        {st['unpaired_lift']}x  (95% CI: {st['unpaired_ci']})")
    print(f"   Date-Clustered Lift:  95% Bootstrap CI: {res['ci_boot_lift_unsched']}")
    print(f"   Paired Discordance:   n10={st['n10']} (flag only), n01={st['n01']} (ctrl only)")
    print(f"   Paired Odds Ratio:    {st['paired_odds_ratio']}")
    print("=" * 75)
