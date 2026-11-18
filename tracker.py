"""
Outcome Tracker Module (Phase 1 Upgraded)
Evaluates flagged and control stocks over T+1 through T+10 trading days:
- Measures forward return from Next-Day Open (T+1 Open) to T+N Close
- Computes excess return vs. benchmark (Nifty Midcap 150 / Nifty 500)
- Detects corporate filings published strictly AFTER the flag timestamp (pre-move filings excluded)
- Distinguishes material corporate filings from routine disclosures
- Tracks unflagged control sample to compute statistical lift
"""

from datetime import date, datetime, timedelta
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests
import yfinance as yf

from config import (
    BENCHMARK_TICKERS,
    CONTROL_SAMPLE_SIZE,
    DB_PATH,
    DEFAULT_BENCHMARK,
    MATERIAL_ANNOUNCEMENT_KEYWORDS,
    REQUEST_BACKOFF_FACTOR,
    REQUEST_MAX_RETRIES,
    REQUEST_TIMEOUT,
    ROUTINE_ANNOUNCEMENT_KEYWORDS,
    TRACKING_HORIZONS,
    TRACKING_MAX_DAYS,
    TRACKING_MIN_DAYS,
    setup_logging,
)
from db import (
    export_db_to_csv,
    export_db_to_sql,
    fetch_sources_last_modified,
    get_active_flags,
    get_hit_rate_stats,
    log_run,
    mark_flag_status,
    upsert_outcome,
)
from holidays import (
    count_trading_days,
    get_next_trading_day,
    parse_date,
    sync_holidays_from_api,
)

logger = setup_logging("tracker")

# In-memory caches to avoid duplicate network calls within a run
_PRICE_HISTORY_CACHE: Dict[str, pd.DataFrame] = {}
_ANNOUNCEMENTS_CACHE: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = {}


def parse_flag_timestamp(scan_date_str: str) -> datetime:
    """
    Parse a flag's scan_date string into a datetime object.
    If no time is present, defaults to 14:30:00 (scan time).
    """
    s = str(scan_date_str).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt)
            if fmt == "%Y-%m-%d":
                return dt.replace(hour=14, minute=30, second=0)
            return dt
        except ValueError:
            continue
    d = parse_date(s)
    return datetime.combine(d, datetime.min.time()).replace(hour=14, minute=30)


def parse_announcement_dt(raw_val: Any) -> Optional[datetime]:
    """
    Parse varied announcement datetime formats from NSE and BSE APIs.
    Examples:
      - '18-Nov-2026 14:51:08'
      - '2026-11-18 14:51:08'
      - '2026-11-18T13:51:56.907'
      - '18112026145108'
    """
    if not raw_val or not isinstance(raw_val, str):
        return None
    val = raw_val.strip()
    if not val or val.lower() == "none":
        return None

    # Handle ISO with T and fractional seconds
    if "t" in val.lower():
        val = val.split(".")[0].replace("T", " ")

    formats = (
        "%d-%b-%Y %H:%M:%S",
        "%d-%b-%Y %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%Y-%m-%d",
        "%d-%b-%Y",
    )
    for fmt in formats:
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            continue

    # Handle compact format: DDMMYYYYHHMMSS
    if re.match(r"^\d{14}$", val):
        try:
            return datetime.strptime(val, "%d%m%Y%H%M%S")
        except ValueError:
            pass

    return None


def fetch_price_history(symbol: str, start_date: date, end_date: date) -> pd.DataFrame:
    """Fetch daily OHLCV history from yfinance with retry and caching."""
    cache_key = f"{symbol}:{start_date.isoformat()}:{end_date.isoformat()}"
    if cache_key in _PRICE_HISTORY_CACHE:
        return _PRICE_HISTORY_CACHE[cache_key]

    yf_ticker = symbol if symbol.startswith("^") else (symbol if symbol.endswith(".NS") else f"{symbol}.NS")
    fetch_start = (start_date - timedelta(days=5)).strftime("%Y-%m-%d")
    fetch_end = (end_date + timedelta(days=5)).strftime("%Y-%m-%d")

    for attempt in range(1, REQUEST_MAX_RETRIES + 1):
        try:
            ticker = yf.Ticker(yf_ticker)
            df = ticker.history(start=fetch_start, end=fetch_end, auto_adjust=False)
            if not df.empty:
                df.index = [pd.to_datetime(idx).date() for idx in df.index]
                _PRICE_HISTORY_CACHE[cache_key] = df
                return df
        except Exception as exc:
            logger.debug("Attempt %d to fetch price for %s failed: %s", attempt, yf_ticker, exc)
            time.sleep(REQUEST_BACKOFF_FACTOR ** attempt)

    return pd.DataFrame()


def get_benchmark_history(start_date: date, end_date: date) -> pd.DataFrame:
    """Fetch benchmark history using primary ticker or fallbacks."""
    for ticker_sym in BENCHMARK_TICKERS:
        df = fetch_price_history(ticker_sym, start_date, end_date)
        if not df.empty:
            return df
    logger.warning("Failed to fetch price history for benchmark tickers: %s", BENCHMARK_TICKERS)
    return pd.DataFrame()


def fetch_corporate_announcements(symbol: str, from_date: date, to_date: date) -> List[Dict[str, Any]]:
    """
    Fetch corporate announcements for a symbol over a date range from NSE,
    with BSE fallback and in-memory caching.
    """
    from_str = from_date.strftime("%d-%m-%Y")
    to_str = to_date.strftime("%d-%m-%Y")
    cache_key = (symbol, from_str, to_str)
    if cache_key in _ANNOUNCEMENTS_CACHE:
        return _ANNOUNCEMENTS_CACHE[cache_key]

    url = (
        f"https://www.nseindia.com/api/corporate-announcements?"
        f"index=equities&symbol={symbol}&from_date={from_str}&to_date={to_str}"
    )
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/",
    }
    session = requests.Session()
    session.headers.update(headers)

    for attempt in range(1, REQUEST_MAX_RETRIES + 1):
        try:
            session.get("https://www.nseindia.com", timeout=REQUEST_TIMEOUT)
            resp = session.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                items = data if isinstance(data, list) else data.get("data", [])
                announcements = []
                for item in items:
                    raw_dt = item.get("sort_date") or item.get("an_dt") or item.get("exchdisstime")
                    announcements.append({
                        "date_str": raw_dt,
                        "dt": parse_announcement_dt(raw_dt),
                        "subject": item.get("desc", ""),
                        "details": item.get("attchmntText", ""),
                        "url": item.get("attchmntFile", ""),
                    })
                _ANNOUNCEMENTS_CACHE[cache_key] = announcements
                return announcements
        except Exception as exc:
            logger.debug("Attempt %d fetching announcements for %s failed: %s", attempt, symbol, exc)
            time.sleep(REQUEST_BACKOFF_FACTOR ** attempt)

    _ANNOUNCEMENTS_CACHE[cache_key] = []
    return []


def classify_announcement(title: str, details: str = "") -> Tuple[int, str]:
    """
    Classify whether an announcement is material (1) or routine (0).
    Returns (is_material, matched_category).
    """
    combined = f"{title} {details}".lower()

    # Check routine first
    is_routine = any(kw in combined for kw in ROUTINE_ANNOUNCEMENT_KEYWORDS)

    # Check material
    for kw in MATERIAL_ANNOUNCEMENT_KEYWORDS:
        if kw in combined:
            return (1, kw.title())

    if is_routine:
        return (0, "Routine Disclosure")

    return (0, "General Intimation")


def evaluate_flag(flag: Dict[str, Any],
                  today: Optional[date] = None,
                  benchmark_df: Optional[pd.DataFrame] = None,
                  db_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Evaluate forward returns and announcements for a single flag across horizons T+1..T+10.
    Ensures:
      1. Flags with < 10 trading days elapsed STAY ACTIVE.
      2. Only horizons with actual trading days elapsed and valid prices are recorded.
      3. Only announcements published strictly AFTER the flag timestamp are counted as outcomes.
    """
    flag_id = flag["id"]
    symbol = flag["symbol"]
    scan_dt = parse_date(flag["scan_date"])
    flag_timestamp = parse_flag_timestamp(flag["scan_date"])
    eval_today = today or date.today()

    trading_days_elapsed = count_trading_days(scan_dt, eval_today)

    # If scan is less than 1 trading day old, cannot measure T+1 Open yet -> stay ACTIVE
    if trading_days_elapsed < 1:
        return {"flag_id": flag_id, "symbol": symbol, "status": "ACTIVE", "trading_days_elapsed": 0}

    # Target entry is T+1 Open
    t1_date = get_next_trading_day(scan_dt, 1)
    max_eval_horizon = min(max(TRACKING_HORIZONS), trading_days_elapsed)
    max_eval_date = get_next_trading_day(scan_dt, max_eval_horizon)

    stock_df = fetch_price_history(symbol, t1_date, max_eval_date)
    if stock_df.empty:
        logger.debug("No price data found for %s to evaluate flag #%d", symbol, flag_id)
        return {"flag_id": flag_id, "symbol": symbol, "status": "ACTIVE"}

    # Entry price is strictly T+1 Open
    entry_price = None
    if t1_date in stock_df.index:
        entry_price = round(float(stock_df.loc[t1_date]["Open"]), 2)
    else:
        available_dates = [d for d in stock_df.index if d >= t1_date]
        if available_dates:
            entry_price = round(float(stock_df.loc[available_dates[0]]["Open"]), 2)

    if not entry_price or entry_price <= 0:
        logger.debug("Valid T+1 entry price not found for %s (flag #%d)", symbol, flag_id)
        return {"flag_id": flag_id, "symbol": symbol, "status": "ACTIVE"}

    # Evaluate each eligible horizon
    evaluated_horizons = 0
    material_announcement_found = False

    for h in TRACKING_HORIZONS:
        # Strictly skip horizons that have not occurred yet
        if trading_days_elapsed < h:
            continue

        th_date = get_next_trading_day(scan_dt, h)
        th_close = None
        if th_date in stock_df.index:
            th_close = float(stock_df.loc[th_date]["Close"])
        else:
            prev_dates = [d for d in stock_df.index if d <= th_date]
            if prev_dates:
                th_close = float(stock_df.loc[prev_dates[-1]]["Close"])

        # No real price data for this horizon -> skip it
        if th_close is None or th_close <= 0:
            continue

        fwd_return = round(((th_close - entry_price) / entry_price) * 100.0, 2)

        # Benchmark return over same window
        bench_return = None
        excess_return = None
        if benchmark_df is not None and not benchmark_df.empty:
            b_t1_open = None
            if t1_date in benchmark_df.index:
                b_t1_open = float(benchmark_df.loc[t1_date]["Open"])
            elif any(d >= t1_date for d in benchmark_df.index):
                b_t1_open = float(benchmark_df.loc[[d for d in benchmark_df.index if d >= t1_date][0]]["Open"])

            b_th_close = None
            if th_date in benchmark_df.index:
                b_th_close = float(benchmark_df.loc[th_date]["Close"])
            elif any(d <= th_date for d in benchmark_df.index):
                b_th_close = float(benchmark_df.loc[[d for d in benchmark_df.index if d <= th_date][-1]]["Close"])

            if b_t1_open and b_th_close and b_t1_open > 0:
                bench_return = round(((b_th_close - b_t1_open) / b_t1_open) * 100.0, 2)
                excess_return = round(fwd_return - bench_return, 2)

        # Fetch corporate announcements between T+1 and T+h
        all_announcements = fetch_corporate_announcements(symbol, t1_date, th_date)

        # Filter strictly: only announcements published AFTER flag timestamp
        forward_announcements = []
        for ann in all_announcements:
            ann_dt = ann.get("dt")
            if ann_dt and ann_dt <= flag_timestamp:
                # Pre-move disclosure: context only, not an outcome!
                continue
            forward_announcements.append(ann)

        ann_found = 1 if forward_announcements else 0
        best_type = None
        is_mat = 0
        ann_date_str = None
        ann_title = None
        ann_url = None

        if forward_announcements:
            for item in forward_announcements:
                subj = item.get("subject", "")
                detail = item.get("details", "")
                mat, cat = classify_announcement(subj, detail)

                # Prioritize detail text for auditability
                full_text = detail if detail else subj

                if mat == 1:
                    is_mat = 1
                    best_type = cat
                    ann_date_str = item.get("date_str")
                    ann_title = full_text
                    ann_url = item.get("url", "")
                    material_announcement_found = True
                    break
                elif not best_type:
                    best_type = cat
                    ann_date_str = item.get("date_str")
                    ann_title = full_text
                    ann_url = item.get("url", "")

        outcome_record = {
            "flag_id": flag_id,
            "horizon_days": h,
            "entry_price": entry_price,
            "forward_return": fwd_return,
            "benchmark_return": bench_return,
            "excess_return": excess_return,
            "announcement_found": ann_found,
            "announcement_type": best_type,
            "is_material": is_mat,
            "announcement_date": ann_date_str,
            "announcement_title": ann_title,
            "announcement_url": ann_url,
        }
        upsert_outcome(outcome_record, db_path=db_path)
        evaluated_horizons += 1

    # Status determination:
    # Must have elapsed at least 10 trading days to be marked RESOLVED
    if trading_days_elapsed >= 10:
        mark_flag_status(flag_id, "RESOLVED", db_path=db_path)
        new_status = "RESOLVED"
    elif trading_days_elapsed > TRACKING_MAX_DAYS:
        mark_flag_status(flag_id, "EXPIRED", db_path=db_path)
        new_status = "EXPIRED"
    else:
        mark_flag_status(flag_id, "ACTIVE", db_path=db_path)
        new_status = "ACTIVE"

    return {
        "flag_id": flag_id,
        "symbol": symbol,
        "status": new_status,
        "trading_days_elapsed": trading_days_elapsed,
        "evaluated_horizons": evaluated_horizons,
        "material_found": material_announcement_found,
        "entry_price": entry_price,
    }


def run_tracker(today: Optional[date] = None) -> Dict[str, Any]:
    """
    Main entry point for outcome tracking.
    Evaluates all eligible flags, updates stats, dumps SQL, and exports CSVs.
    """
    start_time = datetime.now()
    eval_today = today or date.today()
    logger.info("Running outcome tracker for date: %s", eval_today.isoformat())

    # Auto-refresh holidays from NSE API if needed
    try:
        sync_holidays_from_api()
    except Exception as exc:
        logger.debug("Holiday auto-refresh skipped: %s", exc)

    active_flags = get_active_flags()
    logger.info("Found %d active flags eligible for tracking evaluation", len(active_flags))

    if not active_flags:
        logger.info("No active flags to evaluate today.")
        return {"evaluated": 0, "status": "SUCCESS"}

    earliest_scan = min(parse_date(f["scan_date"]) for f in active_flags)
    benchmark_df = get_benchmark_history(earliest_scan, eval_today)

    evaluated_count = 0
    resolved_count = 0
    active_count = 0

    for flag in active_flags:
        res = evaluate_flag(flag, today=eval_today, benchmark_df=benchmark_df)
        evaluated_count += 1
        if res.get("status") == "RESOLVED":
            resolved_count += 1
        else:
            active_count += 1

    sql_path = export_db_to_sql()
    export_db_to_csv()

    stats = get_hit_rate_stats()
    runtime = (datetime.now() - start_time).total_seconds()
    last_mod_headers = fetch_sources_last_modified()

    log_run(
        run_type="track",
        source_used="yfinance_and_nse",
        runtime_seconds=runtime,
        rows_scanned=len(active_flags),
        flags_generated=resolved_count,
        status="SUCCESS",
        source_last_modified=last_mod_headers,
    )

    logger.info(
        "Tracker completed in %.2f seconds. Active: %d, Resolved: %d, Precision: %.1f%%, Lift: %.2fx",
        runtime, active_count, resolved_count, stats["flagged_precision"], stats["lift"]
    )
    return {
        "evaluated": evaluated_count,
        "active": active_count,
        "resolved": resolved_count,
        "stats": stats,
        "runtime_seconds": runtime,
    }


if __name__ == "__main__":
    result = run_tracker()
    print("\nOutcome Tracking Summary:")
    print(f"Evaluated: {result.get('evaluated')} flags")
    print(f"Active:    {result.get('active')} flags (fewer than 10 trading days)")
    print(f"Resolved:  {result.get('resolved')} flags (≥10 trading days)")
    if "stats" in result:
        st = result["stats"]
        print(f"Flagged Precision: {st.get('flagged_precision')}% ({st.get('flagged_catalysts')}/{st.get('flagged_evaluated')})")
        print(f"Control Precision: {st.get('control_precision')}% ({st.get('control_catalysts')}/{st.get('control_evaluated')})")
        print(f"Lift vs Control:   {st.get('lift')}x")
        print(f"Avg 10d Return:    {st.get('avg_fwd_ret_10d')}%")
