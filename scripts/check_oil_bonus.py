import os, sys
from datetime import date
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bhavcopy import download_uddip_bhavcopy

# Oil India bonus was 1:2 on 2024-07-02
for d in [date(2024, 7, 1), date(2024, 7, 2), date(2024, 7, 3)]:
    df = download_uddip_bhavcopy(d)
    if df is not None:
        sub = df[(df["symbol"] == "OIL") & (df["series"] == "EQ")]
        if not sub.empty:
            r = sub.iloc[0]
            print(d.isoformat(), "OIL:", "close:", float(r["close"]), "prev_close:", float(r["prev_close"]))
