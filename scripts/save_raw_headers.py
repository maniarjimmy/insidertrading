import os
import sys
import datetime
import requests
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_HEADERS_DIR = os.path.join(BASE_DIR, "output", "audit", "raw_headers")
os.makedirs(RAW_HEADERS_DIR, exist_ok=True)

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "*/*",
})

targets = [
    # UDDiP
    ("uddip_20261118", "https://archives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_20261118_F_0000.csv.zip", "2026-11-18", "UDDiP"),
    ("uddip_20261119", "https://archives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_20261119_F_0000.csv.zip", "2026-11-19", "UDDiP"),
    ("uddip_20261120", "https://archives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_20261120_F_0000.csv.zip", "2026-11-20", "UDDiP"),
    # MTO
    ("mto_20261118", "https://archives.nseindia.com/archives/equities/mto/MTO_18112026.DAT", "2026-11-18", "MTO"),
    ("mto_20261119", "https://archives.nseindia.com/archives/equities/mto/MTO_19112026.DAT", "2026-11-19", "MTO"),
    ("mto_20261120", "https://archives.nseindia.com/archives/equities/mto/MTO_20112026.DAT", "2026-11-20", "MTO"),
    # Continuous / post-market files
    ("bulk_deals", "https://archives.nseindia.com/content/equities/bulk.csv", "2026-11-20", "Bulk Deals"),
    ("block_deals", "https://archives.nseindia.com/content/equities/block.csv", "2026-11-20", "Block Deals"),
    ("sec_list", "https://archives.nseindia.com/content/equities/sec_list.csv", "2026-11-20", "Security List"),
]

print("Fetching raw headers and saving to output/audit/raw_headers/...")
log_rows = []

for name, url, dt_str, category in targets:
    req_time_utc = datetime.datetime.now(datetime.timezone.utc)
    req_time_ist = req_time_utc + datetime.timedelta(hours=5, minutes=30)
    
    try:
        resp = session.get(url, stream=True, timeout=15)
        status_code = resp.status_code
        headers_dict = dict(resp.headers)
        lm = headers_dict.get("Last-Modified", "N/A")
        cl = headers_dict.get("Content-Length", "N/A")
    except Exception as exc:
        status_code = "ERROR"
        headers_dict = {"Error": str(exc)}
        lm = "N/A"
        cl = "N/A"

    # Save full headers file
    raw_header_file = os.path.join(RAW_HEADERS_DIR, f"{name}.txt")
    with open(raw_header_file, "w", encoding="utf-8") as f:
        f.write(f"URL: {url}\n")
        f.write(f"Category: {category}\n")
        f.write(f"Target Date: {dt_str}\n")
        f.write(f"Request Time (UTC): {req_time_utc.isoformat()}\n")
        f.write(f"Request Time (IST): {req_time_ist.strftime('%Y-%m-%d %H:%M:%S IST')}\n")
        f.write(f"HTTP Status: {status_code}\n")
        f.write("=" * 80 + "\n")
        f.write("RESPONSE HEADERS:\n")
        for k, v in headers_dict.items():
            f.write(f"{k}: {v}\n")

    print(f"  Saved {name}: Status {status_code}, Last-Modified: {lm}")
    log_rows.append({
        "target": name,
        "category": category,
        "date": dt_str,
        "status": status_code,
        "last_modified": lm,
        "content_length": cl,
        "request_time_ist": req_time_ist.strftime('%Y-%m-%d %H:%M:%S'),
    })

# Now delete the old output/source_publication_log.csv
old_log = os.path.join(BASE_DIR, "output", "source_publication_log.csv")
if os.path.exists(old_log):
    os.remove(old_log)
    print(f"Deleted old {old_log}")

# Write new verified log strictly from the saved headers
new_log = os.path.join(BASE_DIR, "output", "source_publication_log.csv")
with open(new_log, "w", encoding="utf-8") as f:
    f.write("target,category,date,http_status,last_modified_gmt,content_length,logged_at_ist\n")
    for r in log_rows:
        f.write(f"{r['target']},{r['category']},{r['date']},{r['status']},\"{r['last_modified']}\",{r['content_length']},{r['request_time_ist']}\n")

print(f"Regenerated verified {new_log}")
