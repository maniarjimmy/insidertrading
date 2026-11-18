"""
Insider Activity Scanner — Configuration
All tuneable parameters and system paths are centralized here.
"""

import logging
import os
import sys
from typing import List

# ── Stock Universe ──────────────────────────────────────────────────────────
UNIVERSE_FILE = os.path.join(os.path.dirname(__file__), "data", "nifty500.csv")
RANK_START = 210   # inclusive
RANK_END = 500     # inclusive (NIFTY 500 covers up to rank 500)

# ── Scanner Thresholds ──────────────────────────────────────────────────────
MIN_PCT_CHANGE = 4.0       # minimum price % change to flag (positive only)
MAX_PCT_CHANGE = 15.0      # ignore moves > this % (likely circuit / operator pump)
MIN_VOLUME_RATIO = 2.0     # current volume / 20-day avg volume
VOLUME_HISTORY_DAYS = 30   # calendar days to fetch for computing 20-day avg volume

# ── News Verification ──────────────────────────────────────────────────────
NEWS_LOOKBACK_HOURS = 24   # search window for news articles
NEWS_SEARCH_DELAY = 2.0    # seconds between Google News requests (rate limit)
NEWS_MAX_RESULTS = 5       # max articles to retrieve per stock

# ── Scheduling ──────────────────────────────────────────────────────────────
SCAN_TIME = "14:30"        # IST — 2:30 PM (market closes at 3:30 PM)

# ── Output & Persistent Storage (Phase 1) ────────────────────────────────────
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
DB_PATH = os.path.join(OUTPUT_DIR, "scanner.db")
DB_SQL_DUMP_PATH = os.path.join(OUTPUT_DIR, "scanner.sql")
HOLIDAYS_FILE = os.path.join(os.path.dirname(__file__), "data", "nse_holidays_2026.json")

# Master CSV Export Files
SUSPICIOUS_MASTER_CSV = os.path.join(OUTPUT_DIR, "suspicious_master.csv")
NEWS_DRIVEN_MASTER_CSV = os.path.join(OUTPUT_DIR, "news_driven_master.csv")
UNEXPLAINED_MASTER_CSV = os.path.join(OUTPUT_DIR, "unexplained_master.csv")

# ── Outcome Tracking & Hit Rate (Phase 1) ────────────────────────────────────
TRACKING_HORIZONS: List[int] = [1, 2, 3, 5, 10]    # Trading day evaluation horizons (T+N)
TRACKING_MIN_DAYS = 1                             # Flags older than 1 trading day
TRACKING_MAX_DAYS = 15                            # Flags younger than 15 trading days
CONTROL_SAMPLE_SIZE = 10                          # Unflagged control group stocks per scan

# Primary benchmark ticker for abnormal returns (Nifty Midcap 150), with fallbacks
BENCHMARK_TICKERS: List[str] = ["NIFTYMIDCAP150.NS", "^CRSLDX", "^NSEI"]
DEFAULT_BENCHMARK = "NIFTYMIDCAP150.NS"

# Material corporate announcements vs routine disclosures
MATERIAL_ANNOUNCEMENT_KEYWORDS: List[str] = [
    "financial result",
    "financial results",
    "board meeting",
    "dividend",
    "acquisition",
    "merger",
    "amalgamation",
    "takeover",
    "order win",
    "award of contract",
    "contract win",
    "fund raise",
    "fund raising",
    "qip",
    "preferential issue",
    "rights issue",
    "bonus issue",
    "credit rating",
    "commercial production",
    "regulatory approval",
    "usfda",
    "fda approval",
    "patent",
    "joint venture",
    "demerger",
    "expansion",
    "strategic alliance",
    "allotment of shares",
]

ROUTINE_ANNOUNCEMENT_KEYWORDS: List[str] = [
    "loss of share certificate",
    "loss of share certificates",
    "duplicate share certificate",
    "newspaper publication",
    "newspaper advertisement",
    "investor presentation",
    "earnings call transcript",
    "audio recording",
    "compliance certificate",
    "shareholding pattern",
    "closure of trading window",
    "trading window closure",
    "annual general meeting",
    "agm",
    "egm",
    "secretarial audit",
    "clarification on price movement",
    "change in directors",
    "resignation",
    "re-appointment",
]

# ── Network & Resiliency ────────────────────────────────────────────────────
REQUEST_MAX_RETRIES = 3
REQUEST_BACKOFF_FACTOR = 1.5
REQUEST_TIMEOUT = 12

# ── yfinance Batch Settings ─────────────────────────────────────────────────
BATCH_SIZE = 20            # stocks per yfinance batch request
BATCH_DELAY = 1.0          # seconds between batches

# ── Logging Setup ───────────────────────────────────────────────────────────
def setup_logging(name: str = "scanner", level: int = logging.INFO) -> logging.Logger:
    """Centralized logger configuration with clean timestamped formatting."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(level)
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger
