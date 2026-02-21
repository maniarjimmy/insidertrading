"""
Insider Activity Scanner — Configuration
All tuneable parameters are centralized here.
"""

import os

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

# ── Output ──────────────────────────────────────────────────────────────────
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")

# ── yfinance Batch Settings ─────────────────────────────────────────────────
BATCH_SIZE = 20            # stocks per yfinance batch request
BATCH_DELAY = 1.0          # seconds between batches
