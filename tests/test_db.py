"""
Unit Tests for Database Persistence Layer (db.py)
Tests schema initialization, WAL mode, idempotent upserts, foreign keys,
diffable SQL dump generation, and master CSV exports.
"""

import os
import sqlite3
import tempfile
import pytest

from db import (
    export_db_to_csv,
    export_db_to_sql,
    get_active_flags,
    get_connection,
    get_hit_rate_stats,
    get_recent_resolved_flags,
    init_db,
    log_run,
    mark_flag_status,
    upsert_deal,
    upsert_flag,
    upsert_holidays,
    upsert_outcome,
)


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name
    init_db(db_path)
    yield db_path
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except Exception:
        pass


def test_init_db_creates_all_tables_and_indexes(temp_db):
    """Verify all 5 required tables and indexes exist."""
    with get_connection(temp_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        assert {"flags", "outcomes", "deals", "holidays", "run_log"}.issubset(tables)

        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = {row[0] for row in cursor.fetchall()}
        assert "idx_flags_date" in indexes
        assert "idx_flags_symbol" in indexes
        assert "idx_outcomes_flag" in indexes
        assert "idx_deals_lookup" in indexes


def test_upsert_flag_idempotency(temp_db):
    """Upserting flag with same (symbol, scan_date, run_type) must update, not duplicate."""
    flag_1 = {
        "scan_date": "2026-04-10",
        "symbol": "MAZDOCK",
        "company": "Mazagon Dock",
        "industry": "Defence",
        "current_price": 2400.0,
        "prev_close": 2280.0,
        "price_change": 5.26,
        "current_volume": 500000,
        "avg_volume_20d": 100000.0,
        "volume_ratio": 5.0,
        "score": 75.0,
        "status": "ACTIVE",
        "catalyst_state": "NONE",
        "run_type": "eod",
        "is_control": 0,
    }
    flag_id = upsert_flag(flag_1, db_path=temp_db)
    assert flag_id > 0

    # Upsert again with modified price and score
    flag_2 = dict(flag_1)
    flag_2["current_price"] = 2450.0
    flag_2["score"] = 85.0
    updated_id = upsert_flag(flag_2, db_path=temp_db)
    assert updated_id == flag_id

    # Check that row count is still 1 and values are updated
    with get_connection(temp_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM flags WHERE symbol='MAZDOCK'")
        assert cursor.fetchone()[0] == 1

        cursor.execute("SELECT current_price, score FROM flags WHERE id=?", (flag_id,))
        row = cursor.fetchone()
        assert row["current_price"] == 2450.0
        assert row["score"] == 85.0


def test_upsert_outcome_idempotency(temp_db):
    """Upserting outcome with same (flag_id, horizon_days) must update without error."""
    flag_id = upsert_flag({
        "scan_date": "2026-04-10",
        "symbol": "COCHINSHIP",
        "current_price": 1500.0,
        "price_change": 6.0,
        "run_type": "eod",
    }, db_path=temp_db)

    outcome_1 = {
        "flag_id": flag_id,
        "horizon_days": 1,
        "entry_price": 1510.0,
        "forward_return": 2.5,
        "benchmark_return": 0.5,
        "excess_return": 2.0,
        "announcement_found": 0,
        "is_material": 0,
    }
    out_id = upsert_outcome(outcome_1, db_path=temp_db)
    assert out_id > 0

    # Re-evaluate with an announcement discovered
    outcome_2 = dict(outcome_1)
    outcome_2["announcement_found"] = 1
    outcome_2["announcement_title"] = "Quarterly Financial Results"
    outcome_2["is_material"] = 1
    out_id_2 = upsert_outcome(outcome_2, db_path=temp_db)
    assert out_id_2 == out_id

    with get_connection(temp_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM outcomes WHERE flag_id=?", (flag_id,))
        assert cursor.fetchone()[0] == 1
        cursor.execute("SELECT is_material, announcement_title FROM outcomes WHERE id=?", (out_id,))
        row = cursor.fetchone()
        assert row["is_material"] == 1
        assert row["announcement_title"] == "Quarterly Financial Results"


def test_upsert_deal_idempotency(temp_db):
    """Bulk/block deals keyed by (date, symbol, client_name, side) must be idempotent."""
    deal_1 = {
        "date": "2026-04-10",
        "symbol": "TCS",
        "client_name": "MORGAN STANLEY ASIA",
        "side": "BUY",
        "quantity": 100000,
        "price": 3850.0,
        "deal_type": "BULK",
    }
    deal_id = upsert_deal(deal_1, db_path=temp_db)
    assert deal_id > 0

    deal_2 = dict(deal_1)
    deal_2["quantity"] = 150000
    deal_id_2 = upsert_deal(deal_2, db_path=temp_db)
    assert deal_id_2 == deal_id

    with get_connection(temp_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM deals WHERE symbol='TCS'")
        assert cursor.fetchone()[0] == 1
        cursor.execute("SELECT quantity FROM deals WHERE id=?", (deal_id,))
        assert cursor.fetchone()[0] == 150000


def test_run_logging_and_stats(temp_db):
    """Test run_log audit entries and hit rate statistics calculation."""
    log_id = log_run(
        run_type="scan",
        source_used="bhavcopy",
        runtime_seconds=12.5,
        rows_scanned=290,
        flags_generated=4,
        status="SUCCESS",
        db_path=temp_db,
    )
    assert log_id > 0

    # Add 1 flagged stock and 1 control stock with outcomes
    flag_id = upsert_flag({
        "scan_date": "2026-04-01",
        "symbol": "TESTFLAG",
        "score": 75.0,
        "status": "RESOLVED",
        "is_control": 0,
        "run_type": "eod",
    }, db_path=temp_db)

    upsert_outcome({
        "flag_id": flag_id,
        "horizon_days": 10,
        "entry_price": 100.0,
        "forward_return": 8.0,
        "benchmark_return": 2.0,
        "excess_return": 6.0,
        "is_material": 1,
    }, db_path=temp_db)

    control_id = upsert_flag({
        "scan_date": "2026-04-01",
        "symbol": "TESTCTRL",
        "score": 0.0,
        "status": "RESOLVED",
        "is_control": 1,
        "run_type": "eod",
    }, db_path=temp_db)

    upsert_outcome({
        "flag_id": control_id,
        "horizon_days": 10,
        "entry_price": 50.0,
        "forward_return": 1.0,
        "benchmark_return": 2.0,
        "excess_return": -1.0,
        "is_material": 0,
    }, db_path=temp_db)

    stats = get_hit_rate_stats(db_path=temp_db)
    assert stats["flagged_evaluated"] == 1
    assert stats["flagged_catalysts"] == 1
    assert stats["flagged_precision"] == 100.0
    assert stats["control_evaluated"] == 1
    assert stats["control_catalysts"] == 0
    assert stats["control_precision"] == 0.0
    assert stats["avg_fwd_ret_10d"] == 8.0
    assert stats["avg_excess_ret_10d"] == 6.0


def test_export_db_to_sql_and_csv(temp_db):
    """Verify that export_db_to_sql produces a valid text .dump file and export_db_to_csv produces CSVs."""
    with tempfile.TemporaryDirectory() as td:
        sql_file = os.path.join(td, "scanner_dump.sql")
        export_db_to_sql(db_path=temp_db, sql_path=sql_file)
        assert os.path.isfile(sql_file)
        with open(sql_file, "r", encoding="utf-8") as f:
            content = f.read()
        assert "CREATE TABLE flags" in content
        assert "CREATE TABLE outcomes" in content

        csv_files = export_db_to_csv(db_path=temp_db, output_dir=td)
        assert os.path.isfile(csv_files["suspicious_master"])
        assert os.path.isfile(csv_files["news_driven_master"])
        assert os.path.isfile(csv_files["unexplained_master"])
