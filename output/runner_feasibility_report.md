# Phase 0: Feasibility & Data Quality Report (GitHub-Hosted Runner (ubuntu-latest))
**Environment**: GitHub-Hosted Runner (ubuntu-latest)
**Run Timestamp**: 2026-11-18 09:27:26 UTC
**Total Tested**: 14 | **Passed**: 14 | **Failed**: 0

| Category | Endpoint / Source | Status | Format Valid? | Items/Rows | Required Fields | Latency |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| 1. NSE Index Lists | NSE Index - NIFTY 100 | ✅ `200` | ✅ Yes | 100 | All Present | 544.5 ms |
| 1. NSE Index Lists | NSE Index - Midcap 150 | ✅ `200` | ✅ Yes | 150 | All Present | 373.4 ms |
| 1. NSE Index Lists | NSE Index - Smallcap 250 | ✅ `200` | ✅ Yes | 251 | All Present | 299.5 ms |
| 1. NSE Index Lists | NSE Index - NIFTY 500 | ✅ `200` | ✅ Yes | 501 | All Present | 342.5 ms |
| 2. Bhavcopy & Delivery | NSE Full Bhavcopy (2026-11-17) | ✅ `200` | ✅ Yes | 3572 | All Present | 1563.9 ms |
| 3. Deals & Surveillance | NSE Bulk Deals CSV | ✅ `200` | ✅ Yes | 122 | All Present | 342.9 ms |
| 3. Deals & Surveillance | NSE Block Deals CSV | ✅ `200` | ✅ Yes | 61 | All Present | 376.8 ms |
| 4. NSE Dynamic APIs | NSE Corporate Announcements API | ✅ `200` | ✅ Yes | 20 | All Present | 394.2 ms |
| 4. NSE Dynamic APIs | NSE Event Calendar (Board Meetings / Results) | ✅ `200` | ✅ Yes | 13 | All Present | 260.3 ms |
| 4. NSE Dynamic APIs | NSE Corporate Actions API | ✅ `200` | ✅ Yes | 20 | All Present | 294.7 ms |
| 4. NSE Dynamic APIs | NSE Trading Holidays Master | ✅ `200` | ✅ Yes | 12 | All Present | 283.9 ms |
| 5. BSE Dynamic APIs | BSE Announcements API (20261117) | ✅ `200` | ✅ Yes | 2 | All Present | 499.1 ms |
| 6. News & Fallback Feeds | Google News RSS (Reliance 1d) | ✅ `200` | ✅ Yes | 0 | N/A | 385.1 ms |
| 7. Market Data Fallback | yfinance (RELIANCE.NS fast_info & history) | ✅ `200` | ✅ Yes | 3 | last_price, history candles | 1457.6 ms |

---
## Content Quality & Sample Records

### 1. NSE Corporate Announcements (Sample 2 Records)
```json
[
  {
    "an_dt": "18-Nov-2026 14:56:31",
    "attFileSize": "3.89 MB",
    "attchmntFile": "https://nsearchives.nseindia.in/corporate/CENTUME_18112026145616_Investor_Presentation.pdf",
    "attchmntText": "Centum Electronics Limited has informed the Exchange about Investor Presentation",
    "bflag": null,
    "csvName": null,
    "desc": "Investor Presentation",
    "difference": "00:00:02",
    "dt": "18112026145631",
    "exchdisstime": "18-Nov-2026 14:56:33",
    "fileSize": "3.89 MB",
    "hasXbrl": true,
    "old_new": null,
    "orgid": null,
    "seq_id": "106864842",
    "smIndustry": "Electronics - Industrial",
    "sm_isin": "INE320B01020",
    "sm_name": "Centum Electronics Limited",
    "sort_date": "2026-11-18 14:56:31",
    "symbol": "CENTUM",
    "voiceSummary": null,
    "voiceUrl": null
  },
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
  }
]
```

### 2. BSE Corporate Announcements (Sample 2 Records)
```json
[
  {
    "NEWSID": "2a3ded54-ff10-471e-a791-8581fc485792",
    "SCRIP_CD": 500110,
    "XML_NAME": "ANN_500110_2A3DED54-FF10-471E-A791-8581FC485792",
    "NEWSSUB": "Chennai Petroleum Corporation Ltd - 500110 - Announcement under Regulation 30 (LODR)-Change in Directorate",
    "DT_TM": "2026-11-17T23:57:27.52",
    "NEWS_DT": "2026-11-17T23:57:27.52",
    "CRITICALNEWS": "0",
    "ANNOUNCEMENT_TYPE": "A",
    "QUARTER_ID": null,
    "FILESTATUS": "N    ",
    "ATTACHMENTNAME": "38a8b135-3a0b-4e45-b4d6-53a9503c1b36.pdf",
    "MORE": "",
    "HEADLINE": "Appointment of Shri Inderjeet, Government Nominee Director w.e.f 16.11.2026",
    "CATEGORYNAME": "Company Update",
    "OLD": 1,
    "RN": 1,
    "PDFFLAG": 0,
    "NSURL": "https://www.bseindia.com/stock-share-price/chennai-petroleum-corporation-ltd/chennpetro/500110/",
    "SLONGNAME": "Chennai Petroleum Corporation Ltd",
    "AGENDA_ID": 15,
    "TotalPageCnt": 16,
    "News_submission_dt": "2026-11-17T23:57:27",
    "DissemDT": "2026-11-17T23:57:27.52",
    "TimeDiff": "00:00:00",
    "Fld_Attachsize": 493231,
    "SUBCATNAME": "Change in Directorate",
    "BSENEWSID": null,
    "INVESTOR_PRESENTATION": null,
    "RECORDID": null,
    "DataInsDate": null,
    "AUDIO_VIDEO_FILE": null
  },
  {
    "NEWSID": "63f88d8e-f676-41ca-9cb8-d613399f1a98",
    "SCRIP_CD": 540570,
    "XML_NAME": "ANN_540570_63F88D8E-F676-41CA-9CB8-D613399F1A98",
    "NEWSSUB": "Variman Global Enterprises Ltd - 540570 - Announcement under Regulation 30 (LODR)-Allotment",
    "DT_TM": "2026-11-17T23:51:50.87",
    "NEWS_DT": "2026-11-17T23:51:50.87",
    "CRITICALNEWS": "0",
    "ANNOUNCEMENT_TYPE": "A",
    "QUARTER_ID": null,
    "FILESTATUS": "N    ",
    "ATTACHMENTNAME": "2976922e-e62c-4762-b5f3-98d43fda11dc.pdf",
    "MORE": "",
    "HEADLINE": "Allotment of Equity Shares and Warrants",
    "CATEGORYNAME": "Company Update",
    "OLD": 1,
    "RN": 1,
    "PDFFLAG": 0,
    "NSURL": "https://www.bseindia.com/stock-share-price/variman-global-enterprises-ltd/variman/540570/",
    "SLONGNAME": "Variman Global Enterprises Ltd",
    "AGENDA_ID": 5,
    "TotalPageCnt": 16,
    "News_submission_dt": "2026-11-17T23:51:50",
    "DissemDT": "2026-11-17T23:51:50.87",
    "TimeDiff": "00:00:00",
    "Fld_Attachsize": 286066,
    "SUBCATNAME": "Allotment of Equity Shares",
    "BSENEWSID": null,
    "INVESTOR_PRESENTATION": null,
    "RECORDID": null,
    "DataInsDate": null,
    "AUDIO_VIDEO_FILE": null
  }
]
```

### 3. NSE Event Calendar: Board Meetings & Financial Results (Sample 2 Records)
```json
[
  {
    "symbol": "ANTGRAPHIC",
    "company": "Antarctica Limited",
    "purpose": "Financial Results",
    "bm_desc": "ANTGRAPHIC : 19-Nov-2026 :  The Company has informed the Exchange that a Board meeting to be held on November 12, 2026 has been re-scheduled. Further, the Company has informed the Exchange that the meeting of the Board of Directors of the Company will be held on November 19, 2026,  To consider and approve the financial results for the period ended September 30, 2026",
    "date": "19-Nov-2026"
  },
  {
    "symbol": "BETA",
    "company": "Beta Drugs Limited",
    "purpose": "Other business matters",
    "bm_desc": "To consider other business matters",
    "date": "19-Nov-2026"
  }
]
```
