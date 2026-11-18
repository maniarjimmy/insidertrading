"""
NSE UDDiP Bhavcopy & Security Delivery Position Ingestion Module (bhavcopy.py)
Phase 5 Implementation:
1. Ingest official UDDiP Bhavcopy (BhavCopy_NSE_CM_0_0_0_YYYYMMDD_F_0000.csv.zip) as primary EOD data.
2. Ingest Security Delivery Position (MTO_DDMMYYYY.DAT) for official delivery % and quantity.
3. Fall back to yfinance when Bhavcopy is not yet published or unreachable.
"""

from datetime import date, datetime, timedelta
import io
import json
import logging
import os
import zipfile
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import pandas as pd
import requests

from config import (
    REQUEST_BACKOFF_FACTOR,
    REQUEST_MAX_RETRIES,
    REQUEST_TIMEOUT,
    setup_logging,
)
from holidays import is_trading_day, parse_date

logger = setup_logging("bhavcopy")

BHAVCOPY_CACHE_DIR = os.path.join(os.path.dirname(__file__), "output", "cache", "bhavcopy")
os.makedirs(BHAVCOPY_CACHE_DIR, exist_ok=True)

NSE_ARCHIVE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}


def download_uddip_bhavcopy(target_date: Union[date, datetime, str]) -> Optional[pd.DataFrame]:
    """
    Download and parse official NSE UDDiP Bhavcopy CSV for target_date.
    Returns normalized DataFrame with columns: symbol, series, open, high, low, close, prev_close, volume, turnover.
    """
    t_date = parse_date(target_date)
    ymd = t_date.strftime("%Y%m%d")

    cache_file = os.path.join(BHAVCOPY_CACHE_DIR, f"uddip_{ymd}.parquet")
    if os.path.exists(cache_file):
        try:
            return pd.read_parquet(cache_file)
        except Exception:
            pass

    url = f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{ymd}_F_0000.csv.zip"

    for attempt in range(1, REQUEST_MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers=NSE_ARCHIVE_HEADERS, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
                    csv_names = [n for n in z.namelist() if n.endswith(".csv")]
                    if not csv_names:
                        return None
                    with z.open(csv_names[0]) as f:
                        df = pd.read_csv(f)

                # Normalize column names
                rename_map = {
                    "TckrSymb": "symbol",
                    "SctySrs": "series",
                    "OpnPric": "open",
                    "HghPric": "high",
                    "LwPric": "low",
                    "ClsPric": "close",
                    "PrvsClsgPric": "prev_close",
                    "TtlTradgVol": "volume",
                    "TtlTrfVal": "turnover",
                }
                df = df.rename(columns=rename_map)

                # Keep only active equity series
                if "series" in df.columns:
                    df = df[df["series"].isin(["EQ", "BE", "BZ", "SM"])].copy()

                df["symbol"] = df["symbol"].astype(str).str.strip()
                for num_col in ("open", "high", "low", "close", "prev_close", "volume", "turnover"):
                    if num_col in df.columns:
                        df[num_col] = pd.to_numeric(df[num_col], errors="coerce")

                # Compute price change
                if "close" in df.columns and "prev_close" in df.columns:
                    df["price_change"] = ((df["close"] - df["prev_close"]) / df["prev_close"] * 100.0).round(2)

                try:
                    df.to_parquet(cache_file)
                except Exception:
                    pass

                return df
            elif resp.status_code == 404:
                logger.debug("UDDiP Bhavcopy not published yet for %s (HTTP 404)", ymd)
                return None
        except Exception as exc:
            logger.debug("Attempt %d to fetch UDDiP Bhavcopy failed: %s", attempt, exc)

    return None


def download_mto_delivery(target_date: Union[date, datetime, str]) -> Dict[str, Dict[str, float]]:
    """
    Download and parse official NSE Security Delivery Position (MTO_DDMMYYYY.DAT).
    Returns dict: {symbol: {'delivery_qty': float, 'delivery_pct': float, 'traded_qty': float}}
    """
    t_date = parse_date(target_date)
    dmy = t_date.strftime("%d%m%Y")
    cache_file = os.path.join(BHAVCOPY_CACHE_DIR, f"mto_{dmy}.json")

    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    url = f"https://nsearchives.nseindia.com/archives/equities/mto/MTO_{dmy}.DAT"

    for attempt in range(1, REQUEST_MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers=NSE_ARCHIVE_HEADERS, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                delivery_map = {}
                lines = resp.text.splitlines()
                for line in lines:
                    parts = line.strip().split(",")
                    # Record type 20: [RecordType, SrNo, Symbol, Series, TradedQty, DeliveredQty, DeliveryPct]
                    if len(parts) >= 7 and parts[0].strip() == "20":
                        sym = parts[2].strip()
                        series = parts[3].strip()
                        if series in ("EQ", "BE", "BZ", "SM"):
                            try:
                                traded = float(parts[4].strip())
                                delivered = float(parts[5].strip())
                                pct = float(parts[6].strip())
                                delivery_map[sym] = {
                                    "traded_qty": traded,
                                    "delivery_qty": delivered,
                                    "delivery_pct": pct,
                                }
                            except ValueError:
                                pass

                try:
                    with open(cache_file, "w", encoding="utf-8") as f:
                        json.dump(delivery_map, f)
                except Exception:
                    pass

                return delivery_map
            elif resp.status_code == 404:
                return {}
        except Exception as exc:
            logger.debug("Attempt %d to fetch MTO delivery failed: %s", attempt, exc)

    return {}


def fetch_yfinance_fallback(symbol: str, target_date: date) -> Optional[Dict[str, Any]]:
    """Fetch single-day candle fallback using yfinance."""
    try:
        import yfinance as yf
        ticker_str = f"{symbol}.NS"
        t = yf.Ticker(ticker_str)
        # Fetch 5 days to cover weekends and compute prev_close reliably
        hist = t.history(start=target_date - timedelta(days=5), end=target_date + timedelta(days=1))
        if hist.empty:
            return None

        # Locate exact target date row
        target_ts = pd.Timestamp(target_date).date()
        hist.index = hist.index.map(lambda x: x.date())
        if target_ts not in hist.index:
            return None

        loc = hist.index.get_loc(target_ts)
        row = hist.loc[target_ts]
        prev_row = hist.iloc[loc - 1] if loc > 0 else row

        close_p = float(row["Close"])
        prev_p = float(prev_row["Close"])
        vol = int(row["Volume"])

        return {
            "symbol": symbol,
            "open": round(float(row["Open"]), 2),
            "high": round(float(row["High"]), 2),
            "low": round(float(row["Low"]), 2),
            "close": round(close_p, 2),
            "prev_close": round(prev_p, 2),
            "price_change": round(((close_p - prev_p) / prev_p * 100.0) if prev_p else 0.0, 2),
            "volume": vol,
            "delivery_pct": None,
            "source": "yfinance_fallback",
        }
    except Exception as exc:
        logger.debug("yfinance fallback failed for %s: %s", symbol, exc)
        return None


def get_eod_data_for_universe(symbols: List[str],
                              target_date: Union[date, datetime, str]) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    """
    Get clean EOD data for a list of symbols on target_date.
    Primary source: UDDiP Bhavcopy + MTO delivery data.
    Fallback: yfinance.
    Returns (eod_data_map, skipped_symbols).
    """
    t_date = parse_date(target_date)
    bhav = download_uddip_bhavcopy(t_date)
    delivery = download_mto_delivery(t_date)

    data_map = {}
    skipped = []

    if bhav is not None and not bhav.empty:
        # Index bhavcopy by symbol
        bhav_indexed = bhav.set_index("symbol").to_dict(orient="index")
        for sym in symbols:
            clean_sym = sym.strip()
            if clean_sym in bhav_indexed:
                row = bhav_indexed[clean_sym]
                deliv_info = delivery.get(clean_sym, {})
                data_map[clean_sym] = {
                    "symbol": clean_sym,
                    "open": row.get("open"),
                    "high": row.get("high"),
                    "low": row.get("low"),
                    "close": row.get("close"),
                    "prev_close": row.get("prev_close"),
                    "price_change": row.get("price_change"),
                    "volume": row.get("volume"),
                    "turnover": row.get("turnover"),
                    "delivery_pct": deliv_info.get("delivery_pct"),
                    "delivery_qty": deliv_info.get("delivery_qty"),
                    "source": "NSE_UDDiP",
                }
            else:
                # Try fallback
                fb = fetch_yfinance_fallback(clean_sym, t_date)
                if fb:
                    data_map[clean_sym] = fb
                else:
                    skipped.append(clean_sym)
    else:
        # Bhavcopy unavailable: use yfinance fallback
        logger.info("Bhavcopy unavailable for %s. Using yfinance fallback for %d symbols.", t_date.isoformat(), len(symbols))
        for sym in symbols:
            clean_sym = sym.strip()
            fb = fetch_yfinance_fallback(clean_sym, t_date)
            if fb:
                data_map[clean_sym] = fb
            else:
                skipped.append(clean_sym)

    return data_map, skipped
