import os
import sys
from datetime import date
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bhavcopy import download_uddip_bhavcopy

# Test downloading UDDiP for Cochin Shipyard ex-date (2024-01-10) and Canara Bank (2024-05-15) and BPCL (2024-06-21)
for d in [date(2024, 1, 9), date(2024, 1, 10), date(2024, 5, 14), date(2024, 5, 15), date(2024, 6, 20), date(2024, 6, 21), date(2026, 2, 16), date(2026, 3, 16), date(2026, 4, 15)]:
    df = download_uddip_bhavcopy(d)
    print(f"Date {d}: df is {'None' if df is None else f'{len(df)} rows'}")
