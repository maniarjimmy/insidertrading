import os
import sys
import pandas as pd
import yfinance as yf
from datetime import datetime, date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bhavcopy import download_uddip_bhavcopy

# 10 universe symbols (mid/small caps)
SYMBOLS = [
    "AARTIIND", "AMBER", "CANBK", "COCHINSHIP", "CROMPTON",
    "FEDERALBNK", "IRB", "NATIONALUM", "OIL", "TEJASNET"
]

# 3 distinct historical dates in 2026
DATES = [date(2026, 2, 16), date(2026, 3, 16), date(2026, 4, 15)]

print("="*80)
print("REAL-DATA VALIDATION: UDDIP CLOSE VS YFINANCE CLOSE FOR 10 SYMBOLS ON 3 DATES")
print("="*80)

for d in DATES:
    print(f"\n==================== DATE: {d.isoformat()} ====================")
    df_uddip = download_uddip_bhavcopy(d)
    if df_uddip is None or df_uddip.empty:
        print(f"Failed to load UDDiP Bhavcopy for {d}")
        continue
    
    # Filter EQ series
    eq_df = df_uddip[df_uddip["series"] == "EQ"].set_index("symbol")

    # Fetch yfinance close for all 10 symbols
    next_day = d + pd.Timedelta(days=5)
    yf_tickers = [f"{s}.NS" for s in SYMBOLS]
    yf_data = yf.download(yf_tickers, start=d.isoformat(), end=next_day.strftime("%Y-%m-%d"),
                          auto_adjust=False, progress=False)

    if isinstance(yf_data.columns, pd.MultiIndex):
        close_df = yf_data["Close"]
    else:
        close_df = yf_data[["Close"]]

    d_str = d.strftime("%Y-%m-%d")
    matched_row = None
    for idx_dt in close_df.index:
        if idx_dt.strftime("%Y-%m-%d") == d_str:
            matched_row = close_df.loc[idx_dt]
            break

    print(f"{'Symbol':<12} | {'UDDiP Close':<12} | {'yfinance Close':<14} | {'Diff':<8} | {'Match Status'}")
    print("-" * 65)
    for sym in SYMBOLS:
        u_close = None
        if sym in eq_df.index:
            u_close = float(eq_df.loc[sym]["close"])
            
        yf_sym = f"{sym}.NS"
        y_close = None
        if matched_row is not None and yf_sym in matched_row:
            val = matched_row[yf_sym]
            if pd.notnull(val):
                y_close = float(val)

        if u_close is not None and y_close is not None:
            diff = abs(u_close - y_close)
            status = "EXACT MATCH (0.00)" if diff < 0.05 else f"DIFF ({diff:.2f})"
            print(f"{sym:<12} | {u_close:<12.2f} | {y_close:<14.2f} | {diff:<8.2f} | {status}")
        else:
            print(f"{sym:<12} | {str(u_close):<12} | {str(y_close):<14} | N/A      | MISSING")
