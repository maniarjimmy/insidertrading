import os, sys
from datetime import date
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bhavcopy import download_uddip_bhavcopy

def check_sym(d, sym):
    df = download_uddip_bhavcopy(d)
    if df is not None:
        sub = df[(df["symbol"] == sym) & (df["series"] == "EQ")]
        if not sub.empty:
            r = sub.iloc[0]
            return {"date": d.isoformat(), "open": float(r["open"]), "close": float(r["close"]), "prev_close": float(r["prev_close"])}
    return None

# Check PERSISTENT around 2024-03-04
print("PERSISTENT:")
for d in [date(2024, 3, 1), date(2024, 3, 4), date(2024, 3, 5)]:
    print(check_sym(d, "PERSISTENT"))

# Check HPCL around 2024-06-21 (Bonus 1:2, ex-date 2024-06-21)
print("\nHPCL:")
for d in [date(2024, 6, 20), date(2024, 6, 21), date(2024, 6, 24)]:
    print(check_sym(d, "HINDPETRO"))
