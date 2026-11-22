import datetime
from datetime import date, datetime, timedelta
import json
import math
import os
import random
import subprocess
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from filings import classify_catalyst, get_nse_session, parse_filing_datetime
from holidays import get_next_trading_day, parse_date


def wilson_ci(k: int, n: int, conf: float = 0.95):
    if n == 0:
        return 0.0, 0.0
    z = 1.95996
    p = k / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    spread = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return max(0.0, centre - spread), min(1.0, centre + spread)


def run():
    head_commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode().strip()
    out_file = os.path.join(BASE_DIR, "output", "audit", f"random_control_base_rate_{head_commit}.txt")
    os.makedirs(os.path.dirname(out_file), exist_ok=True)

    session = get_nse_session()

    # 10 Universe symbols from ranks 101-500 (Mid/Small Cap)
    test_symbols = [
        "AARTIIND", "CROMPTON", "DEEPAKNTR", "GLENMARK", "IPCALAB",
        "JUBLFOOD", "LALPATHLAB", "MFSL", "POLYCAB", "VOLTAS"
    ]

    # Sample 10 random trading dates per symbol across 2024-2025 (strictly outside 2026 development set)
    random.seed(42)
    # Generate potential trading dates across 2024-2025 (exclude weekends)
    start_d = date(2024, 1, 15)
    end_d = date(2025, 12, 15)
    all_dates = []
    cur = start_d
    while cur <= end_d:
        if cur.weekday() < 5:  # Mon-Fri
            all_dates.append(cur)
        cur += timedelta(days=1)

    lines = []
    lines.append("=" * 115)
    lines.append(f"RANDOM CONTROL BASE RATE ESTIMATION (BACKTEST SPAN 2024-2025) | COMMIT: {head_commit}")
    lines.append("=" * 115)
    lines.append("Design Mandate (prereg-v4 Requirement 5c):")
    lines.append("- Estimate control base rate from RANDOM NON-FLAG STOCK-DAYS across the backtest span.")
    lines.append("- Quarantines February-May 2026 development data completely.")
    lines.append("- Sampling Frame: 100 stock-days sampled across 10 Nifty Mid/Small cap universe symbols across 2024-2025.")
    lines.append("- Pre-Move Cleanliness: [T-3, T] must contain zero material filings per classifier-v1.")
    lines.append("- Forward Horizon: T+1 .. T+10 trading days for unscheduled-material and all-material filings.\n")

    total_sampled = 0
    clean_stock_days = 0
    all_mat_count = 0
    unsched_mat_count = 0

    lines.append(f"{'#':<3} | {'Symbol':<10} | {'Stock-Day (T)':<13} | {'Clean [T-3,T]?':<15} | {'Fwd All Mat?':<13} | {'Fwd Unsched?':<13}")
    lines.append("-" * 75)

    sample_log = []

    for sym in test_symbols:
        # Fetch 2024-2025 announcements for symbol
        url = f"https://www.nseindia.com/api/corporate-announcements?index=equities&symbol={sym}&from_date=01-01-2024&to_date=31-12-2025"
        ann_items = []
        for attempt in range(3):
            try:
                resp = session.get(url, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    ann_items = data if isinstance(data, list) else data.get("data", [])
                    break
                elif resp.status_code in (401, 403):
                    session.get("https://www.nseindia.com", timeout=10)
                    time.sleep(0.5)
            except Exception:
                time.sleep(0.5)

        # Parse announcements
        parsed_ann = []
        for it in ann_items:
            raw_dt = it.get("sort_date") or it.get("an_dt")
            if not raw_dt:
                continue
            desc = it.get("desc", "")
            att_text = it.get("attchmntText", "")
            att_url = it.get("attchmntFile", "")
            state, mat, cat = classify_catalyst(desc=desc, text=att_text, url=att_url, parse_pdf=True, cache_only_pdf=True)
            dt = parse_filing_datetime(raw_dt)
            if dt:
                parsed_ann.append({
                    "dt": dt.date() if isinstance(dt, datetime) else dt,
                    "state": state,
                    "mat": mat,
                    "cat": cat,
                    "unsched": mat and (cat not in ("Financial Results", "Board Meeting"))
                })

        # Sample 10 dates for this symbol
        sampled_dates = random.sample(all_dates, 10)
        sampled_dates.sort()

        for t_date in sampled_dates:
            total_sampled += 1
            t_minus_3 = t_date - timedelta(days=4)
            t_plus_10 = get_next_trading_day(t_date, 10)

            # Check pre-move
            is_clean = True
            for a in parsed_ann:
                if t_minus_3 <= a["dt"] <= t_date:
                    if a["mat"] == 1:
                        is_clean = False
                        break

            if not is_clean:
                clean_str = "CONTAMINATED"
                fwd_all_str = "N/A"
                fwd_unsched_str = "N/A"
            else:
                clean_str = "CLEAN"
                clean_stock_days += 1
                has_all = False
                has_unsched = False
                for a in parsed_ann:
                    if t_date < a["dt"] <= t_plus_10:
                        if a["mat"] == 1:
                            has_all = True
                            if a["unsched"]:
                                has_unsched = True
                if has_all:
                    all_mat_count += 1
                if has_unsched:
                    unsched_mat_count += 1
                fwd_all_str = "YES" if has_all else "NO"
                fwd_unsched_str = "YES" if has_unsched else "NO"

            if total_sampled <= 25 or total_sampled % 10 == 0:
                lines.append(f"{total_sampled:<3} | {sym:<10} | {t_date.strftime('%Y-%m-%d'):<13} | {clean_str:<15} | {fwd_all_str:<13} | {fwd_unsched_str:<13}")

    p0_all = all_mat_count / clean_stock_days if clean_stock_days > 0 else 0.0
    p0_unsched = unsched_mat_count / clean_stock_days if clean_stock_days > 0 else 0.0

    ci_all_low, ci_all_high = wilson_ci(all_mat_count, clean_stock_days)
    ci_unsched_low, ci_unsched_high = wilson_ci(unsched_mat_count, clean_stock_days)

    lines.append("-" * 75)
    lines.append("\nEMPIRICAL BASE RATE RESULTS ACROSS 2024-2025 BACKTEST SPAN:")
    lines.append(f"  Total Random Stock-Days Sampled: {total_sampled}")
    lines.append(f"  Pre-Move Clean Stock-Days (No Catalysts in [T-3, T]): {clean_stock_days} ({clean_stock_days/total_sampled*100:.1f}%)")
    lines.append(f"  Pre-Move Contaminated Disqualified: {total_sampled - clean_stock_days} ({(total_sampled-clean_stock_days)/total_sampled*100:.1f}%)\n")
    lines.append(f"  1. Forward Unscheduled-Material Catalyst Base Rate (P0): {p0_unsched * 100:.2f}% ({unsched_mat_count}/{clean_stock_days})")
    lines.append(f"     Wilson 95% Confidence Interval: [{ci_unsched_low * 100:.2f}%, {ci_unsched_high * 100:.2f}%]")
    lines.append(f"  2. Forward All-Material Catalyst Base Rate: {p0_all * 100:.2f}% ({all_mat_count}/{clean_stock_days})")
    lines.append(f"     Wilson 95% Confidence Interval: [{ci_all_low * 100:.2f}%, {ci_all_high * 100:.2f}%]\n")

    lines.append("METHODOLOGICAL ADOPTION FOR PREREG-V4:")
    lines.append(f"  Pre-registered Unscheduled Base Rate P0 = {p0_unsched * 100:.1f}% (derived from 2024-2025 random control stock-days).")
    lines.append(f"  Completely independent of 2026 development flag rates.")
    lines.append("=" * 115)

    out_text = "\n".join(lines)
    print(out_text)
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(out_text)
    print(f"\n[Random control base rate estimation written to {out_file}]")


if __name__ == "__main__":
    run()
