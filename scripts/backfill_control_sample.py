"""
Historical Control Sample Backfill Script (Item 2)
Backfills a deterministic random control sample of unflagged, liquidity-eligible stocks
(ranks 210–500) for all historical scan dates, evaluates forward returns and catalysts,
and reports monthly baseline catalyst base rates and lift.
"""

from datetime import date, datetime
import logging
import os
import random
import sqlite3
import sys
from typing import Any, Dict, List, Set

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from config import DB_PATH, DEFAULT_BENCHMARK, setup_logging
from db import get_connection, init_db, upsert_flag
from tracker import evaluate_flag, get_benchmark_history
from universe import load_universe

logger = setup_logging("backfill_control")


def backfill_and_evaluate_control_sample(db_path: str = DB_PATH) -> Dict[str, Any]:
    init_db(db_path)
    universe_df = load_universe()
    if universe_df.empty:
        logger.error("Universe is empty. Aborting.")
        return {}

    all_symbols = universe_df["symbol"].tolist()
    symbol_to_meta = {
        row["symbol"]: {
            "company": row.get("company", ""),
            "industry": row.get("industry", ""),
        }
        for _, row in universe_df.iterrows()
    }

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT scan_date FROM flags WHERE is_control = 0 ORDER BY scan_date")
        scan_dates = [r[0] for r in cursor.fetchall()]

    logger.info("Found %d distinct historical scan dates for control backfill", len(scan_dates))

    control_flags_inserted = 0
    # Fixed seed for deterministic repeatability
    rng = random.Random(42)

    for idx, scan_d in enumerate(scan_dates):
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT symbol FROM flags WHERE scan_date = ? AND is_control = 0", (scan_d,))
            flagged_on_date = {r[0] for r in cursor.fetchall()}

            # Check if control sample already exists for this date
            cursor.execute("SELECT COUNT(*) FROM flags WHERE scan_date = ? AND is_control = 1", (scan_d,))
            existing_control_count = cursor.fetchone()[0]

        if existing_control_count >= 10:
            continue

        eligible_pool = [s for s in all_symbols if s not in flagged_on_date]
        sample_size = min(10, len(eligible_pool))
        # Deterministic sample per date
        date_seed = 42 + idx * 1000 + int(scan_d.replace("-", "")[:8])
        date_rng = random.Random(date_seed)
        sampled_symbols = date_rng.sample(eligible_pool, sample_size)

        for sym in sampled_symbols:
            meta = symbol_to_meta.get(sym, {})
            upsert_flag({
                "scan_date": scan_d,
                "symbol": sym,
                "company": meta.get("company", ""),
                "industry": meta.get("industry", ""),
                "score": 0.0,
                "status": "ACTIVE",
                "catalyst_state": "NONE",
                "delivery_pct": None,
                "run_type": "eod",
                "is_control": 1,
            }, db_path=db_path)
            control_flags_inserted += 1

    logger.info("Inserted %d control group flags into database", control_flags_inserted)

    # Now evaluate all control group flags
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, scan_date, symbol, status, is_control
            FROM flags
            WHERE is_control = 1 AND status = 'ACTIVE'
            ORDER BY scan_date ASC
        """)
        active_controls = [dict(r) for r in cursor.fetchall()]

    logger.info("Evaluating %d control group flags...", len(active_controls))

    if active_controls:
        earliest_scan = min(datetime.strptime(f["scan_date"].split(" ")[0], "%Y-%m-%d").date() for f in active_controls)
        bench_df = get_benchmark_history(earliest_scan, date.today())
        for flag in active_controls:
            evaluate_flag(flag, today=date.today(), benchmark_df=bench_df, db_path=db_path)

    # Compute monthly statistics
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT substr(f.scan_date, 1, 7) as month_str,
                   f.is_control,
                   COUNT(DISTINCT f.id) as total_flags,
                   SUM(CASE WHEN o.is_material = 1 THEN 1 ELSE 0 END) as material_found,
                   AVG(o.forward_return) as avg_return,
                   AVG(o.excess_return) as avg_excess
            FROM flags f
            JOIN outcomes o ON f.id = o.flag_id
            WHERE o.horizon_days = 10 AND o.entry_price IS NOT NULL
            GROUP BY month_str, f.is_control
            ORDER BY month_str ASC, f.is_control ASC
        """)
        rows = cursor.fetchall()

    monthly_summary: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        m = r["month_str"]
        ctrl = r["is_control"]
        if m not in monthly_summary:
            monthly_summary[m] = {"flagged": {}, "control": {}, "lift": 1.0}

        grp = "control" if ctrl == 1 else "flagged"
        tot = r["total_flags"]
        mat = r["material_found"]
        prec = round((mat / tot) * 100.0, 1) if tot > 0 else 0.0
        monthly_summary[m][grp] = {
            "evaluated": tot,
            "catalysts": mat,
            "precision": prec,
            "avg_return": round(r["avg_return"] or 0.0, 2),
            "avg_excess": round(r["avg_excess"] or 0.0, 2),
        }

    # Calculate monthly lift
    for m, data in monthly_summary.items():
        f_prec = data["flagged"].get("precision", 0.0)
        c_prec = data["control"].get("precision", 0.0)
        if c_prec > 0:
            data["lift"] = round(f_prec / c_prec, 2)
        else:
            data["lift"] = round(f_prec / 1.0, 2) if f_prec > 0 else 1.0

    return monthly_summary


if __name__ == "__main__":
    summary = backfill_and_evaluate_control_sample()
    print("\n" + "=" * 75)
    print("  MONTHLY BASELINE & STATISTICAL LIFT REPORT")
    print("=" * 75)
    for m, d in summary.items():
        f = d.get("flagged", {})
        c = d.get("control", {})
        print(f"\n📅 Month: {m}")
        print(f"   🔴 Flagged: {f.get('evaluated', 0)} evaluated | {f.get('catalysts', 0)} catalysts | Precision: {f.get('precision', 0.0)}% | Avg 10D Ret: {f.get('avg_return', 0.0)}%")
        print(f"   ⚪ Control: {c.get('evaluated', 0)} evaluated | {c.get('catalysts', 0)} catalysts | Base Rate:  {c.get('precision', 0.0)}% | Avg 10D Ret: {c.get('avg_return', 0.0)}%")
        print(f"   🚀 Lift vs Base Rate: {d.get('lift', 1.0)}x")
    print("=" * 75)
