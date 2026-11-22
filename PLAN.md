# Insider Activity Scanner — Engineering Roadmap & Implementation Plan

## Executive Summary
This document outlines the architectural transformation of the **Insider Activity Scanner** (Indian mid/small-cap NSE equities) from an initial prototype into an institutional-grade, statistically rigorous, and resilient market intelligence system.

---

## Architecture & Workflow Strategy

### Branching & Environment Rules
* **Branch Strategy**: Development is executed strictly on `feature/scanner-upgrade`. The `main` branch is untouched and unmerged by automated tasks.
* **Persistent State**: The `data` orphan branch is the single source of truth for `scanner.db` and master exports. Daily reports will not be committed to `main`.
* **Execution Budget**: Designed for `ubuntu-latest` within GitHub's free tier (target < 1,000 Actions minutes/month), with explicit per-job timeouts and runtime logging.
* **Network & Feasibility**: Every external endpoint (NSE/BSE/Bhavcopy) is validated from GitHub Actions runners in Phase 0 before building dependent phases.

---

## Phased Implementation Sequence

```mermaid
flowchart TD
    P0[Phase 0:<br/>Endpoint Feasibility Spike<br/>Actions Validation] --> P1[Phase 1:<br/>Outcome Tracking<br/>& SQLite DB on data branch]
    P1 --> P2[Phase 2:<br/>Catalyst Detection<br/>Exchange Filings]
    P2 --> P5[Phase 5:<br/>Data Correctness,<br/>EOD Bhavcopy, Schedule]
    P5 --> P5b[Phase 5b:<br/>Historical Event Study<br/>12-24 Mo Backtest]
    P5b --> P4[Phase 4:<br/>India Microstructure,<br/>Delivery % & Deals]
    P4 --> P3[Phase 3:<br/>Signals & Scoring,<br/>Robust Z-Scores]
    P3 --> P6[Phase 6:<br/>Unexplained Movers,<br/>Report UI & CI/CD]
```

### Phase 0: Endpoint Feasibility Spike (Actions Runner Verified)
**Objective**: Empirically verify every prospective NSE/BSE public endpoint, Bhavcopy URL, and RSS feed from a GitHub Actions `ubuntu-latest` runner to detect geo-blocking, Akamai challenges, or IP bans before writing application logic.

**Verified Results from GitHub Runner Runs #44275991733 and #44277610196 (`ubuntu-latest`)**:
* **16/17 Endpoints Tested**: 16 Passed with valid JSON/CSV formatting and required fields present (1 expected unready: today's Bhavcopy returning 404 prior to EOD publication; yesterday's Bhavcopy returned HTTP 200 with 3,572 rows).
* **Bhavcopy Timing & Schedule Calibration**:
  - `sec_bhavdata_full_<DDMMYYYY>.csv` has `Last-Modified: 18:25 GMT` (23:55 IST). It returns 404 before midnight on NSE archives.
  - Official UDDiP Bhavcopy (`BhavCopy_NSE_CM_0_0_0_<YYYYMMDD>_F_0000.csv.zip`) and Delivery Position (`MTO_<DDMMYYYY>.DAT`) are published after market close.
  - Daily logging of `Last-Modified` headers for UDDiP, MTO, bulk, and block deals is active across 5 consecutive trading days to empirically establish publication timing before locking the EOD schedule (provisional target: 17:30–18:00 IST).
  - Extended spike on GitHub Actions will run after 17:00 IST on the next trading day for live runner verification of UDDiP, MTO, and multi-symbol date ranges.
* **Surveillance (ASM / GSM) & Price Bands**:
  - `sec_list.csv` confirmed (3,609 securities; GSM stages 0, 1, 2 for 67 stocks; 329 T2T series `BE`/`BZ`/`ST`; circuit bands: 2%, 5%, 10%, 20%, No Band).
  - ST-ASM/LT-ASM lists are published via circulars API `/api/circulars` (subject strings: "ST-ASM", "ASM").
* **BSE Dynamic APIs**: `/BseIndiaAPI/api/AnnSubCategoryGetData/w` verified functional as primary fallback, supports multi-day `strPrevDate/strToDate` spans and pagination (`pageno=1,2,3...` with 50+ records/page).
* **Completeness**:
  - NSE announcements by symbol/date range returns up to 1,779 historical items without truncation when symbol is supplied.
  - Event calendar returns all forward items in the specified 7-day window.

**Data Source & Fallback Architecture Matrix**:
| Data Requirement | Primary Source (Actions Verified) | Secondary Fallback | Failure Graceful Mode |
| :--- | :--- | :--- | :--- |
| **Market-Cap Universe** | `archives.nseindia.com` Index CSVs | Local cached `data/nifty500.csv` | Slices available local universe |
| **EOD Price & Delivery** | NSE UDDiP / Bhavcopy | `yfinance` history (`period="1d"`) | Delivery % marked `None`, log warning |
| **Corporate Filings** | NSE API `/api/corporate-announcements` | BSE API `AnnSubCategoryGetData/w` | Google News RSS / Catalyst `UNCLEAR` |
| **Upcoming Board Mtgs** | NSE API `/api/event-calendar` | BSE API `BoardMeeting/w` | Pre-announcement radar skipped |
| **Trading Holidays** | NSE API `/api/holiday-master` | Static `data/nse_holidays_2026.json` | Fallback to hardcoded Mon-Fri rules |
| **Bulk & Block Deals** | NSE `bulk.csv` & `block.csv` | Direct scrape if available | Tag skipped, composite score ignores deals |
| **Market Data Fallback** | `yfinance` (`NIFTYMIDCAP150.NS`) | NSE Bhavcopy EOD | Log skipped symbol |

---

### Phase 1: Outcome Tracking & Persistent Storage (COMPLETED)
**Objective**: Build a persistent evaluation loop measuring forward returns and hit rates against a benchmark and a random control sample.

1. **Storage Architecture (`output/scanner.db` on `data` branch)**:
   - Orphan `data` branch established as primary storage for `scanner.db` and exports.
   - Core tables implemented: `flags`, `outcomes`, `deals`, `holidays`, and `run_log`.
   - Idempotent upsert constraints: `UNIQUE(symbol, scan_date, run_type)` on flags, `UNIQUE(flag_id, horizon_days)` on outcomes, `UNIQUE(date, symbol, client_name, side)` on deals.
   - Diffable SQLite `.dump` generation (`output/scanner.sql`) for auditability.
2. **NSE Trading Holiday Calendar (`holidays.py` & `data/nse_holidays_2026.json`)**:
   - Official 2026 NSE Equities trading holidays incorporated.
   - Trading day arithmetic functions (`is_trading_day`, `get_next_trading_day`, `get_previous_trading_day`, `count_trading_days`).
3. **Outcome Evaluator & Control Sample (`tracker.py`)**:
   - Forward returns measured strictly from **next-day open** ($T+1$ Open) to evaluate realistic execution feasibility.
   - Evaluates horizons $T+1, T+2, T+3, T+5, T+10$ trading days against Nifty Midcap 150 benchmark (`NIFTYMIDCAP150.NS`).
   - Categorizes corporate filings into material vs routine disclosures.
   - Evaluates random 10-stock control group per scan to compute baseline precision and statistical **lift**.
4. **Report Integration (`report.py`)**:
   - Added visual "Outcome Tracking & Catalyst Hit Rate" dashboard section.
   - Metrics: 10-day precision, control precision, lift factor, average forward return, average excess return.
   - Score bucket breakdown table and recent resolved flags table with links to verified exchange disclosures.
5. **CLI & Migration**:
   - CLI command `python main.py --track`.
   - Migration script `scripts/migrate_csv_to_db.py` migrated 156 historical records and 775 outcome records into `output/scanner.db`.
   - Full test coverage with 18 pytest unit tests.

---

### Phase 2: Catalyst Detection from Exchange Filings (COMPLETED)
**Objective**: Primary catalyst classification from exchange disclosures, supplemented by Google News.

1. **Filing Ingestion & Fallback Architecture (`filings.py`)**:
   * Official NSE corporate announcements API as primary source.
   * BSE dynamic API (`AnnSubCategoryGetData/w`) as secondary fallback.
   * Mapped 495/501 Nifty 500 equities by ISIN to BSE 6-digit scrip codes (`data/nse_to_bse_mapping.json`).
2. **Unified Catalyst Classifier (`classify_catalyst`)**:
   * Single standardized function used both at scan detection time and outcome evaluation time in the tracker.
   * Priority 1: Exact / normalized exchange `desc` category matching.
   * Priority 2: Text rules with routine-priority filtering for ambiguous categories (`Updates`, `General`, news headlines).
   * Three-valued catalyst state: `CATALYST` / `UNCLEAR` / `NONE`, plus materiality flag (`is_material` 1 | 0) and normalized category name.
   * State is decoupled from the statistical anomaly score.
3. **Benchmark Fixtures (`tests/fixtures/filings_fixtures.json`)**:
   * 50 real-world exchange disclosures curated from SQLite outcomes.
   * 25 training fixtures: 100.0% precision, 100.0% recall, 100.0% accuracy.
   * 25 strictly held-out test fixtures: 100.0% precision (0 false positives), 92.9% recall, 96.0% accuracy, F1 = 0.963.
4. **Pre-Announcement Radar Check**:
   * Evaluates NSE Event Calendar API (`/api/event-calendar`) for scheduled board meetings in the next 7 days.
5. **Efficiency & Budget**:
   * In-memory filing cache (`_FILINGS_CACHE`) and persistent session reuse eliminate redundant network calls and Akamai session handshakes.
   * Request throttling (0.15s) respects rate limits and Actions runner budgets.
6. **Matched Control Baseline & Statistical Findings**:
   * Nearest-neighbor quintile matching on 20-day average turnover and 60-day return volatility.
   * **Empirical Results & Lift Significance**:
     - **All Material Catalysts (3-day pre-move window)**: Clean unexplained pairs $N = 118$. Flag precision: 27.12% (32/118), Control precision: 36.44% (43/118). Unpaired lift: 0.74x (95% CI: [0.51, 1.08]). Paired discordance: $n_{10} = 19$ (flag only), $n_{01} = 30$ (control only). Paired odds ratio = 0.63. McNemar stat = 2.04 ($p = 0.153$), exact binomial sign test $p = 0.1524$. Conclusion: **No evidence of a positive edge** over matched controls.
     - **Unscheduled Deficit (Exploratory Only)**: Unscheduled-material precision was 13.56% for flags vs. 24.58% for controls ($p = 0.0470$ at 3-day; $p = 0.0639$ at 10-day). This deficit is reported as strictly **exploratory**, not a finding, due to multiple testing across horizons and category splits ($\ge 6$ comparisons, where Bonferroni-corrected threshold is $\alpha \approx 0.0083$).
     - **Sensitivity Bounds**:
       * *Baseline (UNCLEAR as non-material)*: $N=99$ clean pairs, Flag 30.3% vs Ctrl 38.4%, Lift 0.79x, Odds 0.69, $p=0.2912$.
       * *Bound A (UNCLEAR as material - upper bound)*: $N=47$ clean pairs, Flag 63.8% vs Ctrl 61.7%, Lift 1.03x, Odds 1.11, $p=1.000$.
       * *Strictly Unique Controls (sampled without replacement across all dates)*: $N=66$ clean pairs, Flag 31.8% vs Ctrl 31.8%, Lift 1.00x, Odds 1.00, $p=1.000$.
     - **Sample Note**: The current 156 historical flags (Feb–May 2026) represent **development and tuning data only, not out-of-sample evidence**. Pre-move classification results represent "no material filing per our classifier (upper bound)".

---

### Phase 5: Data Correctness & Scheduling
*(Executed before Phase 4 & 3 so signal modeling is built on clean, validated EOD data)*

1. **Corporate Action Adjustment**:
   * Adjust historical prices for stock splits, bonuses, and rights.
   * Exclude or tag stocks within 2 business days of an ex-date.
2. **Bhavcopy as Primary EOD, yfinance as Fallback**:
   * Clean validation layer (check missing candles, stale timestamps, zero volume).
   * Audit log of skipped symbols.
3. **Dual-Tier Schedule with Actions Drift Awareness**:
   * Intraday run at 14:30 IST (early alert) and main EOD run at 17:00 IST (with final Bhavcopy and delivery).
   * Explicit job timeouts (e.g. 15 minutes) and runtime logging to ensure monthly usage stays well within the 1,000-minute free tier budget.
4. **Dynamic Universe & Microcap Support**:
   * Script to update constituents from NiftyIndices semi-annual revisions with rank slice config and `--microcap` flag.

---

### Phase 5b: Historical Event Study & 12–24 Month Backtest
**Objective**: Build a historical backtest spanning 12–24 months using verified archived exchange data to measure signal efficacy, baseline announcement rates, and matched control lift across multiple market regimes and earnings seasons.

1. **Archive Feasibility & Availability (Empirically Verified)**:
   * **UDDiP Bhavcopy Archive**: Official ZIP files (`BhavCopy_NSE_CM_0_0_0_YYYYMMDD_F_0000.csv.zip`) verified HTTP 200 on NSE public archives across 12-month and 24-month lookbacks.
   * **Security Delivery Position**: `MTO_DDMMYYYY.DAT` verified HTTP 200 across 12-month and 24-month archives.
   * **Corporate Actions**: Historical ex-dates and adjustment factors available via `/api/corporates-corporateActions`.
   * **Corporate Announcements**: NSE API `/api/corporate-announcements` by symbol and date range returns up to 2 years of filings without truncation.
2. **Local Execution & Budget Isolation**:
   * **Strictly Local**: Run entirely on local workstations via CLI (`python scripts/run_historical_backtest.py`), consuming **0 GitHub Actions runner minutes**.
   * **Storage Footprint**: Cached daily Bhavcopy ZIPs (~1 MB/day = ~250 MB/year, ~500 MB for 24 months).
   * **Runtime & Throttling**: Batch downloads with session reuse and disk caching run in 15–30 minutes locally.
3. **Rigorous Signal Evaluation & Pre-Registration (prereg-v5)**:
   * **Provenance Manifest & Formal Retraction (Item 1, 3 & 6 Audit)**:
     - The earlier 20-row precision audit table presented in Round 8 (referencing CIPLA, TRENT, BEL, HAVELLS, POLYCAB, DIXON, APOLLOHOSP, MAXHEALTH, L&TFH) is **formally retracted**.
     - An exhaustive audit of `output/scanner.db` (`output/audit/provenance_manifest_8367e6e.txt`) confirmed that only POLYCAB (Flag ID 140) and TRENT (Flag ID 21) exist in `flags` (both with 0 controls in DB); the remaining 7 symbols have 0 occurrences across `flags`, `outcomes`, and `controls`.
     - Git log and blame inspection (`git log -S`) confirmed zero commits ever generated that table; it was an exploratory synthetic draft querying live APIs across arbitrary members. All repository metrics are backed strictly by committed scripts and saved audit outputs in `output/audit/`.
     - Contradiction corrections formally adopted: Flags status is 1 ACTIVE / 155 RESOLVED in `scanner.db`; Confusion matrix DB truth is 111 News-Driven / 44 Unexplained (35 pre-move catalysts at [T-3, T]); Matched-control lift for unexplained flags is 0.62x (not 1.18x); and untracked scripts (`migrate_legacy_data.py`, `verify_tracker_and_horizons.py`) are formally marked RETRACTED.

   * **Threshold Origin, Original Scanner Defaults & Signal Specification (Item 4 & 5)**:
     - **Original Production Defaults (`main:config.py`)**: `MIN_PCT_CHANGE = 4.0` (positive only: `pct_change >= MIN_PCT_CHANGE`), `MAX_PCT_CHANGE = 15.0`, `MIN_VOLUME_RATIO = 2.0`, `VOLUME_HISTORY_DAYS = 30`.
     - **Retraction of False Attribute**: `MIN_DELIVERY_PCT` and `MIN_TURNOVER_CR` **NEVER existed on `main`**. Any prior claim attributing them to `main:config.py` was factually false and is hereby retracted.
     - **Primary Signal (LIVE Scanner Defaults)**:
       - **Primary Signal**: Signed up-move breakout: $r_{\text{day}} \ge +4.0\%$ with $V / \text{SMA}_{20}(V) \ge 2.0\text{x}$. Directly tests the live scanner's production rule.
       - **Secondary Pre-Registered Variant**: $r_{\text{day}} \ge +3.0\%$ with $V / \text{SMA}_{20}(V) \ge 2.5\text{x}$ (introduced in commit `d8edf37`).
       - **Exploratory Signal**: Down-move breakdowns ($r_{\text{day}} \le -4.0\%$).
     - Delivery percentage and composite score are unvalidated Phase 3/4 concepts and are strictly excluded from the primary signal.

   * **Amended Pre-Registered Success Rule & Outcomes (Item 1 & Item 5g)**:
     - **Pre-Registered Success Criterion**: **One-sided paired $p < 0.05$ for $\text{Lift} > 1.0$ (with 95% confidence interval reported)**.
     - **Role of 1.25x Lift**: The $1.25\text{x}$ threshold is strictly the **sample sizing target**, NOT a decision gate. (Requiring observed $\ge 1.25\text{x}$ AND $p < 0.05$ would yield only $\sim 50\%$ power even when the true underlying lift is $1.25\text{x}$).
     - **Primary Outcome (Binary)**: Occurrence of $\ge 1$ **unscheduled-material corporate filing** (orders/contracts, M&A/acquisition/disinvestment, fundraising/preferential issue, commercial production milestones, regulatory actions, credit rating revisions; strictly excluding scheduled financial results and board meetings) within **10 trading days ($T+1..T+10$)** evaluated under `classifier-v2`.
     - **Statistical Test**: One-sided paired test (paired McNemar test / exact binomial sign test on discordant pairs $n_{10} > n_{01}$) at pre-registered significance level $\alpha = 0.05$.
     - **Secondary Outcome (High-Power Continuous Metric)**: Total **count of unscheduled-material filings** in $T+1..T+10$, tested via paired Wilcoxon signed-rank test.
     - **Inconclusive Result Threshold**: Any null result ($p \ge 0.05$) obtained at statistical power $<80\%$ is reported strictly as **INCONCLUSIVE**, not as evidence of absence of edge.

   * **Control Base Rate Estimation & Statistical Power (Item 5c & Item 7)**:
     - **Independent Base Rate Estimation (N = 3,000)**: Control base rate estimated from **3,000 random non-flag stock-days across 2021–2025** (600/yr across 30 universe symbols, evaluated under `classifier-v2`).
     - **Empirical Base Rate ($P_0$)**: $P_0 = 11.83\%$ ($95\%$ Wilson CI: $[10.65\%, 13.13\%]$, $N=2,628$ clean stock-days).
     - **Stage 1 Dry Count on 2024 (Flags only, NO outcomes)**:
       - Observed raw flags: ~384 flags/year (~32/month).
       - Pre-move clean retention: ~72.5% ([T-3, T] clean).
       - Unique control retention: ~90% (capped at $\le 3\text{x}$/yr).
       - Expected clean pairs per year: $384 \times 0.725 \times 0.90 \approx 250$ pairs/year.
     - **60-Month Primary Evaluation Window (2021–2026)**:
       - Expected Clean Matched Pairs: $5 \times 250 \approx 1,250$ clean pairs.
       - Achieved Statistical Power at $N=1,250$ for true $\text{Lift} = 1.30\text{x}$ ($P_1 = 15.38\%$): $\approx 74.2\%$.
       - Achieved Statistical Power at $N=1,250$ for true $\text{Lift} = 1.25\text{x}$ ($P_1 = 14.79\%$): $\approx 60.5\%$.
       - Split-half 30-month subsets ($N \approx 625$ pairs) are pre-registered as **EXPLORATORY / CONSISTENCY CHECKS**; primary inference is pooled across all 60 months.

   * **Deterministic Text-Only Classifier (classifier-v2, Item 2)**:
     - **Specification**: Evaluated strictly under `classifier-v2` (`classify_catalyst_v2`: `desc + attchmntText`, zero PDF extraction, zero network requests).
     - **Concordance**: 99.87% identical classification vs v1 (8,549 / 8,560 cached records). Exactly 7 records shift from CATALYST to UNCLEAR due to absence of PDF text.
     - **Reliability**: Eliminates all 7,261 PDF cache misses (0 misses by design). attchmntText is 100% populated in 2026 cache and 100% populated in sampled 2021–2025 exchange records.

   * **Control Uniqueness & Covariate Balance (Item 5b)**:
     - **Uniqueness Rules**: Zero reuse of the same symbol on the same scan date; symbol reuse capped at $\le 3\text{x}$ per symbol per calendar year across all scan dates.
     - **Covariate Balance Acceptance Criterion**: Standardized Mean Difference ($\text{SMD} < 0.10$) across 20-day Turnover, 60-day Volatility, and $\log(\text{Close})$. Verified before unblinding Stage 2 outcomes.

   * **Surveillance, Circuit Proxy & Exclusion Rules (Item 5a)**:
     - **Historical Data Availability**: Continuous ASM lists and daily price band files are UNAVAILABLE on public NSE endpoints. Continuous ASM and continuous price band exclusions are therefore **NOT applied in the backtest**.
     - **Circuit Day Proxy Rule**: Circuit days approximated from daily OHLCV: move $|r_{\text{day}}| \ge 4.90\%$ (or $9.85\%$ / $19.85\%$) AND intraday range $(\text{High} - \text{Low}) / \text{Close} < 0.20\%$ AND volume $< 0.25 \times \text{SMA}_{20}(V)$. Excluded from flags and entry.
     - **Exclusions Applied**: Ex-date $\pm 2$ trading days of corporate actions (splits, bonuses, rights); partial/abnormal sessions; 5-trading-day repeat-flag cooldown.

   * **Backtest Span, Data Formats & Timing Schedule (Item 4 & 5d)**:
     - **Primary Evaluation Span**: **2021-01-01 through 2026-01-31 (61 calendar months, ~1,250 trading days)**. Quarantined development data: Feb 1, 2026 – May 31, 2026 (and Nov 2026).
     - **Data Formats**: 2021–2023 (`sec_bhavdata_full_DDMMYYYY.csv` + `MTO_DDMMYYYY.DAT`, delivery % for BE stored as `NULL`); 2024–2026 (UDDiP `BhavCopy_NSE_CM_0_0_0_YYYYMMDD_F_0000.csv.zip` + `MTO_DDMMYYYY.DAT`). Split-adjusted via audited internal adjuster (`scripts/audit_real_splits.py`), NEVER yfinance.
     - **Scan Timing & Scheduling**: Authoritative server publication verified: UDDiP posts at ~16:33 IST; MTO posts at 16:49–17:03 IST; bulk/block/sec_list post at 18:30–19:30 IST. Primary EOD scan scheduled for **20:00 IST** (daily logger window) when all settlement files are guaranteed published. Early scan at 17:15 IST with retry loop (17:30, 17:45, 18:00, 18:30, 19:00, 19:30, 20:00 IST).

   * **Two-Stage Run Protocol & Stage 1 Stopping Gate (Item 5f)**:
     - **Stage 1 (Signal & Control Generation - Zero Outcomes)**:
       - Run historical scanner on raw bhavcopies: flags ($r_{\text{day}} \ge +4.0\%, V \ge 2.0\text{x}$) and matched controls (turnover + volatility quintiles, unique $\le 3\text{x}$/yr).
       - Evaluate pre-move cleanliness in $[T-3, T\text{ 17:15 IST}]$ under `classifier-v2`.
       - Output immutable artifact `output/backtest_stage1_flags_controls.csv`. Record SHA-256 hash.
       - **Stage 1 Gate Check**: Compute raw flags/yr, clean pairs, covariate balance (SMD $< 0.10$), and exact power for $1.25\text{x}$ and $1.30\text{x}$.
       - **Stage 1 Stopping Rule**: If achieved statistical power for $1.25\text{x}$ is $< 70\%$, the test must either be extended or labeled strictly **EXPLORATORY** before unblinding Stage 2 outcomes.
     - **Stage 2 (Outcome Evaluation & Inference)**:
       - Ingest locked Stage 1 artifact, fetch forward announcements in $[T+1, T+10]$, apply `classifier-v2`, and compute paired McNemar and Wilcoxon tests. Zero re-tuning after Stage 1 unblinding.

   * **Operational Abort/Retry Rule for 17:15 IST Pass (Item 8)**:
     - At 17:15 IST, verify availability of UDDiP Bhavcopy and MTO delivery files (HTTP 200).
     - If either returns 404, retry at 17:30, 17:45, and 18:00 IST.
     - If at 18:00 IST files are still unavailable, abort scan with alert log `DATA_NOT_READY_AT_1800` and fall back to scheduled evening pass at 19:30 IST. No partial or corrupted scans.

   * **Standardized Operational Backtest Rules**:
     1. **EOD Flag Thresholds (Primary Signal)**:
        - Daily price return: $|r_{\text{day}}| \ge 3.0\%$
        - Volume ratio: $V / \text{SMA}_{20}(V) \ge 2.5\text{x}$
     2. **Matching Algorithm & Tolerance**:
        - Each flag on scan date $T$ is paired with 1 matched control from the eligible universe on the SAME scan date $T$.
        - Exact matching on 20-day Average Daily Turnover quintile ($\pm 20\%$ tolerance) and 60-day historical volatility quintile ($\pm 20\%$ tolerance).
        - Controls are sampled strictly without replacement across all scan dates to eliminate repeat-control correlation.
     3. **Repeat-Flag Cooldown**:
        - 5-trading-day cooldown on the same symbol: if a symbol triggers multiple flags within 5 trading days, only the initial flag is retained.
     4. **Exclusions**:
        - *Corporate Actions*: Flags occurring within ex-date $\pm 2$ trading days of any stock split, bonus issue, or rights issue are strictly excluded.
        - *Partial Sessions*: Truncated / abnormal sessions (Muhurat trading, disaster recovery Saturday sessions) are tagged `partial_session` and excluded from event studies and $T+N$ counting.
        - *Surveillance Lists*: Securities in Long-term ASM or Stage 2+ GSM on scan date $T$ are excluded.
        - *Circuit Limit Days*: Days where the stock touches upper/lower circuit and does not trade freely (zero volume or close at circuit tick) are excluded.
     5. **Clean-Pair Definition**:
        - Both flag stock and matched control stock must have NO material filing in the pre-move window $[T-3, T\text{ 17:15 IST}]$.
        - Both must have verified $T+1$ Open entry price and full $T+1..T+10$ historical candle history.
     6. **Overlap & Clustering Handling**:
        - Statistical inference incorporates cluster bootstrap by scan date (B=1,000) and cluster grouping by symbol to correct for cross-sectional market clustering.
     7. **Minimum Liquidity Floor**:
        - 20-day average daily turnover $\ge \text{INR } 5\text{ Cr}$ ($\approx \$600\text{k}$ USD equivalent).
     8. **Classifier Hash & Settings**:
        - Classifier version locked at Git tag `classifier-v1` (`3f603a1`).
        - Parameter setting: `parse_pdf = True` (cached locally in `output/cache/pdf_text_cache.json`, throttled).
   * **Standardized Table Window Labels**: Every contingency and lift table must explicitly state both:
     - **Pre-Move Window**: $[T-3, T\text{ 17:15 IST}]$ (baseline 3 calendar days prior to scan) or $[T-10, T\text{ 17:15 IST}]$ (10 calendar days sensitivity).
     - **Forward Horizon Window**: $[T+1, T+10]$ (primary 10 trading days) or $[T+1, T+3]$ (secondary 3 trading days).
   * **Per-Symbol Announcements Caching**: Persistent local disk caching of raw corporate announcements by symbol (`output/cache/announcements/<symbol>.json`) to eliminate redundant HTTP calls across repeated backtest runs.
   * Filter pre-move filings strictly before each flag timestamp.
   * Compute forward returns ($T+1$ Open to $T+10$) and corporate announcement lift vs. liquidity/volatility quintile-matched controls.
   * Report both paired and unpaired lift disaggregated by scheduled vs. unscheduled-material outcomes, with scan-date cluster bootstrap confidence intervals.
   * Use findings to empirically calibrate Phase 4 and Phase 3 filters before deployment.

---

### Phase 4: India-Specific Market Microstructure Data
1. **NSE Bhavcopy Delivery Data**:
   * Ingest official delivery quantity; compute Delivery % and 20-day rolling delivery z-score.
2. **Bulk & Block Deals**:
   * Parse daily bulk and block deals; match against flagged symbols and extract counterparties.
3. **Surveillance & Circuits**:
   * Ingest ASM/GSM surveillance lists and circuit bands (2%, 5%, 10%, 20%). Flag surveillance membership rather than dropping stocks.

---

### Phase 3: Better Signal and Scoring
1. **Residual-Volatility Return Z-Score**:
   * Abnormal return vs. index benchmark ($R_i - R_m$).
   * Normalized by stock's residual volatility (idiosyncratic volatility over 60 days).
2. **Robust Volume Z-Score & Intraday U-Curve**:
   * Volume baseline using median and MAD (Median Absolute Deviation) instead of mean/std:
     $$\text{Robust } Z_{vol} = \frac{\ln(V_t) - \text{median}(\ln(V_{20d}))}{1.4826 \cdot \text{MAD}(\ln(V_{20d}))}$$
   * Time-of-day normalization using empirical U-shaped intraday volume profile.
3. **Multi-day Creeping Accumulation**:
   * Cumulative abnormal return and volume over $t-10$ to $t-1$.
4. **Composite Score (0–100 Mapping)**:
   * Sigmoid / Min-Max normalized composite score mapping purely statistical factors (catalyst state kept separate).
   * Factor attribution breakdown per stock.
   * Walk-forward parameter calibration.
5. **Liquidity Filter & Deduplication**:
   * Turnover floor (ADTV in INR) and $N$-day suppression unless score spikes $\ge 20\%$.

---

### Phase 6: Reporting, Housekeeping & CI/CD
1. **Rebranding & Legal Disclaimer**:
   * Rename "Suspicious Movers" to "Unexplained Movers" across all files, templates, CLI, and exports.
   * Add disclaimer: *"Statistical screen only. Not evidence of wrongdoing. Not investment advice."*
2. **Dashboard UI Updates**:
   * Score breakdown, delivery %, forward return tracking, and direct links to exchange filings.
3. **Repository Cleanliness**:
   * Stop committing daily reports/CSVs to `main`. Sync SQLite DB and exports directly to the orphan `data` branch.
4. **CI/CD Pipeline**:
   * GitHub Actions workflow running `pytest` with coverage on every push to feature branches.
