# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to Semantic Versioning.

---

## [Phase 1: Outcome Tracking & Persistent Storage] - 2026-11-18

### Added
- **SQLite Database Persistence (`db.py`)**:
  - Implemented `output/scanner.db` with WAL mode, foreign keys, and 5 core tables: `flags`, `outcomes`, `deals`, `holidays`, and `run_log`.
  - Idempotent upserts on `(symbol, scan_date, run_type)` for flags, `(flag_id, horizon_days)` for outcomes, and `(date, symbol, client_name, side)` for deals.
  - Text SQL dump generation (`output/scanner.sql`) via `conn.iterdump()` for diffable version history.
  - Automated CSV export synchronization (`suspicious_master.csv`, `news_driven_master.csv`, `unexplained_master.csv`).
- **NSE Trading Holiday Calendar (`holidays.py` & `data/nse_holidays_2026.json`)**:
  - Accurate NSE trading day arithmetic (`is_trading_day`, `get_next_trading_day`, `get_previous_trading_day`, `count_trading_days`).
  - Supports 2026 official NSE Cash Market trading holidays with automatic weekend and holiday skipping.
- **Outcome Tracker Engine (`tracker.py`)**:
  - Evaluates flags across horizons $T+1, T+2, T+3, T+5, T+10$ trading days.
  - Forward returns measured strictly from **Next-Day Open** ($T+1$ Open) to evaluate real-world trade execution feasibility.
  - Excess return benchmarked against Nifty Midcap 150 (`NIFTYMIDCAP150.NS`) and Nifty 500 (`^CRSLDX`).
  - Corporate announcement detection and classification: distinguishes material filings (results, board intimations, dividends, acquisitions, order wins, fund raise) from routine disclosures (newspaper ads, loss of certificates, AGM notices).
  - Unflagged control group sampling (10 stocks per scan) and statistical **lift** calculation:
    $$\text{Lift} = \frac{\text{Precision}_{\text{flagged}}}{\text{Precision}_{\text{control}}}$$
- **CLI Tracker Command (`main.py`)**:
  - Added `python main.py --track` CLI argument to execute outcome evaluation directly.
- **Enhanced HTML Reporting (`report.py`)**:
  - Added "Outcome Tracking & Catalyst Hit Rate" dashboard section.
  - Displays 10-day precision, control group precision, statistical lift factor, average forward return, and benchmark excess return.
  - Added score bucket return breakdown table and recent resolved flags table with links to verified exchange disclosures.
- **Historical Migration Script (`scripts/migrate_csv_to_db.py`)**:
  - Ingested 156 historical records from legacy CSV master files into `output/scanner.db`.
- **Orphan `data` Branch Architecture (`.github/workflows/scan.yml`)**:
  - Separated persistent data storage (`scanner.db`, `scanner.sql`, master CSVs) onto the orphan `data` branch.
  - Added automated monthly squash workflow to compress git history on the `data` branch.
  - Concurrency control and retry-on-conflict logic for data branch pushes.
- **Comprehensive Pytest Suite (`tests/`)**:
  - 18 unit tests covering database schema & idempotent upserts, trading holiday date math, forward return calculations from next-day open, announcement classification, and control group lift.
