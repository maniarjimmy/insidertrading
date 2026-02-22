"""
Insider Activity Scanner — Main Orchestrator
Detects suspicious stock moves (positive price + abnormal volume + no news)
in Indian mid/small-cap stocks (market cap rank 210–500).

Usage:
    python main.py                          # Run scan now
    python main.py --min-pct 3              # Minimum 3% price change
    python main.py --min-vol-ratio 2.5      # Minimum 2.5x volume ratio
    python main.py --schedule               # Schedule daily at 2:30 PM IST
"""

import argparse
import sys
from datetime import datetime

from config import MIN_PCT_CHANGE, MIN_VOLUME_RATIO, MAX_PCT_CHANGE, SCAN_TIME


def run_scan(min_pct: float = None, max_pct: float = None,
             min_vol_ratio: float = None):
    """
    Execute the full scanning pipeline:
    1. Load stock universe (rank 210–500)
    2. Scan price & volume for all stocks
    3. Filter for positive movers with high volume
    4. Check news for flagged stocks
    5. Generate HTML + CSV reports
    """
    from universe import load_universe
    from scanner import scan_stocks, filter_movers
    from news import classify_stocks
    from report import generate_report, save_csv, append_to_master_csv

    min_pct = min_pct or MIN_PCT_CHANGE
    max_pct = max_pct or MAX_PCT_CHANGE
    min_vol_ratio = min_vol_ratio or MIN_VOLUME_RATIO
    timestamp = datetime.now()

    print("=" * 70)
    print("  🔍 INSIDER ACTIVITY SCANNER")
    print(f"  {timestamp.strftime('%d %b %Y, %I:%M %p IST')}")
    print("=" * 70)
    print()

    # ── Step 1: Load Universe ───────────────────────────────────────────
    print("─── Step 1/5: Loading Stock Universe ───")
    universe = load_universe()
    if universe.empty:
        print("[Main] No stocks in universe. Exiting.")
        return
    print()

    # ── Step 2: Scan Price & Volume ─────────────────────────────────────
    print("─── Step 2/5: Scanning Price & Volume ───")
    scan_results = scan_stocks(universe)
    if scan_results.empty:
        print("[Main] No scan data received. Check connection. Exiting.")
        return
    total_scanned = len(scan_results)
    print()

    # ── Step 3: Filter Movers ───────────────────────────────────────────
    print("─── Step 3/5: Filtering Positive Movers ───")
    movers = filter_movers(scan_results, min_pct, max_pct, min_vol_ratio)
    total_flagged = len(movers)

    if movers.empty:
        print("[Main] No stocks passed the price/volume filter today.")
        print("       Try lowering thresholds with --min-pct or --min-vol-ratio")

        # Still generate a report (empty)
        from pandas import DataFrame
        report_path = generate_report(
            DataFrame(), DataFrame(),
            total_scanned, 0, timestamp
        )
        # Append empty rows to master CSVs
        append_to_master_csv(DataFrame(), "suspicious_master", timestamp)
        append_to_master_csv(DataFrame(), "news_driven_master", timestamp)
        print(f"\n📊 Report (empty): {report_path}")
        return
    print()

    # ── Step 4: Check News ──────────────────────────────────────────────
    print("─── Step 4/5: Verifying News Coverage ───")
    suspicious, news_driven = classify_stocks(movers)
    print()

    # ── Step 5: Generate Reports ────────────────────────────────────────
    print("─── Step 5/5: Generating Reports ───")
    report_path = generate_report(
        suspicious, news_driven,
        total_scanned, total_flagged, timestamp
    )

    # Save per-run CSVs
    if not suspicious.empty:
        save_csv(suspicious, "suspicious", timestamp)
    if not news_driven.empty:
        save_csv(news_driven, "news_driven", timestamp)

    # Append to master CSVs (accumulates across runs)
    append_to_master_csv(suspicious, "suspicious_master", timestamp)
    append_to_master_csv(news_driven, "news_driven_master", timestamp)

    # ── Summary ─────────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("  📊 SCAN COMPLETE — SUMMARY")
    print("=" * 70)
    print(f"  Stocks Scanned:        {total_scanned}")
    print(f"  Price+Volume Flagged:  {total_flagged}")
    print(f"  🔴 Suspicious (no news): {len(suspicious)}")
    print(f"  🟢 News-Driven:          {len(news_driven)}")
    print(f"\n  📄 Report: {report_path}")
    print("=" * 70)

    # Print suspicious stocks to console
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
        print("[Main] Install schedule: pip install schedule")
        sys.exit(1)

    import time

    print(f"[Scheduler] Will run scan daily at {SCAN_TIME} IST")
    print(f"[Scheduler] Press Ctrl+C to stop\n")

    schedule.every().day.at(SCAN_TIME).do(run_scan)

    # Also run immediately if within market hours
    now = datetime.now()
    if 9 <= now.hour <= 16:
        print("[Scheduler] Running initial scan...")
        run_scan()

    while True:
        schedule.run_pending()
        time.sleep(30)


def main():
    parser = argparse.ArgumentParser(
        description="Insider Activity Scanner — Detect suspicious stock moves",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                         Run scan immediately
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
    args = parser.parse_args()

    if args.schedule:
        run_scheduled()
    else:
        run_scan(
            min_pct=args.min_pct,
            max_pct=args.max_pct,
            min_vol_ratio=args.min_vol_ratio
        )


if __name__ == "__main__":
    main()
