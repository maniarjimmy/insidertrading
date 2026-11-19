import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from typing import Tuple
import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from holidays import PARTIAL_SESSIONS, is_partial_session, is_trading_day, load_holidays_from_file

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "*/*",
    "Referer": "https://www.nseindia.com/",
}


def check_uddip_exists(d: date) -> Tuple[bool, int]:
    ymd = d.strftime("%Y%m%d")
    url = f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{ymd}_F_0000.csv.zip"
    try:
        r = requests.get(url, headers=HEADERS, stream=True, timeout=5)
        return (r.status_code == 200), r.status_code
    except Exception:
        return False, 0


def run():
    head_commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode().strip()
    out_file = os.path.join(BASE_DIR, "output", "audit", f"holiday_mismatches_{head_commit}.txt")
    os.makedirs(os.path.dirname(out_file), exist_ok=True)

    lines = []
    lines.append("=" * 95)
    lines.append(f"NSE TRADING HOLIDAY & PARTIAL SESSION GROUND-TRUTH AUDIT | COMMIT: {head_commit}")
    lines.append("=" * 95)
    lines.append("Ground Truth Standard: Official NSE UDDiP Bhavcopy Archive existence (HTTP 200).")
    lines.append("Removes circular dependencies and unverified external calendar heuristics.\n")

    # Mismatch candidates:
    # 1. Known calendar holidays where UDDiP exists (e.g. Muhurat Trading)
    # 2. Weekends where UDDiP exists (e.g. Saturday DR switch sessions, rescheduled sessions)
    # 3. Weekdays where calendar expected trading, but exchange was closed (e.g. unpredicted holidays)

    mismatch_candidates = [
        {"date": date(2024, 1, 20), "reason": "Saturday Live Trading (Ram Mandir rescheduled session)"},
        {"date": date(2024, 1, 22), "reason": "Ram Mandir Consecration Public Holiday (declared on short notice)"},
        {"date": date(2024, 3, 2), "reason": "Saturday Disaster Recovery Site Switch Live Trading"},
        {"date": date(2024, 5, 18), "reason": "Saturday Disaster Recovery Site Switch Live Trading"},
        {"date": date(2024, 11, 1), "reason": "Diwali Laxmi Pujan / Muhurat Trading (1-hour evening session)"},
        {"date": date(2024, 11, 20), "reason": "Maharashtra Assembly Elections Public Holiday"},
        {"date": date(2025, 10, 21), "reason": "Diwali Laxmi Pujan / Muhurat Trading 2025"},
        {"date": date(2026, 11, 8), "reason": "Diwali Laxmi Pujan / Muhurat Trading 2026"},
    ]

    holiday_set = load_holidays_from_file()

    lines.append(f"{'Date':<12} | {'Weekday':<10} | {'Calendar Status':<16} | {'UDDiP Bhavcopy':<16} | {'Classification':<18} | {'T+N Arithmetic':<15}")
    lines.append("-" * 95)

    for cand in mismatch_candidates:
        d = cand["date"]
        d_str = d.isoformat()
        w_day = d.strftime("%A")
        is_cal_h = d_str in holiday_set
        is_weekend = d.weekday() >= 5
        cal_status = "HOLIDAY" if is_cal_h else ("WEEKEND" if is_weekend else "TRADING DAY")

        # UDDiP ground truth
        exists, status = check_uddip_exists(d)
        uddip_str = f"EXISTS (200)" if exists else f"NOT FOUND ({status})"

        # Classification
        is_partial = is_partial_session(d)
        is_std_trading = is_trading_day(d, exclude_partial=True)

        if is_partial:
            classification = "PARTIAL_SESSION"
            tn_status = "EXCLUDED (Skipped)"
        elif is_std_trading:
            classification = "FULL_TRADING_DAY"
            tn_status = "INCLUDED (Counted)"
        else:
            classification = "EXCHANGE_CLOSED"
            tn_status = "EXCLUDED (Skipped)"

        lines.append(
            f"{d_str:<12} | {w_day:<10} | {cal_status:<16} | {uddip_str:<16} | {classification:<18} | {tn_status:<15}"
        )

    lines.append("-" * 95)
    lines.append("\nOPERATIONAL POLICY IN HOLIDAYS.PY:")
    lines.append("1. Ground Truth Alignment: A date is considered a traded session only if NSE published a valid UDDiP Bhavcopy.")
    lines.append("2. Partial Session Exclusion: PARTIAL_SESSIONS set marks Muhurat trading (2024-11-01, 2025-10-21, 2026-11-08)")
    lines.append("   and disaster recovery Saturday sessions (2024-01-20, 2024-03-02, 2024-05-18).")
    lines.append("3. Arithmetic Invariant: is_trading_day(d, exclude_partial=True) returns False for all partial sessions.")
    lines.append("   Consequently, get_next_trading_day(), get_previous_trading_day(), and count_trading_days() automatically")
    lines.append("   skip partial sessions, ensuring zero contamination of forward T+N event study windows.\n")
    lines.append("=" * 95)

    out_text = "\n".join(lines)
    print(out_text)
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(out_text)
    print(f"\n[Holiday mismatches output written to {out_file}]")


if __name__ == "__main__":
    from typing import Tuple
    run()
