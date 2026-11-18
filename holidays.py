"""
NSE Trading Holiday Calendar Module
Provides accurate trading-day arithmetic (T+N) and holiday checks.
"""

from datetime import date, datetime, timedelta
import json
import logging
import os
import sqlite3
import time
from typing import Dict, List, Optional, Set, Union

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


def parse_date(d: Union[date, datetime, str]) -> date:
    """Normalize a date, datetime, or date string into a datetime.date object."""
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    if isinstance(d, str):
        # Support "YYYY-MM-DD", "YYYY-MM-DD HH:MM", "DD-MM-YYYY", etc.
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
    """Load holiday dates from the static JSON file."""
    if not os.path.isfile(filepath):
        logger.warning("Holidays file not found at %s", filepath)
        return set()
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        dates = set()
        for item in data:
            if "isoDate" in item:
                dates.add(item["isoDate"])
            elif "tradingDate" in item:
                try:
                    d = datetime.strptime(item["tradingDate"], "%d-%b-%Y").strftime("%Y-%m-%d")
                    dates.add(d)
                except ValueError:
                    pass
        return dates
    except Exception as exc:
        logger.error("Failed to read holidays file: %s", exc)
        return set()


def load_holidays_from_db(db_path: str = DB_PATH) -> Set[str]:
    """Load holiday dates from the SQLite database."""
    if not os.path.isfile(db_path):
        return set()
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            # Check if table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='holidays'")
            if not cursor.fetchone():
                return set()
            cursor.execute("SELECT date FROM holidays WHERE trading_holiday = 1")
            rows = cursor.fetchall()
            return {r[0] for r in rows if r[0]}
    except Exception as exc:
        logger.debug("Could not read holidays from DB: %s", exc)
        return set()


def fetch_nse_holidays() -> List[Dict[str, str]]:
    """
    Fetch the official trading holiday master from NSE with retry and backoff.
    Returns a list of dicts: [{'date': 'YYYY-MM-DD', 'description': '...'}]
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
            # Bootstrap session cookie
            session.get("https://www.nseindia.com", timeout=REQUEST_TIMEOUT)
            resp = session.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                # 'CM' indicates Capital Market (Equities)
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
            logger.warning("Attempt %d to fetch NSE holidays failed: %s", attempt, exc)
            time.sleep(REQUEST_BACKOFF_FACTOR ** attempt)

    logger.warning("All attempts to fetch online NSE holidays failed. Falling back to local cache.")
    return []


def get_holiday_set(db_path: str = DB_PATH, refresh: bool = False) -> Set[str]:
    """Retrieve the set of holiday ISO date strings (cached in memory)."""
    global _HOLIDAY_CACHE
    if _HOLIDAY_CACHE is not None and not refresh:
        return _HOLIDAY_CACHE

    holidays = load_holidays_from_db(db_path)
    if not holidays:
        holidays = load_holidays_from_file()

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
    iso = parsed.strftime("%Y-%m-%d")
    holidays = get_holiday_set(db_path)
    return iso not in holidays


def get_next_trading_day(d: Union[date, datetime, str], n: int = 1, db_path: str = DB_PATH) -> date:
    """
    Advance n trading days from date d, skipping weekends and NSE holidays.
    """
    cur = parse_date(d)
    count = 0
    while count < n:
        cur += timedelta(days=1)
        if is_trading_day(cur, db_path):
            count += 1
    return cur


def get_previous_trading_day(d: Union[date, datetime, str], n: int = 1, db_path: str = DB_PATH) -> date:
    """
    Step backward n trading days from date d, skipping weekends and NSE holidays.
    """
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
    """
    Return all trading days in the range [start_d, end_d] inclusive.
    """
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
