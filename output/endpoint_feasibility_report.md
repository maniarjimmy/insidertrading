# Phase 0: Endpoint & Data Source Feasibility Report
**Run Timestamp**: 2026-11-18 14:50:00 UTC
**Total Tested**: 14 | **Passed**: 14 | **Failed**: 0

| Category | Endpoint / Source | Status | Latency | Result / Sample Preview |
| :--- | :--- | :---: | :---: | :--- |
| 1. NSE Index Lists | NSE Index - NIFTY 100 | ✅ `200` | 350.6 ms | CSV (101 lines, header: Company Name,Industry,Symbol,Series,ISIN Code...) |
| 1. NSE Index Lists | NSE Index - Midcap 150 | ✅ `200` | 277.9 ms | CSV (151 lines, header: Company Name,Industry,Symbol,Series,ISIN Code...) |
| 1. NSE Index Lists | NSE Index - Smallcap 250 | ✅ `200` | 308.8 ms | CSV (252 lines, header: Company Name,Industry,Symbol,Series,ISIN Code...) |
| 1. NSE Index Lists | NSE Index - NIFTY 500 | ✅ `200` | 296.7 ms | CSV (502 lines, header: Company Name,Industry,Symbol,Series,ISIN Code...) |
| 2. Bhavcopy & Delivery | NSE Full Bhavcopy (2026-11-17) | ✅ `200` | 342.3 ms | CSV (3573 lines, header: SYMBOL, SERIES, DATE1, PREV_CLOSE, OPEN_PRICE, HIGH_PRICE, L...) |
| 3. Deals & Surveillance | NSE Bulk Deals CSV | ✅ `200` | 335.5 ms | CSV (123 lines, header: Date,Symbol,Security Name,Client Name,Buy/Sell,Quantity Trad...) |
| 3. Deals & Surveillance | NSE Block Deals CSV | ✅ `200` | 292.2 ms | CSV (62 lines, header: Date,Symbol,Security Name,Client Name,Buy/Sell,Quantity Trad...) |
| 4. NSE Dynamic APIs | NSE Corporate Announcements API | ✅ `200` | 96.8 ms | JSON Array (20 items) |
| 4. NSE Dynamic APIs | NSE Event Calendar (Board Meetings / Results) | ✅ `200` | 79.0 ms | JSON Array (13 items) |
| 4. NSE Dynamic APIs | NSE Corporate Actions API | ✅ `200` | 125.7 ms | JSON Array (20 items) |
| 4. NSE Dynamic APIs | NSE Trading Holidays Master | ✅ `200` | 136.5 ms | JSON Dict (keys: ['CBM', 'CD', 'CM', 'CMOT', 'COM']) |
| 5. BSE Dynamic APIs | BSE Announcements API (20261117) | ✅ `200` | 529.9 ms | JSON Dict (keys: ['Table', 'Table1']) |
| 6. News & Fallback Feeds | Google News RSS (Reliance 1d) | ✅ `200` | 611.2 ms | <?xml version="1.0" encoding="UTF-8" standalone="yes"?><rss version="2.0" xmlns:media="http://search |
| 7. Market Data Fallback | yfinance (RELIANCE.NS fast_info & history) | ✅ `200` | 1815.0 ms | lastPrice: 1360.2, 3d candles: 3 |

---
### Architectural Implications & Feasibility Findings

1. **Bhavcopy & Delivery Data**: `sec_bhavdata_full_<DDMMYYYY>.csv` is completely accessible with direct HTTP 200 without blocking. This confirms Bhavcopy as a reliable primary source for Phase 4 and Phase 5.
2. **Index Constituents**: All NSE Index CSVs (NIFTY 100, Midcap 150, Smallcap 250, NIFTY 500) succeed with HTTP 200, enabling clean market-cap segmentation.
3. **Corporate Filings**: Both NSE Corporate Announcements API (`/api/corporate-announcements`) and NSE Event Calendar (`/api/event-calendar`) succeed with 200 when pre-warmed with home session cookies. BSE Announcements (`/BseIndiaAPI/api/AnnSubCategoryGetData/w`) provides a viable JSON fallback.
4. **Bulk / Block Deals**: Public CSVs on `archives.nseindia.com` succeed with HTTP 200.
5. **News & Market Data**: Google News RSS and yfinance both respond with HTTP 200 and low latency.
