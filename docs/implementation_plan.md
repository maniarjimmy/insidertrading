# Insider Activity Scanner — Implementation Plan

Detect suspicious stock moves in Indian mid/small-cap stocks (market cap rank 210–600) by scanning for **positive price moves with abnormal volume but no public news** — a signal of potential insider-driven trading.

## User Review Required

> [!IMPORTANT]
> **Stock Universe**: We'll use stocks ranked 210–600 by market cap. The simplest reliable approach is to download the **NIFTY 500 CSV** from [niftyindices.com](https://www.niftyindices.com/indices/equity/broad-based-indices/NIFTY-500) and use stocks ranked 210–500. For ranks 501–600, we can supplement with a screener-based list or accept the 210–500 range. **Which do you prefer?**

> [!IMPORTANT]
> **News Verification Limitation**: The `GNews` library searches Google News. It won't catch WhatsApp/Telegram leaks or broker-channel-only news. Some false positives are inevitable. We'll mitigate by also checking for **upcoming board meetings / result dates** (available from BSE announcements), but this requires additional scraping effort. **Should we include this in v1 or add it later?**

> [!WARNING]
> **yfinance Intraday Limitation**: `yfinance` provides near-real-time quotes but is not a true real-time feed. There may be a **5–15 minute delay**. For a production-grade system, you'd want a broker API (Zerodha Kite, Angel One, etc.). For now, yfinance is sufficient as a free starting point.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                    main.py (Orchestrator)            │
│   Runs at 2:30 PM IST via scheduler / manual run    │
├─────────────┬──────────────┬────────────┬───────────┤
│ universe.py │  scanner.py  │ news.py    │ report.py │
│ Stock list  │  Price/Vol   │ News check │ Output    │
│ (210-600)   │  analysis    │ (GNews)    │ HTML/CSV  │
└─────────────┴──────────────┴────────────┴───────────┘
```

### Data Flow
1. **universe.py** → Load stock list (from local CSV, rank 210–600)
2. **scanner.py** → For each stock, fetch current price vs prev close & volume vs 20-day avg
3. Filter: **price change ≥ 2%** AND **volume ratio ≥ 2x** (configurable)
4. **news.py** → For each flagged stock, search Google News for last 24h
5. Filter: remove stocks with recent news
6. **report.py** → Generate HTML + CSV report of suspicious stocks

---

## Proposed Changes

### Project Setup

#### [NEW] [requirements.txt](file:///C:/Users/mania/.gemini/antigravity/scratch/insider-scanner/requirements.txt)
Dependencies:
- `yfinance` — price/volume data
- `pandas` — data manipulation
- `gnews` — Google News search
- `schedule` — optional scheduler for 2:30 PM auto-run
- `jinja2` — HTML report generation

---

### Stock Universe Module

#### [NEW] [universe.py](file:///C:/Users/mania/.gemini/antigravity/scratch/insider-scanner/universe.py)
- Load the NIFTY 500 stock list from a local CSV file (`data/nifty500.csv`)
- Filter stocks by rank (210–600 or 210–500 based on available data)
- Return a list of `{symbol, company_name, industry}` dicts
- Symbol format: `SYMBOL.NS` for yfinance compatibility

#### [NEW] [data/nifty500.csv](file:///C:/Users/mania/.gemini/antigravity/scratch/insider-scanner/data/nifty500.csv)
- Downloaded from NSE India / niftyindices.com
- We'll create a representative sample for development/testing
- User should update this periodically with the latest list

---

### Price & Volume Scanner

#### [NEW] [scanner.py](file:///C:/Users/mania/.gemini/antigravity/scratch/insider-scanner/scanner.py)
- `scan_stocks(symbols: list) → DataFrame`
  - Fetches current quote (price, volume, prev close) via `yfinance`
  - Fetches 20-day historical volume to compute average
  - Computes: `pct_change = (current - prev_close) / prev_close * 100`
  - Computes: `volume_ratio = current_volume / avg_20d_volume`
- `filter_movers(df, min_pct=2.0, min_vol_ratio=2.0) → DataFrame`
  - Returns only stocks meeting both thresholds
- Batch processing to avoid API rate limits (chunks of 20 stocks)

---

### News Verification

#### [NEW] [news.py](file:///C:/Users/mania/.gemini/antigravity/scratch/insider-scanner/news.py)
- `check_news(company_name: str, symbol: str) → dict`
  - Searches Google News via `GNews` for the company name
  - Filters results from last 24 hours  
  - Returns `{has_news: bool, headlines: list[str], urls: list[str]}`
- `classify_stocks(flagged_df) → (suspicious_df, news_driven_df)`
  - Splits flagged stocks into "suspicious" (no news) and "explained" (has news)
- Rate limiting: 2-second delay between news searches to avoid blocks

---

### Report Generator

#### [NEW] [report.py](file:///C:/Users/mania/.gemini/antigravity/scratch/insider-scanner/report.py)
- `generate_report(suspicious_df, news_driven_df, timestamp) → str`
  - Produces a clean HTML report with two tables:
    1. **🔴 Suspicious Stocks** (no news, potential insider activity)
    2. **🟢 News-Driven Movers** (explained moves, for reference)
  - Columns: Symbol, Company, Price Change %, Volume Ratio, Sector, News Headlines
- `save_csv(df, path)` — CSV export for further analysis
- Reports saved to `output/` directory with timestamp

---

### Main Orchestrator

#### [NEW] [main.py](file:///C:/Users/mania/.gemini/antigravity/scratch/insider-scanner/main.py)
- `run_scan()` — Full pipeline: universe → scan → news check → report
- CLI arguments:
  - `--min-pct` — Minimum price change % (default: 2.0)
  - `--min-vol-ratio` — Minimum volume ratio (default: 2.0)
  - `--output-dir` — Output directory (default: `output/`)
- Optional: `--schedule` flag to auto-run at 2:30 PM IST daily
- Console summary printed after scan completes

---

### Configuration

#### [NEW] [config.py](file:///C:/Users/mania/.gemini/antigravity/scratch/insider-scanner/config.py)
- Centralized configuration:
  - `MIN_PCT_CHANGE = 2.0`
  - `MIN_VOLUME_RATIO = 2.0`
  - `SCAN_TIME = "14:30"` (IST)
  - `UNIVERSE_FILE = "data/nifty500.csv"`
  - `RANK_START = 210`
  - `RANK_END = 600`
  - `NEWS_LOOKBACK_HOURS = 24`
  - `OUTPUT_DIR = "output/"`

---

## Project Structure
```
insider-scanner/
├── main.py              # Entry point & orchestrator
├── config.py            # All configurable parameters
├── universe.py          # Stock universe loader
├── scanner.py           # Price/volume scanner
├── news.py              # News verification via GNews
├── report.py            # HTML & CSV report generator
├── requirements.txt     # Python dependencies
├── data/
│   └── nifty500.csv     # Stock universe (user-maintained)
└── output/              # Generated reports land here
```

---

## Verification Plan

### Automated Tests
1. **Module-level smoke test**: Run `python main.py --help` to confirm CLI works
2. **Scanner test**: Run `python -c "from scanner import scan_stocks; print(scan_stocks(['RELIANCE.NS', 'TCS.NS']))"` to verify price/volume fetch
3. **News test**: Run `python -c "from news import check_news; print(check_news('Reliance Industries', 'RELIANCE'))"` to verify news lookup
4. **Full pipeline**: Run `python main.py` and inspect `output/` for the HTML report and CSV

### Manual Verification
1. After running the full scan, **open the generated HTML report** in a browser
2. Cross-check 2–3 flagged stocks manually:
   - Verify the price change % matches what's shown on NSE/Moneycontrol
   - Verify volume is indeed abnormally high
   - Search Google News for the stock — confirm no news exists
3. Check that news-driven movers actually have relevant news headlines
