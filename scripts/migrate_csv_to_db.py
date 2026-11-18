"""
Historical CSV to SQLite Database Migration Script (Phase 1)
Migrates historical suspicious_master.csv and news_driven_master.csv
into output/scanner.db, populates trading holidays, creates initial .dump,
and generates backward-compatible CSV exports.
"""

from datetime import datetime
import json
import logging
import os
import sys

# Ensure root directory is on python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from config import (
    DB_PATH,
    DB_SQL_DUMP_PATH,
    HOLIDAYS_FILE,
    NEWS_DRIVEN_MASTER_CSV,
    SUSPICIOUS_MASTER_CSV,
    setup_logging,
)
from db import (
    export_db_to_csv,
    export_db_to_sql,
    init_db,
    log_run,
    upsert_flag,
    upsert_holidays,
)

logger = setup_logging("migration")


def compute_heuristic_score(vol_ratio: float, pct_change: float) -> float:
    """Compute a baseline score (0-100) based on volume ratio and price move."""
    try:
        vr = float(vol_ratio or 1.0)
        pc = float(pct_change or 0.0)
        # 50% weight on volume ratio (scaled 2x-10x), 50% weight on price change (scaled 4%-15%)
        vr_score = min(50.0, max(0.0, (vr - 2.0) / 8.0 * 50.0))
        pc_score = min(50.0, max(0.0, (pc - 4.0) / 11.0 * 50.0))
        return round(vr_score + pc_score, 1)
    except Exception:
        return 50.0


def migrate_csv_file(filepath: str, is_catalyst_source: bool, db_path: str = DB_PATH) -> int:
    """Parse and migrate a single CSV file into the database."""
    if not os.path.isfile(filepath):
        logger.warning("File not found for migration: %s", filepath)
        return 0

    try:
        df = pd.read_csv(filepath)
    except Exception as exc:
        logger.error("Failed to read %s: %s", filepath, exc)
        return 0

    imported_count = 0
    for _, row in df.iterrows():
        symbol = str(row.get("symbol", "")).strip()
        company = str(row.get("company", "")).strip()

        # Skip dummy empty rows or placeholders
        if not symbol or symbol == "nan" or company == "NONE" or symbol == "NONE":
            continue

        raw_ts = str(row.get("scan_timestamp", "")).strip()
        if not raw_ts or raw_ts == "nan":
            scan_date = datetime.now().strftime("%Y-%m-%d")
        else:
            scan_date = raw_ts.split(" ")[0]

        has_cat = row.get("has_catalyst_news", False)
        classification = str(row.get("classification", "")).strip().lower()

        if is_catalyst_source or str(has_cat).lower() in ("true", "1") or classification == "catalyst":
            catalyst_state = "CATALYST"
        elif classification == "generic_only":
            catalyst_state = "UNCLEAR"
        else:
            catalyst_state = "NONE"

        vol_ratio = float(row.get("volume_ratio", 1.0) or 1.0)
        pct_change = float(row.get("pct_change", 0.0) or 0.0)
        score = compute_heuristic_score(vol_ratio, pct_change)

        flag_data = {
            "scan_date": scan_date,
            "symbol": symbol,
            "company": company if company != "nan" else "",
            "industry": str(row.get("industry", "")).strip() if str(row.get("industry", "")) != "nan" else "",
            "current_price": float(row.get("current_price", 0.0)) if pd.notnull(row.get("current_price")) else None,
            "prev_close": float(row.get("prev_close", 0.0)) if pd.notnull(row.get("prev_close")) else None,
            "price_change": pct_change,
            "current_volume": int(row.get("current_volume", 0)) if pd.notnull(row.get("current_volume")) else 0,
            "avg_volume_20d": float(row.get("avg_volume_20d", 0.0)) if pd.notnull(row.get("avg_volume_20d")) else 0.0,
            "volume_ratio": vol_ratio,
            "score": score,
            "status": "ACTIVE",
            "catalyst_state": catalyst_state,
            "delivery_pct": None,
            "run_type": "eod",
            "is_control": 0,
        }

        upsert_flag(flag_data, db_path=db_path)
        imported_count += 1

    logger.info("Migrated %d valid records from %s", imported_count, filepath)
    return imported_count


def load_and_insert_holidays(db_path: str = DB_PATH) -> int:
    """Populate holidays table from local JSON file."""
    if not os.path.isfile(HOLIDAYS_FILE):
        logger.warning("Holidays file not found: %s", HOLIDAYS_FILE)
        return 0

    with open(HOLIDAYS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    holiday_records = []
    for item in data:
        holiday_records.append({
            "date": item.get("isoDate"),
            "description": item.get("description", ""),
            "trading_holiday": 1,
        })

    count = upsert_holidays(holiday_records, db_path=db_path)
    logger.info("Loaded %d trading holidays into database", count)
    return count


def run_migration(db_path: str = DB_PATH) -> None:
    """Orchestrate full migration of CSVs to DB and initial exports."""
    start_time = datetime.now()
    logger.info("Starting historical CSV migration to SQLite: %s", db_path)

    init_db(db_path)

    holidays_loaded = load_and_insert_holidays(db_path)

    suspicious_count = migrate_csv_file(SUSPICIOUS_MASTER_CSV, is_catalyst_source=False, db_path=db_path)
    news_count = migrate_csv_file(NEWS_DRIVEN_MASTER_CSV, is_catalyst_source=True, db_path=db_path)
    total_migrated = suspicious_count + news_count

    # Generate initial SQL dump
    sql_path = export_db_to_sql(db_path)

    # Export master CSVs from DB
    export_db_to_csv(db_path)

    runtime = (datetime.now() - start_time).total_seconds()
    log_run(
        run_type="migration",
        source_used="csv_master_files",
        runtime_seconds=runtime,
        rows_scanned=total_migrated,
        flags_generated=total_migrated,
        status="SUCCESS",
        db_path=db_path
    )

    logger.info("Migration finished successfully in %.2f seconds. Total records: %d", runtime, total_migrated)
    print(f"\n✅ Migration Complete!")
    print(f"   Database: {db_path}")
    print(f"   SQL Dump: {sql_path}")
    print(f"   Holidays: {holidays_loaded}")
    print(f"   Flags Ingested: {total_migrated} ({suspicious_count} suspicious, {news_count} news-driven)")


if __name__ == "__main__":
    run_migration()
