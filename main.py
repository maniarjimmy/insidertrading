"""
Insider Activity Scanner — Main Orchestrator (Phase 1)
Detects suspicious stock moves (positive price + abnormal volume + no news)
in Indian mid/small-cap stocks (market cap rank 210–500), tracks outcomes,
evaluates catalyst precision, and persists data to SQLite.

Usage:
    python main.py                          # Run scan now
    python main.py --track                  # Run outcome tracker (T+1..T+10 evaluation)
    python main.py --min-pct 3              # Minimum 3% price change
    python main.py --min-vol-ratio 2.5      # Minimum 2.5x volume ratio
    python main.py --schedule               # Schedule daily at 2:30 PM IST
"""

import argparse
from datetime import datetime
import logging
import sys
from typing import Optional

# Ensure utf-8 encoding on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

from config import (
    CONTROL_SAMPLE_SIZE,
    MAX_PCT_CHANGE,
    MIN_PCT_CHANGE,
    MIN_VOLUME_RATIO,
    SCAN_TIME,
    setup_logging,
)
from db import (
    export_db_to_csv,
    export_db_to_sql,
    init_db,
    log_run,
    upsert_flag,
)
from tracker import run_tracker

logger = setup_logging("main")


def compute_heuristic_score(vol_ratio: float, pct_change: float) -> float:
    """Compute normalized score (0-100) based on volume ratio and price change."""
    try:
        vr = float(vol_ratio or 1.0)
        pc = float(pct_change or 0.0)
        vr_score = min(50.0, max(0.0, (vr - 2.0) / 8.0 * 50.0))
        pc_score = min(50.0, max(0.0, (pc - 4.0) / 11.0 * 50.0))
        return round(vr_score + pc_score, 1)
    except Exception:
        return 50.0


def run_scan(min_pct: Optional[float] = None,
             max_pct: Optional[float] = None,
             min_vol_ratio: Optional[float] = None) -> Optional[str]:
    """
    Execute the full scanning pipeline:
    1. Load stock universe (rank 210–500)
    2. Scan price & volume for all stocks
    3. Filter for positive movers with high volume
    4. Check news for flagged stocks
    5. Ingest into SQLite database with control group sample
    6. Generate HTML + CSV reports & diffable SQL dump
    """
    from pandas import DataFrame
    from universe import load_universe
    from scanner import scan_stocks, filter_movers
    from news import classify_stocks
    from report import generate_report, save_csv, append_to_master_csv

    start_time = datetime.now()
    min_pct = min_pct if min_pct is not None else MIN_PCT_CHANGE
    max_pct = max_pct if max_pct is not None else MAX_PCT_CHANGE
    min_vol_ratio = min_vol_ratio if min_vol_ratio is not None else MIN_VOLUME_RATIO
    timestamp = datetime.now()
    scan_date_str = timestamp.strftime("%Y-%m-%d")

    # Initialize database
    init_db()

    print("=" * 70)
    print("  🔍 INSIDER ACTIVITY SCANNER")
    print(f"  {timestamp.strftime('%d %b %Y, %I:%M %p IST')}")
    print("=" * 70)
    print()

    # ── Step 1: Load Universe ───────────────────────────────────────────
    print("─── Step 1/5: Loading Stock Universe ───")
    universe = load_universe()
    if universe.empty:
        logger.error("No stocks in universe. Exiting.")
        return None
    print()

    # ── Step 2: Scan Price & Volume ─────────────────────────────────────
    print("─── Step 2/5: Scanning Price & Volume ───")
    scan_results = scan_stocks(universe)
    if scan_results.empty:
        logger.error("No scan data received. Check connection. Exiting.")
        log_run("scan", "yfinance", (datetime.now() - start_time).total_seconds(), 0, 0, "FAILURE", "No scan data")
        return None
    total_scanned = len(scan_results)
    print()

    # ── Step 3: Filter Movers ───────────────────────────────────────────
    print("─── Step 3/5: Filtering Positive Movers ───")
    movers = filter_movers(scan_results, min_pct, max_pct, min_vol_ratio)
    total_flagged = len(movers)

    if movers.empty:
        print("[Main] No stocks passed the price/volume filter today.")
        print("       Try lowering thresholds with --min-pct or --min-vol-ratio")

        report_path = generate_report(
            DataFrame(), DataFrame(),
            total_scanned, 0, timestamp
        )
        append_to_master_csv(DataFrame(), "suspicious_master", timestamp)
        append_to_master_csv(DataFrame(), "news_driven_master", timestamp)
        export_db_to_sql()
        export_db_to_csv()

        runtime = (datetime.now() - start_time).total_seconds()
        log_run("scan", "yfinance", runtime, total_scanned, 0, "SUCCESS")
        print(f"\n📊 Report (empty): {report_path}")
        return report_path
    print()

    # ── Step 4: Check News ──────────────────────────────────────────────
    print("─── Step 4/5: Verifying News Coverage ───")
    suspicious, news_driven = classify_stocks(movers)
    print()

    # ── Step 5: Database Persistence & Control Group ────────────────────
    flagged_symbols = set(movers["symbol"].tolist())
    unflagged_pool = scan_results[~scan_results["symbol"].isin(flagged_symbols)]

    # 1. Upsert suspicious flags (catalyst_state = NONE or UNCLEAR)
    for _, row in suspicious.iterrows():
        classification = str(row.get("classification", "")).strip().lower()
        cat_state = "UNCLEAR" if classification == "generic_only" else "NONE"
        score = compute_heuristic_score(row.get("volume_ratio", 1.0), row.get("pct_change", 0.0))
        upsert_flag({
            "scan_date": scan_date_str,
            "symbol": row["symbol"],
            "company": row.get("company", ""),
            "industry": row.get("industry", ""),
            "current_price": float(row.get("current_price", 0.0)),
            "prev_close": float(row.get("prev_close", 0.0)),
            "price_change": float(row.get("pct_change", 0.0)),
            "current_volume": int(row.get("current_volume", 0)),
            "avg_volume_20d": float(row.get("avg_volume_20d", 0.0)),
            "volume_ratio": float(row.get("volume_ratio", 0.0)),
            "score": score,
            "status": "ACTIVE",
            "catalyst_state": cat_state,
            "delivery_pct": None,
            "run_type": "eod",
            "is_control": 0,
        })

    # 2. Upsert news-driven flags (catalyst_state = CATALYST)
    for _, row in news_driven.iterrows():
        score = compute_heuristic_score(row.get("volume_ratio", 1.0), row.get("pct_change", 0.0))
        upsert_flag({
            "scan_date": scan_date_str,
            "symbol": row["symbol"],
            "company": row.get("company", ""),
            "industry": row.get("industry", ""),
            "current_price": float(row.get("current_price", 0.0)),
            "prev_close": float(row.get("prev_close", 0.0)),
            "price_change": float(row.get("pct_change", 0.0)),
            "current_volume": int(row.get("current_volume", 0)),
            "avg_volume_20d": float(row.get("avg_volume_20d", 0.0)),
            "volume_ratio": float(row.get("volume_ratio", 0.0)),
            "score": score,
            "status": "ACTIVE",
            "catalyst_state": "CATALYST",
            "delivery_pct": None,
            "run_type": "eod",
            "is_control": 0,
        })

    # 3. Sample and upsert unflagged control group (is_control = 1)
    if not unflagged_pool.empty:
        n_sample = min(CONTROL_SAMPLE_SIZE, len(unflagged_pool))
        control_sample = unflagged_pool.sample(n=n_sample, random_state=int(timestamp.timestamp()) % 100000)
        for _, row in control_sample.iterrows():
            upsert_flag({
                "scan_date": scan_date_str,
                "symbol": row["symbol"],
                "company": row.get("company", ""),
                "industry": row.get("industry", ""),
                "current_price": float(row.get("current_price", 0.0)) if pd.notnull(row.get("current_price")) else None,
                "prev_close": float(row.get("prev_close", 0.0)) if pd.notnull(row.get("prev_close")) else None,
                "price_change": float(row.get("pct_change", 0.0)) if pd.notnull(row.get("pct_change")) else 0.0,
                "current_volume": int(row.get("current_volume", 0)) if pd.notnull(row.get("current_volume")) else 0,
                "avg_volume_20d": float(row.get("avg_volume_20d", 0.0)) if pd.notnull(row.get("avg_volume_20d")) else 0.0,
                "volume_ratio": float(row.get("volume_ratio", 0.0)) if pd.notnull(row.get("volume_ratio")) else 0.0,
                "score": 0.0,
                "status": "ACTIVE",
                "catalyst_state": "NONE",
                "delivery_pct": None,
                "run_type": "eod",
                "is_control": 1,
            })
        logger.info("Logged %d random control group stocks into database", n_sample)

    # ── Step 6: Generate Reports & Exports ──────────────────────────────
    print("─── Step 5/5: Generating Reports & Master Exports ───")
    report_path = generate_report(
        suspicious, news_driven,
        total_scanned, total_flagged, timestamp
    )

    # Per-run CSVs (backward-compatible)
    if not suspicious.empty:
        save_csv(suspicious, "suspicious", timestamp)
    if not news_driven.empty:
        save_csv(news_driven, "news_driven", timestamp)

    # Append to master CSVs (backward-compatible)
    append_to_master_csv(suspicious, "suspicious_master", timestamp)
    append_to_master_csv(news_driven, "news_driven_master", timestamp)

    # Export database text dump and updated CSVs
    export_db_to_sql()
    export_db_to_csv()

    runtime = (datetime.now() - start_time).total_seconds()
    log_run("scan", "yfinance", runtime, total_scanned, total_flagged, "SUCCESS")

    # ── Summary ─────────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("  📊 SCAN COMPLETE — SUMMARY")
    print("=" * 70)
    print(f"  Stocks Scanned:        {total_scanned}")
    print(f"  Price+Volume Flagged:  {total_flagged}")
    print(f"  🔴 Suspicious (no news): {len(suspicious)}")
    print(f"  🟢 News-Driven:          {len(news_driven)}")
    print(f"  💾 Database:             output/scanner.db (updated)")
    print(f"  📄 Report:               {report_path}")
    print("=" * 70)

    if not suspicious.empty:
        print("\n  🔴 SUSPICIOUS STOCKS — POTENTIAL INSIDER ACTIVITY:")
        print("  " + "─" * 60)
        for _, row in suspicious.iterrows():
            print(f"    {row['symbol']:15s} │ +{row['pct_change']:5.1f}% │ "
                  f"{row['volume_ratio']:5.1f}x vol │ ₹{row['current_price']:>8.2f} │ "
                  f"{row['company']}")
        print()

    return report_path


def run_scheduled():
    """Run the scanner on a daily schedule at SCAN_TIME IST."""
    try:
        import schedule
    except ImportError:
        logger.error("Install schedule: pip install schedule")
        sys.exit(1)

    import time
    from holidays import is_trading_day

    print(f"[Scheduler] Will run scan daily at {SCAN_TIME} IST (skipping market holidays)")
    print(f"[Scheduler] Press Ctrl+C to stop\n")

    def scheduled_job():
        today = datetime.now().date()
        if not is_trading_day(today):
            logger.info("Today (%s) is an NSE market holiday or weekend. Skipping scan.", today)
            return
        logger.info("Triggering scheduled insider scan...")
        run_scan()
        logger.info("Triggering scheduled outcome tracking...")
        run_tracker()

    schedule.every().day.at(SCAN_TIME).do(scheduled_job)

    # Initial check if within market hours
    now = datetime.now()
    if 9 <= now.hour <= 16 and is_trading_day(now.date()):
        print("[Scheduler] Running initial scan...")
        scheduled_job()

    while True:
        schedule.run_pending()
        time.sleep(30)


def main():
    parser = argparse.ArgumentParser(
        description="Insider Activity Scanner — Detect suspicious stock moves & track outcomes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                         Run scan immediately
  python main.py --track                 Run outcome tracker for T+1..T+10 evaluations
  python main.py --min-pct 3             Raise minimum price change to 3%
  python main.py --min-vol-ratio 3       Raise minimum volume ratio to 3x
  python main.py --schedule              Schedule daily at 2:30 PM IST
        """
    )
    parser.add_argument("--min-pct", type=float, default=None,
                        help=f"Minimum price change %% (default: {MIN_PCT_CHANGE})")
    parser.add_argument("--max-pct", type=float, default=None,
                        help=f"Maximum price change %% (default: {MAX_PCT_CHANGE})")
    parser.add_argument("--min-vol-ratio", type=float, default=None,
                        help=f"Minimum volume ratio (default: {MIN_VOLUME_RATIO})")
    parser.add_argument("--schedule", action="store_true",
                        help="Schedule daily at 2:30 PM IST")
    parser.add_argument("--track", action="store_true",
                        help="Run outcome tracker job (evaluate T+1..T+10 returns & catalysts)")
    args = parser.parse_args()

    if args.track:
        run_tracker()
    elif args.schedule:
        run_scheduled()
    else:
        run_scan(
            min_pct=args.min_pct,
            max_pct=args.max_pct,
            min_vol_ratio=args.min_vol_ratio
        )


if __name__ == "__main__":
    main()
