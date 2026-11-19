import os
import shutil
import sqlite3
import tempfile
import pandas as pd

# Path setup
SCRATCH_DIR = os.path.join(tempfile.gettempdir(), "test_pr1_scratch")
if os.path.exists(SCRATCH_DIR):
    shutil.rmtree(SCRATCH_DIR)
os.makedirs(SCRATCH_DIR, exist_ok=True)

out_dir = os.path.join(SCRATCH_DIR, "output")
os.makedirs(out_dir, exist_ok=True)

# Copy current master CSVs to scratch (representing git clone of repo without scanner.db)
src_susp = "output/suspicious_master.csv"
src_news = "output/news_driven_master.csv"
src_unexp = "output/unexplained_master.csv"

shutil.copy(src_susp, os.path.join(out_dir, "suspicious_master.csv"))
shutil.copy(src_news, os.path.join(out_dir, "news_driven_master.csv"))
if os.path.exists(src_unexp):
    shutil.copy(src_unexp, os.path.join(out_dir, "unexplained_master.csv"))

df_susp_before = pd.read_csv(os.path.join(out_dir, "suspicious_master.csv"))
df_news_before = pd.read_csv(os.path.join(out_dir, "news_driven_master.csv"))
print(f"BEFORE SCAN (committed CSVs without scanner.db):")
print(f"  suspicious_master.csv rows: {len(df_susp_before)}")
print(f"  news_driven_master.csv rows: {len(df_news_before)}")

# Now simulate a fresh DB created during scan (e.g. scanner.db newly initialized)
scratch_db = os.path.join(out_dir, "scanner.db")
assert not os.path.exists(scratch_db), "scanner.db should NOT exist initially"

import sys
sys.path.insert(0, os.path.abspath("."))
from db import init_db, upsert_flag, export_db_to_csv

# Initialize empty DB
init_db(scratch_db)

# Simulate 1 new flag discovered today
upsert_flag({
    "scan_date": "2026-11-18",
    "symbol": "NEWSTOCK",
    "company": "New Stock Ltd",
    "industry": "IT",
    "current_price": 500.0,
    "prev_close": 480.0,
    "price_change": 4.17,
    "current_volume": 100000,
    "avg_volume_20d": 25000,
    "volume_ratio": 4.0,
    "score": 75.0,
    "status": "ACTIVE",
    "catalyst_state": "NONE",
    "delivery_pct": 45.0,
    "run_type": "eod",
    "is_control": 0
}, db_path=scratch_db)

# Run export_db_to_csv pointing to scratch
export_db_to_csv(db_path=scratch_db, output_dir=out_dir)

df_susp_after = pd.read_csv(os.path.join(out_dir, "suspicious_master.csv"))
df_news_after = pd.read_csv(os.path.join(out_dir, "news_driven_master.csv"))
print(f"\nAFTER SCAN (with current db.py export logic):")
print(f"  suspicious_master.csv rows: {len(df_susp_after)}")
print(f"  news_driven_master.csv rows: {len(df_news_after)}")
if len(df_susp_after) < len(df_susp_before):
    print(f"CRITICAL ISSUE CONFIRMED: suspicious_master.csv dropped from {len(df_susp_before)} to {len(df_susp_after)}! History was overwritten!")
