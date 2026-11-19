import os
import sys
import json
import threading
from datetime import date, datetime, timedelta
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from holidays import load_holidays_from_file

holiday_dates_set = load_holidays_from_file()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Referer": "https://www.nseindia.com/"
}

_local = threading.local()

def get_session():
    if not hasattr(_local, "session"):
        _local.session = requests.Session()
        _local.session.headers.update(HEADERS)
    return _local.session

start_date = date(2024, 1, 1)
end_date = date(2026, 11, 18)

weekday_dates = []
cur = start_date
while cur <= end_date:
    if cur.weekday() < 5:  # Monday to Friday
        weekday_dates.append(cur)
    cur += timedelta(days=1)

# Saturday sessions in 2024
saturday_sessions = [date(2024, 1, 20), date(2024, 3, 2), date(2024, 5, 18)]

all_test_dates = sorted(weekday_dates + saturday_sessions)

print(f"Total dates to validate against NSE UDDiP: {len(all_test_dates)}")
print(f"Total holiday dates in calendar: {len(holiday_dates_set)}")

def check_date(d: date):
    ymd = d.strftime("%Y%m%d")
    url = f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{ymd}_F_0000.csv.zip"
    is_cal_holiday = d.isoformat() in holiday_dates_set
    
    status = 0
    s = get_session()
    for attempt in range(2):
        try:
            r = s.head(url, timeout=5)
            status = r.status_code
            if status in (200, 404):
                break
        except Exception:
            pass

    file_exists = (status == 200)
    mismatch = False
    mismatch_type = None

    if is_cal_holiday and file_exists:
        mismatch = True
        mismatch_type = "MARKED_HOLIDAY_BUT_UDDIP_EXISTS"
    elif not is_cal_holiday and not file_exists and d.weekday() < 5 and d != date(2026, 11, 18):
        mismatch = True
        mismatch_type = "NOT_MARKED_HOLIDAY_BUT_UDDIP_MISSING"

    return {
        "date": d.isoformat(),
        "weekday": d.strftime("%A"),
        "is_cal_holiday": is_cal_holiday,
        "file_exists": file_exists,
        "status_code": status,
        "mismatch": mismatch,
        "mismatch_type": mismatch_type,
    }

print("Running validation across 15 threads...")
results = []
with ThreadPoolExecutor(max_workers=15) as executor:
    futures = {executor.submit(check_date, d): d for d in all_test_dates}
    for f in as_completed(futures):
        results.append(f.result())

results.sort(key=lambda x: x["date"])

mismatches = [r for r in results if r["mismatch"]]
print(f"\n========================================================")
print(f"VALIDATION FINISHED. Checked {len(results)} dates.")
print(f"Total mismatches: {len(mismatches)}")
print(f"========================================================")

for m in mismatches:
    print(f"Mismatch: {m['date']} ({m['weekday']}) | Type: {m['mismatch_type']} | HTTP: {m['status_code']}")

with open("output/holiday_validation_results.json", "w", encoding="utf-8") as fp:
    json.dump({"total_checked": len(results), "mismatches": mismatches}, fp, indent=2)
