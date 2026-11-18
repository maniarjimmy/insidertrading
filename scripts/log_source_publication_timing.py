"""
Daily Publication Timing Logger (scripts/log_source_publication_timing.py)
Windows Task Scheduler Friendly script to log HTTP status and Last-Modified headers
for NSE UDDiP Bhavcopy, MTO Delivery Position, Bulk Deals, Block Deals, and sec_list.
Appends daily observations to output/source_publication_log.csv.
"""

from datetime import datetime, date
import os
import sys
import requests

# Base directories
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
LOG_CSV = os.path.join(OUTPUT_DIR, "source_publication_log.csv")
os.makedirs(OUTPUT_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Referer": "https://www.nseindia.com/"
}

def check_header(url: str, timeout: int = 8):
    """Retrieve HTTP status code and Last-Modified header, trying alternate host if needed."""
    candidate_urls = [url]
    if "nsearchives.nseindia.com" in url:
        candidate_urls.append(url.replace("nsearchives.nseindia.com", "archives.nseindia.com"))
    elif "archives.nseindia.com" in url:
        candidate_urls.append(url.replace("archives.nseindia.com", "nsearchives.nseindia.com"))

    for u in candidate_urls:
        try:
            r = requests.head(u, headers=HEADERS, timeout=timeout)
            if r.status_code == 200:
                return 200, r.headers.get("Last-Modified") or "N/A"
            if r.status_code == 405:
                r = requests.get(u, headers=HEADERS, stream=True, timeout=timeout)
                if r.status_code == 200:
                    return 200, r.headers.get("Last-Modified") or "N/A"
        except Exception:
            continue
    return 404, "N/A"

def main():
    now_ist = datetime.now()
    today_dt = now_ist.date()
    ymd = today_dt.strftime("%Y%m%d")
    dmy = today_dt.strftime("%d%m%Y")

    urls = {
        "uddip": f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{ymd}_F_0000.csv.zip",
        "mto": f"https://nsearchives.nseindia.com/archives/equities/mto/MTO_{dmy}.DAT",
        "bulk": "https://nsearchives.nseindia.com/content/equities/bulk.csv",
        "block": "https://nsearchives.nseindia.com/content/equities/block.csv",
        "sec_list": "https://nsearchives.nseindia.com/content/equities/sec_list.csv",
    }

    obs = {
        "timestamp_ist": now_ist.strftime("%Y-%m-%d %H:%M:%S"),
        "date": today_dt.isoformat(),
    }

    print(f"[{obs['timestamp_ist']}] Checking NSE exchange source publication headers...")
    for key, url in urls.items():
        status, lm = check_header(url)
        obs[f"{key}_status"] = status
        obs[f"{key}_last_modified"] = lm
        print(f"  {key:<10}: status={status} | Last-Modified={lm}")

    # Ensure CSV exists with headers
    fieldnames = [
        "timestamp_ist", "date",
        "uddip_status", "uddip_last_modified",
        "mto_status", "mto_last_modified",
        "bulk_status", "bulk_last_modified",
        "block_status", "block_last_modified",
        "sec_list_status", "sec_list_last_modified"
    ]

    write_header = not os.path.exists(LOG_CSV) or os.path.getsize(LOG_CSV) == 0

    import csv
    with open(LOG_CSV, "a", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerow(obs)

    print(f"Successfully recorded observation to {LOG_CSV}")

if __name__ == "__main__":
    main()
