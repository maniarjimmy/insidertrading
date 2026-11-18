"""
Matched Control Group Generator and Evaluator (Item 5)
For each flagged stock on scan date T:
Samples a control stock from the unflagged universe matched on:
1. 20-day average turnover (Q1..Q5)
2. 60-day return volatility (Q1..Q5)
Evaluates forward returns (T+1..T+10) and corporate announcements.
Reports precision and lift against both random and matched controls.
"""

from datetime import date, datetime
import logging
import os
import sqlite3
import sys
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd

from config import DB_PATH, DEFAULT_BENCHMARK, setup_logging
from db import get_connection, init_db, upsert_flag
from tracker import evaluate_flag, get_benchmark_history
from universe import load_universe

logger = setup_logging("matched_control")


def build_matched_controls(db_path: str = DB_PATH) -> Dict[str, Any]:
    init_db(db_path)
    universe_df = load_universe()
    if universe_df.empty:
        logger.error("Universe empty. Aborting matched control generation.")
        return {}

    symbol_to_meta = {
        row["symbol"]: {
            "company": row.get("company", ""),
            "industry": row.get("industry", ""),
        }
        for _, row in universe_df.iterrows()
    }

    # Load cached universe price history
    cache_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "universe_history_cache.pkl")
    if not os.path.exists(cache_path):
        import yfinance as yf
        logger.info("Downloading universe price history for turnover & volatility matching...")
        tickers = universe_df["yf_symbol"].tolist()
        df = yf.download(tickers, start="2025-11-01", end="2026-06-05", progress=False)
        df.to_pickle(cache_path)
    else:
        df = pd.read_pickle(cache_path)

    close_df = df["Close"].copy()
    vol_df = df["Volume"].copy()
    close_df.columns = [c.replace(".NS", "") for c in close_df.columns]
    vol_df.columns = [c.replace(".NS", "") for c in vol_df.columns]

    turnover_df = close_df * vol_df
    ret_df = close_df.pct_change()

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, scan_date, symbol, company, current_price, avg_volume_20d
            FROM flags
            WHERE is_control = 0
            ORDER BY scan_date ASC, id ASC
        """)
        flag_rows = cursor.fetchall()

    logger.info("Matching %d historical flags to quintile-matched controls...", len(flag_rows))

    inserted_matches = 0
    matched_flags_to_eval = []

    for f in flag_rows:
        fid = f["id"]
        sdate = f["scan_date"].split(" ")[0]
        sym = f["symbol"]

        # Check if matched control already exists for this flag date and symbol
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM flags
                WHERE scan_date = ? AND is_control = 2
            """, (sdate,))
            existing_count = cursor.fetchone()[0]

        ts = pd.to_datetime(sdate)
        avail_dates = [d for d in close_df.index if d <= ts]
        if not avail_dates or len(avail_dates) < 20:
            continue
        idx = close_df.index.get_loc(avail_dates[-1])

        t20 = turnover_df.iloc[max(0, idx - 19) : idx + 1].mean().dropna()
        v_window = ret_df.iloc[max(0, idx - 59) : idx + 1]
        v60 = (v_window.std() * np.sqrt(252)).dropna()

        common_syms = t20.index.intersection(v60.index)
        if len(common_syms) < 20:
            continue

        # Get flagged stocks on this date to exclude them from control candidate pool
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT symbol FROM flags WHERE scan_date = ? AND is_control = 0", (sdate,))
            flagged_on_date = {r[0] for r in cursor.fetchall()}

        try:
            t_quintiles = pd.qcut(t20.loc[common_syms], 5, labels=[1, 2, 3, 4, 5])
            v_quintiles = pd.qcut(v60.loc[common_syms], 5, labels=[1, 2, 3, 4, 5])
        except Exception:
            continue

        if sym in t_quintiles.index and sym in v_quintiles.index:
            flag_tq = t_quintiles[sym]
            flag_vq = v_quintiles[sym]
            target_t = t20[sym]
            target_v = v60[sym]
        else:
            # Fallback if flag itself is missing from cache
            flag_tq = 3
            flag_vq = 3
            target_t = t20.median()
            target_v = v60.median()

        # Candidates in same quintile cell
        candidates = [
            s for s in common_syms
            if s not in flagged_on_date and t_quintiles[s] == flag_tq and v_quintiles[s] == flag_vq
        ]
        if not candidates:
            # Relax to adjacent quintiles (+/- 1)
            candidates = [
                s for s in common_syms
                if s not in flagged_on_date
                and abs(t_quintiles[s] - flag_tq) <= 1
                and abs(v_quintiles[s] - flag_vq) <= 1
            ]
        if not candidates:
            candidates = [s for s in common_syms if s not in flagged_on_date]

        t_std = t20.std() or 1.0
        v_std = v60.std() or 1.0
        best_match = min(
            candidates,
            key=lambda s: ((t20[s] - target_t) / t_std) ** 2 + ((v60[s] - target_v) / v_std) ** 2,
        )

        meta = symbol_to_meta.get(best_match, {})
        match_id = upsert_flag({
            "scan_date": sdate,
            "symbol": best_match,
            "company": meta.get("company", ""),
            "industry": meta.get("industry", ""),
            "score": 0.0,
            "status": "ACTIVE",
            "catalyst_state": "NONE",
            "delivery_pct": None,
            "run_type": "matched_control",
            "is_control": 2,  # 2 represents matched control
        }, db_path=db_path)
        inserted_matches += 1

    logger.info("Upserted %d matched control flags", inserted_matches)

    # Evaluate matched controls
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, scan_date, symbol, status, is_control
            FROM flags
            WHERE is_control = 2 AND status = 'ACTIVE'
            ORDER BY scan_date ASC
        """)
        active_matched = [dict(r) for r in cursor.fetchall()]

    logger.info("Evaluating %d active matched controls...", len(active_matched))
    if active_matched:
        earliest_scan = min(datetime.strptime(f["scan_date"].split(" ")[0], "%Y-%m-%d").date() for f in active_matched)
        bench_df = get_benchmark_history(earliest_scan, date.today())
        for flag in active_matched:
            evaluate_flag(flag, today=date.today(), benchmark_df=bench_df, db_path=db_path)

    # Compute comparative stats
    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        # 1. Flagged precision (all vs unexplained)
        cursor.execute("""
            SELECT f.id, f.catalyst_state, MAX(o.is_material), AVG(o.forward_return)
            FROM flags f
            JOIN outcomes o ON f.id = o.flag_id
            WHERE f.is_control = 0 AND o.horizon_days = 10 AND o.entry_price IS NOT NULL
            GROUP BY f.id
        """)
        flag_data = cursor.fetchall()

        # 2. Random controls (is_control = 1)
        cursor.execute("""
            SELECT f.id, MAX(o.is_material), AVG(o.forward_return)
            FROM flags f
            JOIN outcomes o ON f.id = o.flag_id
            WHERE f.is_control = 1 AND o.horizon_days = 10 AND o.entry_price IS NOT NULL
            GROUP BY f.id
        """)
        random_ctrl_data = cursor.fetchall()

        # 3. Matched controls (is_control = 2)
        cursor.execute("""
            SELECT f.id, MAX(o.is_material), AVG(o.forward_return)
            FROM flags f
            JOIN outcomes o ON f.id = o.flag_id
            WHERE f.is_control = 2 AND o.horizon_days = 10 AND o.entry_price IS NOT NULL
            GROUP BY f.id
        """)
        matched_ctrl_data = cursor.fetchall()

    n_flag = len(flag_data)
    mat_flag = sum(1 for r in flag_data if r[2] == 1)
    p_flag = (mat_flag / n_flag * 100.0) if n_flag > 0 else 0.0

    # Unexplained flags only
    unexp_data = [r for r in flag_data if r[1] != "CATALYST"]
    n_unexp = len(unexp_data)
    mat_unexp = sum(1 for r in unexp_data if r[2] == 1)
    p_unexp = (mat_unexp / n_unexp * 100.0) if n_unexp > 0 else 0.0

    n_rand = len(random_ctrl_data)
    mat_rand = sum(1 for r in random_ctrl_data if r[1] == 1)
    p_rand = (mat_rand / n_rand * 100.0) if n_rand > 0 else 0.0

    n_match = len(matched_ctrl_data)
    mat_match = sum(1 for r in matched_ctrl_data if r[1] == 1)
    p_match = (mat_match / n_match * 100.0) if n_match > 0 else 0.0

    lift_rand_all = round(p_flag / p_rand, 2) if p_rand > 0 else 1.0
    lift_match_all = round(p_flag / p_match, 2) if p_match > 0 else 1.0

    lift_rand_unexp = round(p_unexp / p_rand, 2) if p_rand > 0 else 1.0
    lift_match_unexp = round(p_unexp / p_match, 2) if p_match > 0 else 1.0

    results = {
        "all_flags": {"n": n_flag, "catalysts": mat_flag, "precision": round(p_flag, 2)},
        "unexplained_flags": {"n": n_unexp, "catalysts": mat_unexp, "precision": round(p_unexp, 2)},
        "random_control": {"n": n_rand, "catalysts": mat_rand, "precision": round(p_rand, 2)},
        "matched_control": {"n": n_match, "catalysts": mat_match, "precision": round(p_match, 2)},
        "lift_all_vs_random": lift_rand_all,
        "lift_all_vs_matched": lift_match_all,
        "lift_unexplained_vs_random": lift_rand_unexp,
        "lift_unexplained_vs_matched": lift_match_unexp,
    }

    logger.info("Matched Control Evaluation Complete: %s", results)
    return results


if __name__ == "__main__":
    res = build_matched_controls()
    print("\n" + "=" * 60)
    print("  CONTROL GROUP COMPARISON: RANDOM VS MATCHED CONTROLS")
    print("=" * 60)
    print(f"All Flags (n={res['all_flags']['n']}): Precision = {res['all_flags']['precision']}%")
    print(f"Unexplained Flags (n={res['unexplained_flags']['n']}): Precision = {res['unexplained_flags']['precision']}%")
    print(f"Random Control (n={res['random_control']['n']}): Precision = {res['random_control']['precision']}%")
    print(f"Matched Control (n={res['matched_control']['n']}): Precision = {res['matched_control']['precision']}%")
    print("-" * 60)
    print(f"Lift (All Flags vs Random Control):   {res['lift_all_vs_random']}x")
    print(f"Lift (All Flags vs Matched Control):  {res['lift_all_vs_matched']}x")
    print(f"Lift (Unexplained vs Random Control): {res['lift_unexplained_vs_random']}x")
    print(f"Lift (Unexplained vs Matched Control):{res['lift_unexplained_vs_matched']}x")
    print("=" * 60)
