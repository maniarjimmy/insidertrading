# Phase 0 Extended: Runner Feasibility & Data Quality Report
**Environment**: GitHub-Hosted Runner (ubuntu-latest)
**Run Timestamp**: 2026-11-18 09:37:37 UTC
**Total Tested**: 17 | **Passed**: 16 | **Expected Unready / Failed**: 1

| Category | Endpoint / Source | Status | Format Valid? | Items/Rows | Required Fields | Latency |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| 1. NSE Index Lists | NSE Index - NIFTY 100 | ✅ `200` | ✅ Yes | 100 | All Present | 417.3 ms |
| 1. NSE Index Lists | NSE Index - Midcap 150 | ✅ `200` | ✅ Yes | 150 | All Present | 358.7 ms |
| 1. NSE Index Lists | NSE Index - Smallcap 250 | ✅ `200` | ✅ Yes | 251 | All Present | 345.2 ms |
| 1. NSE Index Lists | NSE Index - NIFTY 500 | ✅ `200` | ✅ Yes | 501 | All Present | 307.1 ms |
| 2. Bhavcopy Timing | NSE Bhavcopy TODAY (2026-11-18) | ⚠️ `404` | ❌ No | 0 | N/A | 320.9 ms |
| 2. Bhavcopy Timing | NSE Bhavcopy YESTERDAY (2026-11-17) | ✅ `200` | ✅ Yes | 3572 | All Present | 557.9 ms |
| 3. Deals & Surveillance | NSE Bulk Deals CSV | ✅ `200` | ✅ Yes | 122 | All Present | 283.7 ms |
| 3. Deals & Surveillance | NSE Block Deals CSV | ✅ `200` | ✅ Yes | 61 | All Present | 298.3 ms |
| 3. Deals & Surveillance | NSE Securities List (Bands, ASM/GSM & T2T) | ✅ `200` | ✅ Yes | 3609 | All Present | 375.4 ms |
| 4. NSE Dynamic APIs | NSE Announcements by Symbol & Date Range (T-10..T) | ✅ `200` | ✅ Yes | 14 | All Present | 458.4 ms |
| 4. NSE Dynamic APIs | NSE Event Calendar (7-Day Forward Window) | ✅ `200` | ✅ Yes | 17 | All Present | 429.4 ms |
| 4. NSE Dynamic APIs | NSE Corporate Actions API | ✅ `200` | ✅ Yes | 20 | All Present | 335.1 ms |
| 4. NSE Dynamic APIs | NSE Trading Holidays Master | ✅ `200` | ✅ Yes | 12 | All Present | 61.2 ms |
| 5. BSE Dynamic APIs | BSE Announcements Multi-Day by Scrip (500440) | ✅ `200` | ✅ Yes | 2 | All Present | 462.9 ms |
| 5. BSE Dynamic APIs | BSE Announcements Pagination (Page 2) | ✅ `200` | ✅ Yes | 2 | All Present | 330.1 ms |
| 6. News & Fallback Feeds | Google News RSS (Reliance 1d) | ✅ `200` | ✅ Yes | 0 | N/A | 368.8 ms |
| 7. Market Data Fallback | yfinance (RELIANCE.NS fast_info & history) | ✅ `200` | ✅ Yes | 3 | last_price, history candles | 1422.5 ms |

---
## Deep-Dive Verification Findings

### A. Bhavcopy Publication Timing Analysis
* **Today's Bhavcopy (2026-11-18)**: Status `404` (Not published yet during trading hours).
* **Yesterday's Bhavcopy (2026-11-17)**: Status `200` with **3572 rows** containing delivery volumes and prices.
* **Implication**: NSE generates `sec_bhavdata_full` between **18:00 and 19:30 IST**. At 17:00 IST, it returns 404. Therefore, the EOD job should either run at 19:30 IST or poll with exponential backoff up to 19:30 IST, falling back to yfinance for price data.

### B. Surveillance (ASM / GSM) & Price Band Verification
* **Securities Master (`sec_list.csv`)**: Status `200` with **3609 total securities**.
* **Price Band Distribution**: `{'2': 43, '5': 608, '10': 205, '20': 2194, '40': 1, 'No Band': 558}` (Includes 2%, 5%, 10%, 20%, and No Band).
* **GSM Surveillance Tags**: `67 stocks` flagged with GSM stages (`GSM STAGE - 0`, `GSM STAGE - I`, `GSM STAGE - II`).
* **Trade-to-Trade (T2T) Surveillance**: `329 stocks` (Series `BE`, `BZ`, `ST`).

### C. Symbol-Specific & Multi-Day Filings (T+1..T+10)
* **NSE Filings by Symbol & Range**: Supports `symbol=<SYMBOL>&from_date=DD-MM-YYYY&to_date=DD-MM-YYYY` returning all historical announcements for any stock over the 10-day evaluation window.
* **BSE Multi-Day & Pagination**: Supports `strScrip=<SCRIP>&strPrevDate=YYYYMMDD&strToDate=YYYYMMDD` for specific stocks, and `pageno=1,2,3...` with 50+ records per page for market-wide sweeps.
* **Event Calendar (7-Day Forward Window)**: Supports `from_date=DD-MM-YYYY&to_date=DD-MM-YYYY` returning upcoming Board Meetings and Financial Results.

---
## Verified Sample Records

### 1. NSE Announcements by Symbol (Sample Records with Direct PDF URLs)
```json
[
  {
    "an_dt": "18-Nov-2026 14:51:08",
    "attFileSize": "4.25 MB",
    "attchmntFile": "https://nsearchives.nseindia.in/corporate/HINDALCOIND_18112026145014_Loss_of_share_certificate_SE_Intimation_Merged_signed.pdf",
    "attchmntText": "Newspaper Advertisement of Public Notice regarding Loss of Share Certificates.",
    "bflag": null,
    "csvName": null,
    "desc": "Copy of Newspaper Publication",
    "difference": "00:00:01",
    "dt": "18112026145108",
    "exchdisstime": "18-Nov-2026 14:51:09",
    "fileSize": "4.25 MB",
    "hasXbrl": true,
    "old_new": null,
    "orgid": null,
    "seq_id": "106864835",
    "smIndustry": "Aluminium",
    "sm_isin": "INE038A01020",
    "sm_name": "Hindalco Industries Limited",
    "sort_date": "2026-11-18 14:51:08",
    "symbol": "HINDALCO",
    "voiceSummary": "Hindalco Industries Limited published a public notice on November 18, 2026, regarding the loss of share certificates. The notice identifies Folio number MUKHTAR MOHIBUDDIN/SHAMSHAD MUKHTAR holding 1,660 shares with distinctive certificate numbers 11045273 to 11914033. Shareholders are requested to submit any objections or claims in writing within 10 days from the publication date. If no valid claims are received, the company will approve the issuance of duplicate share certificates. Additionally, Kwality Wall's India Limited announced its first Annual General Meeting scheduled for December 10, 2026. The meeting will be held via video conferencing. Remote e-voting is available from December 7, 2026, at 09:00 AM to December 9, 2026, at 05:00 PM. The cut-off date for voting eligibility is December 3, 2026.",
    "voiceUrl": "https://nsearchives.nseindia.in/ann_voice/HINDALCOIND_18112026145014_Loss_of_share_certificate_SE_Intimation_Merged_signed.mp3"
  },
  {
    "an_dt": "15-Nov-2026 10:20:20",
    "attFileSize": "196.08 KB",
    "attchmntFile": "https://nsearchives.nseindia.in/corporate/HINDALCOIND_15112026101130_Cessation_of_WOS_signed.pdf",
    "attchmntText": "Intimation regarding cessation of Novelis (China) Aluminum Products Co. Ltd. and Novelis (Shanghai) Aluminum Trading Co. Ltd, wholly-owned subsidiaries of Novelis Inc. a subsidiary of Hindalco Industries Limited [\"Company\"], as subsidiaries of the Company.",
    "bflag": null,
    "csvName": null,
    "desc": "Sale or disposal",
    "difference": "00:00:01",
    "dt": "15112026102020",
    "exchdisstime": "15-Nov-2026 10:20:21",
    "fileSize": "196.08 KB",
    "hasXbrl": true,
    "old_new": null,
    "orgid": null,
    "seq_id": "106861462",
    "smIndustry": "Aluminium",
    "sm_isin": "INE038A01020",
    "sm_name": "Hindalco Industries Limited",
    "sort_date": "2026-11-15 10:20:20",
    "symbol": "HINDALCO",
    "voiceSummary": "Hindalco Industries Limited has entered into a definitive agreement on November 14, 2026, to sell its wholly-owned subsidiaries Novelis China Aluminum Products Co. Ltd. and Novelis Shanghai Aluminum Trading Co. Ltd. to Shenzhen Hongzhi Industrial Investment Co. Ltd. The transaction consideration is approximately USD 265 million, with a potential contingent earn-out of USD 10 million. Closing is expected within 12 months, subject to regulatory approvals. The entities contributed USD 376 million in net sales and USD 259 million in net worth during the last financial year, representing approximately 1% and 2% of the Company\u2019s respective totals. The buyers are not part of the promoter group. The transaction is not a related party deal and does not fall under a scheme of arrangement.",
    "voiceUrl": "https://nsearchives.nseindia.in/ann_voice/HINDALCOIND_15112026101130_Cessation_of_WOS_signed.mp3"
  }
]
```

### 2. BSE Announcements (Sample Page 2 Records with Attachment PDF Names)
```json
[
  {
    "NEWSID": "e741e8ed-f101-43a8-bd8a-0ff64f918adf",
    "SCRIP_CD": 543257,
    "XML_NAME": "ANN_543257_E741E8ED-F101-43A8-BD8A-0FF64F918ADF",
    "NEWSSUB": "Indian Railway Finance Corporation Ltd - 543257 - Announcement Under Regulation - 30 (LODR)",
    "DT_TM": "2026-11-18T13:51:56.907",
    "NEWS_DT": "2026-11-18T13:51:56.907",
    "CRITICALNEWS": "0",
    "ANNOUNCEMENT_TYPE": "A",
    "QUARTER_ID": null,
    "FILESTATUS": "N    ",
    "ATTACHMENTNAME": "2e506620-aee7-43f0-a1b6-91132be64420.pdf",
    "MORE": "",
    "HEADLINE": "Announcement under Regulation - 30 (LODR)",
    "CATEGORYNAME": "Company Update",
    "OLD": 1,
    "RN": 1,
    "PDFFLAG": 0,
    "NSURL": "https://www.bseindia.com/stock-share-price/indian-railway-finance-corporation-ltd/irfc/543257/",
    "SLONGNAME": "Indian Railway Finance Corporation Ltd",
    "AGENDA_ID": 1,
    "TotalPageCnt": 5,
    "News_submission_dt": "2026-11-18T13:51:56",
    "DissemDT": "2026-11-18T13:51:56.907",
    "TimeDiff": "00:00:00",
    "Fld_Attachsize": 766272,
    "SUBCATNAME": "General",
    "BSENEWSID": null,
    "INVESTOR_PRESENTATION": null,
    "RECORDID": null,
    "DataInsDate": null,
    "AUDIO_VIDEO_FILE": null
  },
  {
    "NEWSID": "61c618d4-955c-43db-bda4-0aecc1bc8385",
    "SCRIP_CD": 531233,
    "XML_NAME": "ANN_531233_61C618D4-955C-43DB-BDA4-0AECC1BC8385",
    "NEWSSUB": "Rasi Electrodes Ltd - 531233 - Announcement under Regulation 30 (LODR)-Newspaper Publication",
    "DT_TM": "2026-11-18T13:51:12.857",
    "NEWS_DT": "2026-11-18T13:51:12.857",
    "CRITICALNEWS": "0",
    "ANNOUNCEMENT_TYPE": "A",
    "QUARTER_ID": null,
    "FILESTATUS": "N    ",
    "ATTACHMENTNAME": "26f3f2f9-5891-4c55-9a50-dbd1b39ce487.pdf",
    "MORE": "",
    "HEADLINE": "Copy of Advt in newspapers relating to Unaudited Results FQE 30.09.2026 and Notice",
    "CATEGORYNAME": "Company Update",
    "OLD": 1,
    "RN": 1,
    "PDFFLAG": 0,
    "NSURL": "https://www.bseindia.com/stock-share-price/rasi-electrodes-ltd/rasielec/531233/",
    "SLONGNAME": "Rasi Electrodes Ltd",
    "AGENDA_ID": 144,
    "TotalPageCnt": 5,
    "News_submission_dt": "2026-11-18T13:51:12",
    "DissemDT": "2026-11-18T13:51:12.857",
    "TimeDiff": "00:00:00",
    "Fld_Attachsize": 4470667,
    "SUBCATNAME": "Newspaper Publication",
    "BSENEWSID": null,
    "INVESTOR_PRESENTATION": null,
    "RECORDID": null,
    "DataInsDate": null,
    "AUDIO_VIDEO_FILE": null
  }
]
```

### 3. NSE Event Calendar (7-Day Forward Window: Board Meetings / Results)
```json
[
  {
    "symbol": "ANSALAPI",
    "company": "Ansal Properties & Infrastructure Limited",
    "purpose": "Financial Results",
    "bm_desc": "To consider and approve the unaudited financial results for the quarter ended Jun 30, 2026",
    "date": "18-Nov-2026"
  },
  {
    "symbol": "ARIHANTCAP",
    "company": "Arihant Capital Markets Limited",
    "purpose": "Other business matters",
    "bm_desc": "To consider other business matters",
    "date": "18-Nov-2026"
  }
]
```
