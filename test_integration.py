"""
Quick integration test — scans 10 stocks to verify end-to-end pipeline.
Uses very low thresholds to ensure some stocks are flagged even after hours.
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
from datetime import datetime
from scanner import scan_stocks, filter_movers
from news import classify_stocks
from report import generate_report, save_csv

# 10 representative mid/small-cap stocks
test_symbols = [
    ("COCHINSHIP", "Cochin Shipyard", "Defence"),
    ("CDSL", "Central Depository Services", "Exchange"),
    ("BSE", "BSE Ltd", "Exchange"),
    ("MAZDOCK", "Mazagon Dock Shipbuilders", "Defence"),
    ("BDL", "Bharat Dynamics", "Defence"),
    ("OLECTRA", "Olectra Greentech", "EV"),
    ("MCX", "MCX India", "Exchange"),
    ("RADICO", "Radico Khaitan", "Liquor"),
    ("PVRINOX", "PVR INOX", "Entertainment"),
    ("SOBHA", "Sobha Ltd", "Real Estate"),
]

test_df = pd.DataFrame({
    "rank": range(210, 210 + len(test_symbols)),
    "symbol": [s[0] for s in test_symbols],
    "company": [s[1] for s in test_symbols],
    "industry": [s[2] for s in test_symbols],
    "yf_symbol": [s[0] + ".NS" for s in test_symbols],
})

print("=" * 60)
print("  INTEGRATION TEST (10 stocks, low thresholds)")
print("=" * 60)

# Step 1: Scan
print("\n--- Scanning ---")
results = scan_stocks(test_df)
print(f"Got data for {len(results)} stocks")

if results.empty:
    print("No data. Exiting.")
    sys.exit(1)

# Show all results
cols = ["symbol", "pct_change", "volume_ratio", "current_price"]
print(results[cols].to_string(index=False))

# Step 2: Filter with very low thresholds (so at least some stocks pass)
print("\n--- Filtering (min 0%, min vol 0x) ---")
movers = filter_movers(results, min_pct=-99, max_pct=99, min_vol_ratio=0)

# Take top 3 for news check (to keep test fast)
top3 = movers.head(3).copy()
print(f"Taking top 3 for news check: {top3['symbol'].tolist()}")

# Step 3: News check
print("\n--- Checking News ---")
suspicious, news_driven = classify_stocks(top3)

# Step 4: Generate report
print("\n--- Generating Report ---")
ts = datetime.now()
report_path = generate_report(suspicious, news_driven, len(results), len(movers), ts)

# Also save CSV
if not suspicious.empty:
    save_csv(suspicious, "test_suspicious", ts)
if not news_driven.empty:
    save_csv(news_driven, "test_news_driven", ts)

print(f"\n{'='*60}")
print(f"  TEST PASSED!")
print(f"  Suspicious: {len(suspicious)}, News-driven: {len(news_driven)}")
print(f"  Report: {report_path}")
print(f"{'='*60}")
