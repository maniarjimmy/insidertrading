"""
Data Quality & Candle Validation Module (data_quality.py)
Phase 5 Implementation:
1. Validate OHLCV candles (detect missing candles, zero volume, inverted bounds).
2. Check for extreme price discontinuities (>25% move) and cross-reference corporate actions.
3. Maintain structured audit log of skipped/filtered symbols.
"""

from datetime import date, datetime
import logging
import os
from typing import Any, Dict, List, Optional, Tuple, Union

from config import setup_logging
from corporate_actions import is_near_corporate_action
from holidays import is_trading_day, parse_date

logger = setup_logging("data_quality")

AUDIT_LOG_FILE = os.path.join(os.path.dirname(__file__), "output", "data_quality_audit.log")


def validate_candle(candle: Dict[str, Any],
                    target_date: Union[date, datetime, str]) -> Tuple[bool, Optional[str]]:
    """
    Validate a single daily price candle.
    Returns (is_valid, rejection_reason).
    """
    t_date = parse_date(target_date)

    if not candle:
        return False, "EMPTY_CANDLE"

    sym = candle.get("symbol", "UNKNOWN")
    close_p = candle.get("close")
    open_p = candle.get("open")
    high_p = candle.get("high")
    low_p = candle.get("low")
    vol = candle.get("volume")

    # 1. Missing prices
    if close_p is None or close_p <= 0:
        return False, f"MISSING_OR_ZERO_CLOSE ({close_p})"

    # 2. Inverted bounds
    if open_p is not None and high_p is not None and low_p is not None:
        if high_p < low_p:
            return False, f"INVERTED_HIGH_LOW (high={high_p} < low={low_p})"
        if high_p < close_p or high_p < open_p:
            return False, f"HIGH_BELOW_CLOSE_OR_OPEN (high={high_p}, open={open_p}, close={close_p})"
        if low_p > close_p or low_p > open_p:
            return False, f"LOW_ABOVE_CLOSE_OR_OPEN (low={low_p}, open={open_p}, close={close_p})"

    # 3. Zero volume on active trading day
    if is_trading_day(t_date) and (vol is None or vol <= 0):
        return False, "ZERO_VOLUME_ON_TRADING_DAY"

    # 4. Extreme unadjusted price discontinuity (>25% price change)
    pct_change = candle.get("price_change")
    if pct_change is not None and abs(pct_change) >= 25.0:
        # Cross check if near corporate action
        near_action, action_details = is_near_corporate_action(sym, t_date, window_days=2)
        if near_action and action_details:
            logger.info("Legitimate corporate action price move for %s: %s (%s)",
                        sym, action_details.get("purpose"), action_details.get("action_type"))
        else:
            return False, f"EXTREME_PRICE_DISCONTINUITY ({pct_change}%) WITHOUT_CORPORATE_ACTION"

    return True, None


def audit_and_clean_market_data(raw_data: Dict[str, Dict[str, Any]],
                                target_date: Union[date, datetime, str]) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, str]]]:
    """
    Audit an entire universe market data dictionary.
    Returns (cleaned_valid_data, audit_records).
    """
    t_date = parse_date(target_date)
    cleaned = {}
    audit_records = []

    for sym, candle in raw_data.items():
        is_valid, reason = validate_candle(candle, t_date)
        if is_valid:
            cleaned[sym] = candle
        else:
            rec = {
                "date": t_date.isoformat(),
                "symbol": sym,
                "reason": reason or "UNKNOWN",
                "source": candle.get("source", "UNKNOWN") if candle else "NONE",
            }
            audit_records.append(rec)
            logger.warning("Rejected candle for %s on %s: %s", sym, t_date.isoformat(), reason)

    # Append to persistent audit log
    if audit_records:
        try:
            os.makedirs(os.path.dirname(AUDIT_LOG_FILE), exist_ok=True)
            with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
                for r in audit_records:
                    f.write(f"{r['date']} | {r['symbol']} | REJECTED: {r['reason']} | Source: {r['source']}\n")
        except Exception as exc:
            logger.debug("Failed writing audit log: %s", exc)

    return cleaned, audit_records
