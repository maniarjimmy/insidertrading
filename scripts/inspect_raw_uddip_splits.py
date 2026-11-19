import os, sys
from datetime import date
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bhavcopy import download_uddip_bhavcopy

def get_price(d, sym):
    df = download_uddip_bhavcopy(d)
    if df is not None:
        sub = df[(df["symbol"] == sym) & (df["series"] == "EQ")]
        if not sub.empty:
            r = sub.iloc[0]
            return {"date": d.isoformat(), "open": r["open"], "high": r["high"], "low": r["low"], "close": r["close"], "prev_close": r["prev_close"], "volume": r["volume"]}
    return None

# Check COCHINSHIP around 2024-01-10 (Ex-date)
print("COCHINSHIP in UDDiP:")
for d in [date(2024, 1, 8), date(2024, 1, 9), date(2024, 1, 10), date(2024, 1, 11)]:
    print(get_price(d, "COCHINSHIP"))

# Check CANBK around 2024-05-15 (Ex-date)
print("\nCANBK in UDDiP:")
for d in [date(2024, 5, 13), date(2024, 5, 14), date(2024, 5, 15), date(2024, 5, 16)]:
    print(get_price(d, "CANBK"))

# Check BPCL around 2024-06-21 (Ex-date)
print("\nBPCL in UDDiP:")
for d in [date(2024, 6, 19), date(2024, 6, 20), date(2024, 6, 21), date(2024, 6, 24)]:
    print(get_price(d, "BPCL"))
