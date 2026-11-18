"""
Corporate Actions Adjustment & Ex-Date Detection Module (corporate_actions.py)
Phase 5 Implementation:
1. Ingest corporate actions (splits, bonuses, rights, dividends) from NSE API with caching.
2. Detect whether a stock is within +/- N trading days of an ex-date.
3. Compute cumulative split/bonus price adjustment factor.
"""

from datetime import date, datetime, timedelta
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple, Union

import requests

from config import (
    REQUEST_BACKOFF_FACTOR,
    REQUEST_MAX_RETRIES,
    REQUEST_TIMEOUT,
    setup_logging,
)
from holidays import get_next_trading_day, get_previous_trading_day, parse_date

logger = setup_logging("corporate_actions")

_ACTIONS_CACHE_FILE = os.path.join(
    os.path.dirname(__file__), "output", "cache", "corporate_actions_cache.json"
)
_ACTIONS_CACHE: Optional[List[Dict[str, Any]]] = None

NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}


def load_cached_actions() -> List[Dict[str, Any]]:
    """Load cached corporate actions from disk."""
    global _ACTIONS_CACHE
    if _ACTIONS_CACHE is not None:
        return _ACTIONS_CACHE
    if os.path.exists(_ACTIONS_CACHE_FILE):
        try:
            with open(_ACTIONS_CACHE_FILE, "r", encoding="utf-8") as f:
                _ACTIONS_CACHE = json.load(f)
                return _ACTIONS_CACHE
        except Exception as exc:
            logger.debug("Failed loading actions cache: %s", exc)
    _ACTIONS_CACHE = []
    return _ACTIONS_CACHE


def save_cached_actions(actions: List[Dict[str, Any]]) -> None:
    """Save corporate actions to disk cache."""
    global _ACTIONS_CACHE
    _ACTIONS_CACHE = actions
    try:
        os.makedirs(os.path.dirname(_ACTIONS_CACHE_FILE), exist_ok=True)
        with open(_ACTIONS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(actions, f)
    except Exception as exc:
        logger.debug("Failed writing actions cache: %s", exc)


def parse_action_purpose(purpose_str: str) -> Tuple[str, float]:
    """
    Parse action purpose string to identify action type and adjustment ratio.
    Returns (action_type, ratio):
      action_type: 'SPLIT' | 'BONUS' | 'RIGHTS' | 'DIVIDEND' | 'OTHER'
      ratio: new_shares / old_shares (e.g. 2.0 for 1:1 bonus, 5.0 for 1:5 split)
    """
    p = (purpose_str or "").lower().strip()

    # Bonus Issue e.g. "Bonus 1:1", "Bonus issue in the ratio of 2:1"
    b_match = re.search(r"bonus.*?(\d+)\s*:\s*(\d+)", p)
    if b_match:
        new_s = float(b_match.group(1))
        old_s = float(b_match.group(2))
        if old_s > 0:
            return "BONUS", (old_s + new_s) / old_s

    # Stock Split / Sub-division e.g. "Sub-division from Rs. 10/- to Rs. 2/-", "Split 10 to 1"
    s_match = re.search(r"(?:split|sub-division|subdivision).*?(\d+(?:\.\d+)?).*?(?:to|into).*?(\d+(?:\.\d+)?)", p)
    if s_match:
        old_fv = float(s_match.group(1))
        new_fv = float(s_match.group(2))
        if new_fv > 0 and old_fv > new_fv:
            return "SPLIT", old_fv / new_fv

    # Rights issue
    if "rights" in p:
        return "RIGHTS", 1.0

    # Dividend
    if "dividend" in p or "interim" in p:
        return "DIVIDEND", 1.0

    return "OTHER", 1.0


def fetch_corporate_actions(symbol: Optional[str] = None,
                            force_refresh: bool = False) -> List[Dict[str, Any]]:
    """
    Fetch corporate actions from NSE public API with disk caching.
    Endpoint: https://www.nseindia.com/api/corporates-corporateActions?index=equities
    """
    cached = load_cached_actions()
    if cached and not force_refresh:
        if symbol:
            return [a for a in cached if a.get("symbol") == symbol]
        return cached

    url = "https://www.nseindia.com/api/corporates-corporateActions?index=equities"
    session = requests.Session()
    session.headers.update(NSE_HEADERS)

    for attempt in range(1, REQUEST_MAX_RETRIES + 1):
        try:
            # Bootstrap cookies
            session.get("https://www.nseindia.com", timeout=REQUEST_TIMEOUT)
            resp = session.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                items = data if isinstance(data, list) else data.get("data", [])
                parsed_actions = []
                for item in items:
                    sym = item.get("symbol", "").strip()
                    ex_date_str = item.get("exDate") or item.get("ndStartDate")
                    if not sym or not ex_date_str or ex_date_str == "-":
                        continue
                    try:
                        ex_dt = parse_date(ex_date_str)
                    except Exception:
                        continue

                    purpose = item.get("purpose", "")
                    action_type, ratio = parse_action_purpose(purpose)

                    parsed_actions.append({
                        "symbol": sym,
                        "company": item.get("companyName", "").strip(),
                        "series": item.get("series", "").strip(),
                        "ex_date": ex_dt.isoformat(),
                        "purpose": purpose,
                        "action_type": action_type,
                        "ratio": ratio,
                        "record_date": item.get("recordDate", ""),
                    })

                save_cached_actions(parsed_actions)
                if symbol:
                    return [a for a in parsed_actions if a.get("symbol") == symbol]
                return parsed_actions
        except Exception as exc:
            logger.debug("Attempt %d to fetch corporate actions failed: %s", attempt, exc)

    return [a for a in cached if a.get("symbol") == symbol] if symbol else cached


def is_near_corporate_action(symbol: str,
                             target_date: Union[date, datetime, str],
                             window_days: int = 2,
                             actions: Optional[List[Dict[str, Any]]] = None) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Check if target_date is within +/- window_days trading days of an ex-date for a
    material corporate action (SPLIT, BONUS, RIGHTS).
    Returns (is_near, action_details).
    """
    t_date = parse_date(target_date)
    action_list = actions if actions is not None else fetch_corporate_actions(symbol=symbol)

    # Compute window bounds using trading days
    lower_bound = get_previous_trading_day(t_date, window_days)
    upper_bound = get_next_trading_day(t_date, window_days)

    for a in action_list:
        if a.get("symbol") != symbol:
            continue
        # Only flag price-distorting structural corporate actions
        if a.get("action_type") not in ("SPLIT", "BONUS", "RIGHTS"):
            continue

        try:
            ex_dt = parse_date(a["ex_date"])
        except Exception:
            continue

        if lower_bound <= ex_dt <= upper_bound:
            return True, a

    return False, None


def adjust_price_for_corporate_actions(prices: List[Dict[str, Any]],
                                       actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Adjust historical daily price candles backwards for stock splits and bonus issues.
    Each candle should have {'date': 'YYYY-MM-DD', 'open': ..., 'high': ..., 'low': ..., 'close': ..., 'volume': ...}
    """
    if not prices or not actions:
        return prices

    # Filter actions to splits and bonuses
    split_bonuses = [
        a for a in actions
        if a.get("action_type") in ("SPLIT", "BONUS") and a.get("ratio", 1.0) > 1.0
    ]
    if not split_bonuses:
        return prices

    # Sort candles descending by date
    sorted_candles = sorted(prices, key=lambda x: parse_date(x["date"]), reverse=True)
    adjusted = []

    cumulative_factor = 1.0
    for candle in sorted_candles:
        c_date = parse_date(candle["date"])

        adj_candle = dict(candle)
        if cumulative_factor > 1.0:
            for k in ("open", "high", "low", "close"):
                if candle.get(k) is not None:
                    adj_candle[k] = round(candle[k] / cumulative_factor, 2)
            if candle.get("volume") is not None:
                adj_candle["volume"] = int(candle["volume"] * cumulative_factor)
            adj_candle["adj_factor"] = round(cumulative_factor, 4)
        else:
            adj_candle["adj_factor"] = 1.0

        # When stepping past an ex-date into the past, accumulate factor for earlier candles
        for act in split_bonuses:
            ex_dt = parse_date(act["ex_date"])
            if ex_dt == c_date:
                cumulative_factor *= act["ratio"]

        adjusted.append(adj_candle)

    # Return in original chronological order
    adjusted.sort(key=lambda x: parse_date(x["date"]))
    return adjusted
