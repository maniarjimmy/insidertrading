# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to Semantic Versioning.

---

## [Phase 5: Data Correctness, Corporate Actions & UDDiP Primary Source] - 2026-11-18

### Added
- **Corporate Actions Adjustment & Ex-Date Detection (`corporate_actions.py`)**:
  - Ingestion of corporate actions from NSE public endpoint (`/api/corporates-corporateActions?index=equities`) with disk caching.
  - Parsing of corporate action purpose strings (splits, bonuses, rights, dividends) and computation of exact structural adjustment ratios.
  - Proximity detection: identifies whether a target date is within $\pm 2$ trading days of an ex-date.
  - Backward historical price and volume adjustment engine for OHLCV candles.
- **UDDiP Bhavcopy & Delivery Position Ingestion (`bhavcopy.py`)**:
  - Primary EOD market data ingestion from official NSE UDDiP Bhavcopy (`BhavCopy_NSE_CM_0_0_0_YYYYMMDD_F_0000.csv.zip`).
  - Official delivery quantity and percentage extraction from Security Delivery Position files (`MTO_DDMMYYYY.DAT`).
  - Resilient graceful fallback to `yfinance` with Parquet/JSON caching.
- **Data Quality & Validation Layer (`data_quality.py`)**:
  - Validates candles for missing/zero close, inverted OHLC bounds, and zero volume on active trading days.
  - Identifies extreme price discontinuities ($>25\%$) and cross-references against corporate actions to distinguish legitimate ex-date moves from bad data.
  - Structured audit logging to `output/data_quality_audit.log`.
- **Expanded Holiday Coverage (`holidays.py`, `data/nse_holidays_2024.json`, `data/nse_holidays_2025.json`)**:
  - Added official NSE trading holidays for 2024 and 2025 to enable multi-year event studies.
  - Updated `holidays.py` to union database and file-based holiday sets across all years.
- **Unit Test Suite (`tests/test_corporate_actions.py`, `tests/test_bhavcopy_and_quality.py`)**:
  - Added 9 new unit tests covering action purpose parsing, ex-date window detection, backward price adjustment, candle validation, extreme price move handling, and data auditing (35 total tests passing).

---

## [Phase 2: Catalyst Detection from Exchange Filings] - 2026-11-18

### Added
- **Corporate Filings Module (`filings.py`)**:
  - Direct ingestion of corporate disclosures from the official NSE API (`/api/corporate-announcements`).
  - Resilient secondary fallback to BSE API (`/BseIndiaAPI/api/AnnSubCategoryGetData/w`).
  - Pre-generated symbol and ISIN mapping (`data/nse_to_bse_mapping.json`) mapping 495 Nifty 500 equities to BSE 6-digit scrip codes.
  - Pre-announcement radar querying upcoming board meetings and corporate events within the next 7 days via `/api/event-calendar`.
  - In-memory filing cache (`_FILINGS_CACHE`) and persistent session reuse to eliminate duplicate requests and respect rate limits.
- **Unified Catalyst & Materiality Classifier (`classify_catalyst`)**:
  - One standardized classifier function shared across detection pipeline (`scanner.py`, `news.py`) and tracker (`tracker.py`).
  - Categorizes using NSE `desc` category first, with routine-priority regex pattern fallback for ambiguous descriptions.
  - Three-valued output state: `CATALYST` / `UNCLEAR` / `NONE`, with `is_material` (1 | 0) and normalized category name.
  - Fully decoupled catalyst state from the statistical anomaly score.
- **Matched Control Group Evaluation (`scripts/generate_matched_controls.py`)**:
  - Implemented nearest-neighbor quintile matching on 20-day average turnover and 60-day return volatility.
  - Evaluated lift of unexplained flags vs both random controls (0.75x) and matched controls (0.62x).
- **Benchmark Fixtures & Test Suite (`tests/test_filings.py` & `tests/fixtures/filings_fixtures.json`)**:
  - Curated 50 real-world exchange disclosures split 50/50 into training and held-out evaluation sets.
  - Achieved 100% precision, 100% recall on training set; 100% precision, 92.9% recall, 96.0% accuracy on strictly held-out set.
  - Added unit tests for BSE symbol mapping, event-calendar radar, and caching.

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
