from datetime import date
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bhavcopy import download_mto_delivery

test_date = date(2026, 4, 15)
mto_data = download_mto_delivery(test_date)
print("="*80)
print(f"REAL-DATA VALIDATION: MTO DELIVERY % ON {test_date.isoformat()}")
print("="*80)

if mto_data:
    print(f"Total symbols parsed in MTO delivery: {len(mto_data)}")
    for sym in ["COCHINSHIP", "CANBK", "AARTIIND", "NATIONALUM", "TEJASNET", "CROMPTON", "FEDERALBNK"]:
        if sym in mto_data:
            info = mto_data[sym]
            print(f"Symbol: {sym:<12} | Traded Qty: {info['traded_qty']:<10.0f} | Delivery Qty: {info['delivery_qty']:<10.0f} | Delivery %: {info['delivery_pct']:<6.2f}%")
        else:
            print(f"Symbol: {sym:<12} | Not found in MTO")
else:
    print("Failed to download or parse MTO delivery.")
