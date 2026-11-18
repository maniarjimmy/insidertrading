"""
NSE Trading Holiday Calendar Module
Provides year-agnostic trading-day arithmetic (T+N), auto-refresh from NSE API,
and out-of-range calendar warnings.
"""

from datetime import date, datetime, timedelta
import json
import logging
import os
import sqlite3
import time
from typing import Any, Dict, List, Optional, Set, Union

import requests

from config import (
    DB_PATH,
    HOLIDAYS_FILE,
    REQUEST_BACKOFF_FACTOR,
    REQUEST_MAX_RETRIES,
    REQUEST_TIMEOUT,
    setup_logging,
)

logger = setup_logging("holidays")

# In-memory cache of loaded trading holidays (ISO string: "YYYY-MM-DD")
_HOLIDAY_CACHE: Optional[Set[str]] = None
_LAST_SYNC_TIMESTAMP: Optional[float] = None


def parse_date(d: Union[date, datetime, str]) -> date:
    """Normalize a date, datetime, or date string into a datetime.date object."""
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    if isinstance(d, str):
        d = d.strip()
        if " " in d:
            d = d.split(" ")[0]
        for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%m-%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(d, fmt).date()
            except ValueError:
                continue
    raise ValueError(f"Unable to parse date: {d}")


def load_holidays_from_file(filepath: str = HOLIDAYS_FILE) -> Set[str]:
    """Load holiday dates from static JSON files (2024, 2025, 2026)."""
    dates = set()
    data_dir = os.path.dirname(filepath) if os.path.isabs(filepath) else os.path.join(os.path.dirname(__file__), "data")

    # Discover all year files (e.g. nse_holidays_2024.json, nse_holidays_2025.json, nse_holidays_2026.json)
    target_files = set()
    if os.path.isfile(filepath):
        target_files.add(filepath)
    if os.path.isdir(data_dir):
        for fname in os.listdir(data_dir):
            if fname.startswith("nse_holidays_") and fname.endswith(".json"):
                target_files.add(os.path.join(data_dir, fname))

    for fpath in target_files:
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data:
                if "isoDate" in item:
                    dates.add(item["isoDate"])
                elif "tradingDate" in item:
                    try:
                        d = datetime.strptime(item["tradingDate"], "%d-%b-%Y").strftime("%Y-%m-%d")
                        dates.add(d)
                    except ValueError:
                        pass
        except Exception as exc:
            logger.debug("Failed reading %s: %s", fpath, exc)

    return dates


def load_holidays_from_db(db_path: str = DB_PATH) -> Set[str]:
    """Load holiday dates from the SQLite database (all years)."""
    if not os.path.isfile(db_path):
        return set()
    try:
        conn = sqlite3.connect(db_path, timeout=10.0)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='holidays'")
            if not cursor.fetchone():
                return set()
            cursor.execute("SELECT date FROM holidays WHERE trading_holiday = 1")
            rows = cursor.fetchall()
            return {r[0] for r in rows if r[0]}
        finally:
            conn.close()
    except Exception as exc:
        logger.debug("Could not read holidays from DB: %s", exc)
        return set()


def fetch_nse_holidays() -> List[Dict[str, Any]]:
    """
    Fetch the official trading holiday master from NSE with retry and backoff.
    Returns list of dicts: [{'date': 'YYYY-MM-DD', 'description': '...', 'trading_holiday': 1}]
    """
    url = "https://www.nseindia.com/api/holiday-master?type=trading"
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
                cm_holidays = data.get("CM", data.get("equities", []))
                result = []
                for item in cm_holidays:
                    td = item.get("tradingDate")
                    desc = item.get("description", "")
                    if td:
                        try:
                            iso = datetime.strptime(td, "%d-%b-%Y").strftime("%Y-%m-%d")
                            result.append({"date": iso, "description": desc, "trading_holiday": 1})
                        except ValueError:
                            pass
                logger.info("Successfully fetched %d trading holidays from NSE API", len(result))
                return result
        except Exception as exc:
            logger.debug("Attempt %d to fetch NSE holidays failed: %s", attempt, exc)
            time.sleep(REQUEST_BACKOFF_FACTOR ** attempt)

    logger.warning("All attempts to fetch online NSE holidays failed. Falling back to local cache.")
    return []


def sync_holidays_from_api(db_path: str = DB_PATH) -> int:
    """
    Auto-refresh holidays from the NSE API and persist them to SQLite.
    Safe to call on every run (cached to avoid repeat calls within 1 hour).
    """
    global _LAST_SYNC_TIMESTAMP, _HOLIDAY_CACHE
    now = time.time()
    if _LAST_SYNC_TIMESTAMP is not None and (now - _LAST_SYNC_TIMESTAMP) < 3600:
        return 0  # synced recently

    holidays = fetch_nse_holidays()
    if not holidays:
        return 0

    from db import upsert_holidays
    count = upsert_holidays(holidays, db_path=db_path)
    _LAST_SYNC_TIMESTAMP = now
    # Refresh in-memory cache
    _HOLIDAY_CACHE = load_holidays_from_db(db_path)
    logger.info("Auto-refreshed and synced %d holidays to database", count)
    return count


def check_holiday_coverage(target_date: date, holidays: Set[str]) -> None:
    """
    Check if the holiday calendar covers the year of target_date.
    Logs a warning if future years are missing.
    """
    target_year = target_date.year
    known_years = {int(d.split("-")[0]) for d in holidays if "-" in d}
    if known_years and target_year > max(known_years):
        logger.warning(
            "⚠️ Holiday calendar coverage gap: target date %s (year %d) exceeds max known holiday year %d! "
            "Please ensure upcoming year holidays are synced. Falling back to Mon-Fri trading calendar.",
            target_date.isoformat(), target_year, max(known_years)
        )


def get_holiday_set(db_path: str = DB_PATH, refresh: bool = False) -> Set[str]:
    """Retrieve the set of holiday ISO date strings (year-agnostic, cached in memory)."""
    global _HOLIDAY_CACHE
    if _HOLIDAY_CACHE is not None and not refresh:
        return _HOLIDAY_CACHE

    holidays = load_holidays_from_db(db_path)
    file_holidays = load_holidays_from_file()
    holidays = holidays.union(file_holidays)

    _HOLIDAY_CACHE = holidays
    return _HOLIDAY_CACHE


def is_trading_day(d: Union[date, datetime, str], db_path: str = DB_PATH) -> bool:
    """
    Check if a given date is an active NSE trading day.
    Returns False for Saturdays, Sundays, and official trading holidays.
    """
    parsed = parse_date(d)
    # 5 = Saturday, 6 = Sunday
    if parsed.weekday() >= 5:
        return False

    holidays = get_holiday_set(db_path)
    check_holiday_coverage(parsed, holidays)
    iso = parsed.strftime("%Y-%m-%d")
    return iso not in holidays


def get_next_trading_day(d: Union[date, datetime, str], n: int = 1, db_path: str = DB_PATH) -> date:
    """Advance n trading days from date d, skipping weekends and NSE holidays."""
    cur = parse_date(d)
    count = 0
    while count < n:
        cur += timedelta(days=1)
        if is_trading_day(cur, db_path):
            count += 1
    return cur


def get_previous_trading_day(d: Union[date, datetime, str], n: int = 1, db_path: str = DB_PATH) -> date:
    """Step backward n trading days from date d, skipping weekends and NSE holidays."""
    cur = parse_date(d)
    count = 0
    while count < n:
        cur -= timedelta(days=1)
        if is_trading_day(cur, db_path):
            count += 1
    return cur


def get_trading_days_between(start_d: Union[date, datetime, str],
                             end_d: Union[date, datetime, str],
                             db_path: str = DB_PATH) -> List[date]:
    """Return all trading days in the range [start_d, end_d] inclusive."""
    start = parse_date(start_d)
    end = parse_date(end_d)
    if start > end:
        return []
    trading_days = []
    cur = start
    while cur <= end:
        if is_trading_day(cur, db_path):
            trading_days.append(cur)
        cur += timedelta(days=1)
    return trading_days


def count_trading_days(start_d: Union[date, datetime, str],
                       end_d: Union[date, datetime, str],
                       db_path: str = DB_PATH) -> int:
    """Count number of trading days between start_d and end_d (excluding start_d, including end_d)."""
    start = parse_date(start_d)
    end = parse_date(end_d)
    if start >= end:
        return 0
    days = get_trading_days_between(start + timedelta(days=1), end, db_path)
    return len(days)
