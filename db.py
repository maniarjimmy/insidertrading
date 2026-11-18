"""
Database Engine & Persistence Layer (Phase 1)
Manages SQLite database (output/scanner.db), WAL mode, idempotent upserts,
diffable SQL dump generation, and backward-compatible CSV exports.
"""

from contextlib import contextmanager
from datetime import datetime
import logging
import os
import sqlite3
from typing import Any, Dict, Generator, List, Optional, Tuple

import pandas as pd

from config import (
    DB_PATH,
    DB_SQL_DUMP_PATH,
    NEWS_DRIVEN_MASTER_CSV,
    OUTPUT_DIR,
    SUSPICIOUS_MASTER_CSV,
    UNEXPLAINED_MASTER_CSV,
    setup_logging,
)

logger = setup_logging("db")


def get_db_path(db_path: Optional[str] = None) -> str:
    """Return normalized DB path, ensuring parent directory exists."""
    path = db_path or DB_PATH
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    return path


@contextmanager
def get_connection(db_path: Optional[str] = None) -> Generator[sqlite3.Connection, None, None]:
    """Context manager for SQLite connections with WAL mode and foreign keys enabled."""
    path = get_db_path(db_path)
    conn = sqlite3.connect(path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 30000")
        yield conn
        conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.error("DB transaction failed: %s", exc)
        raise
    finally:
        conn.close()


def init_db(db_path: Optional[str] = None) -> None:
    """
    Initialize SQLite schema for flags, outcomes, deals, holidays, and run_log.
    Creates unique indexes for idempotent upserts.
    """
    path = get_db_path(db_path)
    logger.info("Initializing scanner database at %s", path)

    with get_connection(path) as conn:
        cursor = conn.cursor()

        # 1. Flags table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS flags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_date TEXT NOT NULL,
                symbol TEXT NOT NULL,
                company TEXT,
                industry TEXT,
                current_price REAL,
                prev_close REAL,
                price_change REAL,
                current_volume INTEGER,
                avg_volume_20d REAL,
                volume_ratio REAL,
                score REAL DEFAULT 0.0,
                status TEXT DEFAULT 'ACTIVE',
                catalyst_state TEXT DEFAULT 'NONE',
                delivery_pct REAL,
                run_type TEXT NOT NULL DEFAULT 'eod',
                is_control INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, scan_date, run_type)
            )
        """)

        # 2. Outcomes table (T+1 to T+10 forward evaluation)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                flag_id INTEGER NOT NULL REFERENCES flags(id) ON DELETE CASCADE,
                horizon_days INTEGER NOT NULL,
                entry_price REAL,
                forward_return REAL,
                benchmark_return REAL,
                excess_return REAL,
                announcement_found INTEGER DEFAULT 0,
                announcement_type TEXT,
                is_material INTEGER DEFAULT 0,
                announcement_date TEXT,
                announcement_title TEXT,
                announcement_url TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(flag_id, horizon_days)
            )
        """)

        # 3. Deals table (Bulk & Block deals daily snapshot)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS deals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                symbol TEXT NOT NULL,
                client_name TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity INTEGER,
                price REAL,
                deal_type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date, symbol, client_name, side)
            )
        """)

        # 4. Holidays table (NSE trading holidays)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS holidays (
                date TEXT PRIMARY KEY,
                holiday_description TEXT,
                trading_holiday INTEGER DEFAULT 1
            )
        """)

        # 5. Run log table (Execution metadata and audit trail)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS run_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                run_type TEXT NOT NULL,
                source_used TEXT,
                runtime_seconds REAL,
                rows_scanned INTEGER DEFAULT 0,
                flags_generated INTEGER DEFAULT 0,
                status TEXT NOT NULL,
                error_message TEXT
            )
        """)

        # Performance Indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_flags_date ON flags(scan_date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_flags_symbol ON flags(symbol)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_flags_status ON flags(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_flags_control ON flags(is_control)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_outcomes_flag ON outcomes(flag_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_deals_lookup ON deals(date, symbol)")


def upsert_flag(flag_data: Dict[str, Any], db_path: Optional[str] = None) -> int:
    """
    Idempotently insert or update a flag in the `flags` table.
    Returns the flag's primary key `id`.
    """
    path = get_db_path(db_path)
    sql = """
        INSERT INTO flags (
            scan_date, symbol, company, industry, current_price, prev_close,
            price_change, current_volume, avg_volume_20d, volume_ratio,
            score, status, catalyst_state, delivery_pct, run_type, is_control
        ) VALUES (
            :scan_date, :symbol, :company, :industry, :current_price, :prev_close,
            :price_change, :current_volume, :avg_volume_20d, :volume_ratio,
            :score, :status, :catalyst_state, :delivery_pct, :run_type, :is_control
        )
        ON CONFLICT(symbol, scan_date, run_type) DO UPDATE SET
            company = excluded.company,
            industry = excluded.industry,
            current_price = excluded.current_price,
            prev_close = excluded.prev_close,
            price_change = excluded.price_change,
            current_volume = excluded.current_volume,
            avg_volume_20d = excluded.avg_volume_20d,
            volume_ratio = excluded.volume_ratio,
            score = excluded.score,
            status = excluded.status,
            catalyst_state = excluded.catalyst_state,
            delivery_pct = excluded.delivery_pct,
            is_control = excluded.is_control
        RETURNING id
    """
    data = {
        "scan_date": flag_data["scan_date"],
        "symbol": flag_data["symbol"],
        "company": flag_data.get("company", ""),
        "industry": flag_data.get("industry", ""),
        "current_price": flag_data.get("current_price"),
        "prev_close": flag_data.get("prev_close"),
        "price_change": flag_data.get("price_change", flag_data.get("pct_change", 0.0)),
        "current_volume": flag_data.get("current_volume", 0),
        "avg_volume_20d": flag_data.get("avg_volume_20d", 0.0),
        "volume_ratio": flag_data.get("volume_ratio", 0.0),
        "score": flag_data.get("score", 0.0),
        "status": flag_data.get("status", "ACTIVE"),
        "catalyst_state": flag_data.get("catalyst_state", "NONE"),
        "delivery_pct": flag_data.get("delivery_pct"),
        "run_type": flag_data.get("run_type", "eod"),
        "is_control": flag_data.get("is_control", 0),
    }

    with get_connection(path) as conn:
        cursor = conn.cursor()
        cursor.execute(sql, data)
        row = cursor.fetchone()
        return row[0] if row else -1


def upsert_outcome(outcome_data: Dict[str, Any], db_path: Optional[str] = None) -> int:
    """
    Idempotently insert or update an outcome record in `outcomes`.
    Returns the outcome's primary key `id`.
    """
    path = get_db_path(db_path)
    sql = """
        INSERT INTO outcomes (
            flag_id, horizon_days, entry_price, forward_return,
            benchmark_return, excess_return, announcement_found,
            announcement_type, is_material, announcement_date,
            announcement_title, announcement_url, updated_at
        ) VALUES (
            :flag_id, :horizon_days, :entry_price, :forward_return,
            :benchmark_return, :excess_return, :announcement_found,
            :announcement_type, :is_material, :announcement_date,
            :announcement_title, :announcement_url, CURRENT_TIMESTAMP
        )
        ON CONFLICT(flag_id, horizon_days) DO UPDATE SET
            entry_price = excluded.entry_price,
            forward_return = excluded.forward_return,
            benchmark_return = excluded.benchmark_return,
            excess_return = excluded.excess_return,
            announcement_found = excluded.announcement_found,
            announcement_type = excluded.announcement_type,
            is_material = excluded.is_material,
            announcement_date = excluded.announcement_date,
            announcement_title = excluded.announcement_title,
            announcement_url = excluded.announcement_url,
            updated_at = CURRENT_TIMESTAMP
        RETURNING id
    """
    data = {
        "flag_id": outcome_data["flag_id"],
        "horizon_days": outcome_data["horizon_days"],
        "entry_price": outcome_data.get("entry_price"),
        "forward_return": outcome_data.get("forward_return"),
        "benchmark_return": outcome_data.get("benchmark_return"),
        "excess_return": outcome_data.get("excess_return"),
        "announcement_found": outcome_data.get("announcement_found", 0),
        "announcement_type": outcome_data.get("announcement_type"),
        "is_material": outcome_data.get("is_material", 0),
        "announcement_date": outcome_data.get("announcement_date"),
        "announcement_title": outcome_data.get("announcement_title"),
        "announcement_url": outcome_data.get("announcement_url"),
    }

    with get_connection(path) as conn:
        cursor = conn.cursor()
        cursor.execute(sql, data)
        row = cursor.fetchone()
        return row[0] if row else -1


def upsert_deal(deal_data: Dict[str, Any], db_path: Optional[str] = None) -> int:
    """
    Idempotently record a bulk/block deal in `deals`.
    """
    path = get_db_path(db_path)
    sql = """
        INSERT INTO deals (date, symbol, client_name, side, quantity, price, deal_type)
        VALUES (:date, :symbol, :client_name, :side, :quantity, :price, :deal_type)
        ON CONFLICT(date, symbol, client_name, side) DO UPDATE SET
            quantity = excluded.quantity,
            price = excluded.price,
            deal_type = excluded.deal_type
        RETURNING id
    """
    with get_connection(path) as conn:
        cursor = conn.cursor()
        cursor.execute(sql, deal_data)
        row = cursor.fetchone()
        return row[0] if row else -1


def upsert_holidays(holidays_list: List[Dict[str, Any]], db_path: Optional[str] = None) -> int:
    """
    Populate or update holiday records in `holidays`.
    """
    path = get_db_path(db_path)
    sql = """
        INSERT INTO holidays (date, holiday_description, trading_holiday)
        VALUES (:date, :description, :trading_holiday)
        ON CONFLICT(date) DO UPDATE SET
            holiday_description = excluded.holiday_description,
            trading_holiday = excluded.trading_holiday
    """
    count = 0
    with get_connection(path) as conn:
        cursor = conn.cursor()
        for item in holidays_list:
            cursor.execute(sql, {
                "date": item["date"],
                "description": item.get("description", item.get("holiday_description", "")),
                "trading_holiday": item.get("trading_holiday", 1),
            })
            count += 1
    return count


def log_run(run_type: str,
            source_used: str,
            runtime_seconds: float,
            rows_scanned: int = 0,
            flags_generated: int = 0,
            status: str = "SUCCESS",
            error_message: Optional[str] = None,
            db_path: Optional[str] = None) -> int:
    """
    Record pipeline execution metadata to `run_log`.
    """
    path = get_db_path(db_path)
    sql = """
        INSERT INTO run_log (
            run_type, source_used, runtime_seconds, rows_scanned,
            flags_generated, status, error_message
        ) VALUES (
            :run_type, :source_used, :runtime_seconds, :rows_scanned,
            :flags_generated, :status, :error_message
        ) RETURNING id
    """
    with get_connection(path) as conn:
        cursor = conn.cursor()
        cursor.execute(sql, {
            "run_type": run_type,
            "source_used": source_used,
            "runtime_seconds": runtime_seconds,
            "rows_scanned": rows_scanned,
            "flags_generated": flags_generated,
            "status": status,
            "error_message": error_message,
        })
        row = cursor.fetchone()
        return row[0] if row else -1


def get_active_flags(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Retrieve all flags marked 'ACTIVE' for forward return and announcement evaluation.
    """
    path = get_db_path(db_path)
    with get_connection(path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, scan_date, symbol, company, industry, current_price,
                   prev_close, price_change, current_volume, avg_volume_20d,
                   volume_ratio, score, status, catalyst_state, delivery_pct,
                   run_type, is_control
            FROM flags
            WHERE status = 'ACTIVE'
            ORDER BY scan_date ASC, id ASC
        """)
        return [dict(r) for r in cursor.fetchall()]


def mark_flag_status(flag_id: int, status: str, db_path: Optional[str] = None) -> None:
    """Update status of a flag ('ACTIVE', 'RESOLVED', 'EXPIRED')."""
    path = get_db_path(db_path)
    with get_connection(path) as conn:
        conn.execute("UPDATE flags SET status = ? WHERE id = ?", (status, flag_id))


def get_hit_rate_stats(db_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Calculate precision, lift vs control group, and forward return statistics.
    """
    path = get_db_path(db_path)
    stats: Dict[str, Any] = {
        "flagged_evaluated": 0,
        "flagged_catalysts": 0,
        "flagged_precision": 0.0,
        "control_evaluated": 0,
        "control_catalysts": 0,
        "control_precision": 0.0,
        "lift": 1.0,
        "avg_fwd_ret_10d": 0.0,
        "avg_excess_ret_10d": 0.0,
        "score_buckets": {},
    }

    with get_connection(path) as conn:
        cursor = conn.cursor()

        # Flagged stocks at horizon_days = 10 (or latest resolved)
        cursor.execute("""
            SELECT f.is_control, o.is_material, o.forward_return, o.excess_return, f.score
            FROM flags f
            JOIN outcomes o ON f.id = o.flag_id
            WHERE o.horizon_days = 10 AND o.entry_price IS NOT NULL
        """)
        rows = cursor.fetchall()

        flagged_rets = []
        flagged_excess = []
        score_bucket_data: Dict[str, List[float]] = {
            "High (Score ≥ 70)": [],
            "Medium (Score 50–69)": [],
            "Low (Score < 50)": [],
        }

        for r in rows:
            is_control = r["is_control"]
            is_material = r["is_material"]
            fwd_ret = r["forward_return"]
            excess = r["excess_return"]
            score = r["score"] or 0.0

            if is_control == 0:
                stats["flagged_evaluated"] += 1
                if is_material == 1:
                    stats["flagged_catalysts"] += 1
                if fwd_ret is not None:
                    flagged_rets.append(fwd_ret)
                if excess is not None:
                    flagged_excess.append(excess)

                # Score bucket
                if score >= 70:
                    bucket = "High (Score ≥ 70)"
                elif score >= 50:
                    bucket = "Medium (Score 50–69)"
                else:
                    bucket = "Low (Score < 50)"
                if fwd_ret is not None:
                    score_bucket_data[bucket].append(fwd_ret)

            else:
                stats["control_evaluated"] += 1
                if is_material == 1:
                    stats["control_catalysts"] += 1

        if stats["flagged_evaluated"] > 0:
            stats["flagged_precision"] = round(
                (stats["flagged_catalysts"] / stats["flagged_evaluated"]) * 100.0, 1
            )
        if stats["control_evaluated"] > 0:
            stats["control_precision"] = round(
                (stats["control_catalysts"] / stats["control_evaluated"]) * 100.0, 1
            )
            if stats["control_precision"] > 0:
                stats["lift"] = round(stats["flagged_precision"] / stats["control_precision"], 2)
            else:
                stats["lift"] = round(stats["flagged_precision"] / 1.0, 2) if stats["flagged_precision"] > 0 else 1.0

        if flagged_rets:
            stats["avg_fwd_ret_10d"] = round(sum(flagged_rets) / len(flagged_rets), 2)
        if flagged_excess:
            stats["avg_excess_ret_10d"] = round(sum(flagged_excess) / len(flagged_excess), 2)

        for bucket, rets in score_bucket_data.items():
            if rets:
                stats["score_buckets"][bucket] = {
                    "count": len(rets),
                    "avg_return": round(sum(rets) / len(rets), 2)
                }

    return stats


def get_recent_resolved_flags(limit: int = 15, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Fetch recently evaluated flags with their outcomes for display in the report.
    """
    path = get_db_path(db_path)
    with get_connection(path) as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT f.id, f.scan_date, f.symbol, f.company, f.price_change,
                   f.volume_ratio, f.score, f.status, f.is_control,
                   MAX(CASE WHEN o.horizon_days = 1 THEN o.entry_price END) as entry_price,
                   MAX(CASE WHEN o.horizon_days = 1 THEN o.forward_return END) as ret_1d,
                   MAX(CASE WHEN o.horizon_days = 3 THEN o.forward_return END) as ret_3d,
                   MAX(CASE WHEN o.horizon_days = 5 THEN o.forward_return END) as ret_5d,
                   MAX(CASE WHEN o.horizon_days = 10 THEN o.forward_return END) as ret_10d,
                   MAX(CASE WHEN o.horizon_days = 10 THEN o.excess_return END) as excess_10d,
                   MAX(o.is_material) as material_found,
                   MAX(o.announcement_title) as catalyst_title,
                   MAX(o.announcement_url) as catalyst_url
            FROM flags f
            LEFT JOIN outcomes o ON f.id = o.flag_id
            WHERE f.is_control = 0
            GROUP BY f.id
            ORDER BY f.scan_date DESC, f.id DESC
            LIMIT {int(limit)}
        """)
        return [dict(r) for r in cursor.fetchall()]


def export_db_to_sql(db_path: Optional[str] = None, sql_path: Optional[str] = None) -> str:
    """
    Generate a text .dump of the SQLite database for diffable version history on the data branch.
    """
    src_db = get_db_path(db_path)
    target_sql = sql_path or DB_SQL_DUMP_PATH
    os.makedirs(os.path.dirname(os.path.abspath(target_sql)), exist_ok=True)

    conn = sqlite3.connect(src_db)
    try:
        with open(target_sql, "w", encoding="utf-8") as f:
            for line in conn.iterdump():
                f.write(f"{line}\n")
    finally:
        conn.close()

    logger.info("Exported database text dump to %s", target_sql)
    return target_sql


def export_db_to_csv(db_path: Optional[str] = None, output_dir: Optional[str] = None) -> Dict[str, str]:
    """
    Export database records back into CSV files for backward compatibility:
    - output/suspicious_master.csv (flags where catalyst_state != 'CATALYST')
    - output/news_driven_master.csv (flags where catalyst_state == 'CATALYST')
    - output/unexplained_master.csv (unified modern export)
    """
    path = get_db_path(db_path)
    out_dir = output_dir or OUTPUT_DIR
    os.makedirs(out_dir, exist_ok=True)

    with get_connection(path) as conn:
        df = pd.read_sql_query("""
            SELECT scan_date as scan_timestamp,
                   symbol, company, industry, current_price, prev_close,
                   price_change as pct_change, current_volume, avg_volume_20d,
                   volume_ratio,
                   (CASE WHEN catalyst_state = 'CATALYST' THEN 1 ELSE 0 END) as has_catalyst_news,
                   catalyst_state as classification,
                   '' as headlines,
                   'database' as news_source,
                   score, delivery_pct, run_type, status
            FROM flags
            WHERE is_control = 0
            ORDER BY scan_date ASC, id ASC
        """, conn)

    suspicious_file = os.path.join(out_dir, "suspicious_master.csv")
    news_driven_file = os.path.join(out_dir, "news_driven_master.csv")
    unexplained_file = os.path.join(out_dir, "unexplained_master.csv")

    if not df.empty:
        # Backward-compatible column list
        legacy_cols = [
            "scan_timestamp", "symbol", "company", "industry",
            "current_price", "prev_close", "pct_change", "current_volume",
            "avg_volume_20d", "volume_ratio", "has_catalyst_news",
            "classification", "headlines", "news_source"
        ]

        suspicious_df = df[df["has_catalyst_news"] == 0]
        news_driven_df = df[df["has_catalyst_news"] == 1]

        suspicious_df[legacy_cols].to_csv(suspicious_file, index=False, encoding="utf-8")
        news_driven_df[legacy_cols].to_csv(news_driven_file, index=False, encoding="utf-8")
        df.to_csv(unexplained_file, index=False, encoding="utf-8")
    else:
        # Write headers if empty
        pd.DataFrame(columns=[
            "scan_timestamp", "symbol", "company", "industry",
            "current_price", "prev_close", "pct_change", "current_volume",
            "avg_volume_20d", "volume_ratio", "has_catalyst_news",
            "classification", "headlines", "news_source"
        ]).to_csv(suspicious_file, index=False, encoding="utf-8")

        pd.DataFrame(columns=[
            "scan_timestamp", "symbol", "company", "industry",
            "current_price", "prev_close", "pct_change", "current_volume",
            "avg_volume_20d", "volume_ratio", "has_catalyst_news",
            "classification", "headlines", "news_source"
        ]).to_csv(news_driven_file, index=False, encoding="utf-8")

        df.to_csv(unexplained_file, index=False, encoding="utf-8")

    logger.info("Updated CSV exports: %s, %s, %s", suspicious_file, news_driven_file, unexplained_file)
    return {
        "suspicious_master": suspicious_file,
        "news_driven_master": news_driven_file,
        "unexplained_master": unexplained_file,
    }
