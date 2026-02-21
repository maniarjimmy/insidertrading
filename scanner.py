"""
Price & Volume Scanner Module
Fetches current price and volume data for stocks, computes
percentage change and volume ratio vs 20-day average.
"""

import time
import warnings
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

from config import (
    BATCH_SIZE, BATCH_DELAY, VOLUME_HISTORY_DAYS,
    MIN_PCT_CHANGE, MAX_PCT_CHANGE, MIN_VOLUME_RATIO
)

warnings.filterwarnings("ignore", category=FutureWarning)


def scan_stocks(universe_df: pd.DataFrame) -> pd.DataFrame:
    """
    Scan all stocks in the universe for price and volume data.

    Parameters
    ----------
    universe_df : pd.DataFrame
        Must have columns: symbol, company, industry, yf_symbol

    Returns
    -------
    pd.DataFrame with columns:
        symbol, company, industry, current_price, prev_close,
        pct_change, current_volume, avg_volume_20d, volume_ratio
    """
    all_results = []
    symbols = universe_df["yf_symbol"].tolist()
    total = len(symbols)

    print(f"[Scanner] Scanning {total} stocks in batches of {BATCH_SIZE}...")

    for i in range(0, total, BATCH_SIZE):
        batch = symbols[i : i + BATCH_SIZE]
        batch_num = (i // BATCH_SIZE) + 1
        total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"  Batch {batch_num}/{total_batches} ({len(batch)} stocks)...", end=" ")

        try:
            batch_results = _scan_batch(batch)
            all_results.extend(batch_results)
            print(f"✓ ({len(batch_results)} ok)")
        except Exception as e:
            print(f"✗ Error: {e}")

        if i + BATCH_SIZE < total:
            time.sleep(BATCH_DELAY)

    if not all_results:
        print("[Scanner] ⚠️  No data received. Check internet connection.")
        return pd.DataFrame()

    results_df = pd.DataFrame(all_results)

    # Merge with universe data
    merged = universe_df.merge(results_df, on="yf_symbol", how="inner")

    print(f"[Scanner] ✅ Got data for {len(merged)}/{total} stocks")
    return merged


def _scan_batch(yf_symbols: list) -> list:
    """
    Fetch price and volume data for a batch of symbols.
    """
    results = []
    join_str = " ".join(yf_symbols)

    # Get current quotes
    tickers = yf.Tickers(join_str)

    # Get historical data for volume average (last 30 calendar days)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=VOLUME_HISTORY_DAYS)

    for sym in yf_symbols:
        try:
            ticker = tickers.tickers.get(sym)
            if ticker is None:
                continue

            # Get quote info
            info = ticker.fast_info
            current_price = getattr(info, "last_price", None)
            prev_close = getattr(info, "previous_close", None)

            if current_price is None or prev_close is None or prev_close == 0:
                continue

            pct_change = ((current_price - prev_close) / prev_close) * 100

            # Get historical data for volume
            hist = ticker.history(
                start=start_date.strftime("%Y-%m-%d"),
                end=end_date.strftime("%Y-%m-%d"),
                interval="1d"
            )

            if hist.empty or len(hist) < 5:
                continue

            # Current day's volume (last row)
            current_volume = hist["Volume"].iloc[-1]

            # Average volume over prior 20 trading days (exclude today)
            prior_volumes = hist["Volume"].iloc[:-1]
            if len(prior_volumes) == 0:
                continue

            # Use up to 20 most recent trading days
            avg_volume_20d = prior_volumes.tail(20).mean()

            if avg_volume_20d == 0:
                continue

            volume_ratio = current_volume / avg_volume_20d

            results.append({
                "yf_symbol": sym,
                "current_price": round(current_price, 2),
                "prev_close": round(prev_close, 2),
                "pct_change": round(pct_change, 2),
                "current_volume": int(current_volume),
                "avg_volume_20d": int(avg_volume_20d),
                "volume_ratio": round(volume_ratio, 2),
            })

        except Exception:
            # Skip individual stock errors silently
            pass

    return results


def filter_movers(df: pd.DataFrame,
                  min_pct: float = None,
                  max_pct: float = None,
                  min_vol_ratio: float = None) -> pd.DataFrame:
    """
    Filter for positive movers with abnormal volume.

    Parameters
    ----------
    df : pd.DataFrame from scan_stocks()
    min_pct : float, minimum % price change (default from config)
    max_pct : float, maximum % price change (default from config)
    min_vol_ratio : float, minimum volume ratio (default from config)

    Returns
    -------
    pd.DataFrame of stocks meeting all criteria, sorted by volume_ratio desc
    """
    if df.empty:
        return df

    min_pct = min_pct if min_pct is not None else MIN_PCT_CHANGE
    max_pct = max_pct if max_pct is not None else MAX_PCT_CHANGE
    min_vol_ratio = min_vol_ratio if min_vol_ratio is not None else MIN_VOLUME_RATIO

    filtered = df[
        (df["pct_change"] >= min_pct) &
        (df["pct_change"] <= max_pct) &
        (df["volume_ratio"] >= min_vol_ratio)
    ].copy()

    filtered = filtered.sort_values("volume_ratio", ascending=False).reset_index(drop=True)

    print(f"[Scanner] 🎯 {len(filtered)} stocks pass filters "
          f"(price: +{min_pct}% to +{max_pct}%, vol ratio: ≥{min_vol_ratio}x)")
    return filtered


# ── CLI ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Quick test with a few stocks
    test_symbols = ["COCHINSHIP.NS", "CDSL.NS", "BSE.NS", "MAZDOCK.NS", "BDL.NS"]
    test_df = pd.DataFrame({
        "symbol": [s.replace(".NS", "") for s in test_symbols],
        "company": ["Test"] * len(test_symbols),
        "industry": ["Test"] * len(test_symbols),
        "yf_symbol": test_symbols,
        "rank": range(210, 210 + len(test_symbols)),
    })

    print("=" * 60)
    print("Scanner Module — Quick Test")
    print("=" * 60)

    results = scan_stocks(test_df)
    if not results.empty:
        print("\nAll results:")
        cols = ["symbol", "pct_change", "volume_ratio", "current_price", "current_volume"]
        print(results[cols].to_string(index=False))

        movers = filter_movers(results)
        if not movers.empty:
            print("\nFiltered movers:")
            print(movers[cols].to_string(index=False))
        else:
            print("\nNo stocks passed the filter.")
