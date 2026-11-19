import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from corporate_actions import adjust_price_for_corporate_actions, parse_action_purpose

# 3 Known splits/bonuses in 2024-2026:
# 1. COCHINSHIP: Split 2:1 (Face value Rs 10 to Rs 5) on 2024-01-10 (Ratio 2.0)
# 2. CANBK (Canara Bank): Split 5:1 (Face value Rs 10 to Rs 2) on 2024-05-15 (Ratio 5.0)
# 3. BPCL: Bonus 1:1 (Ratio 2.0) on 2024-06-21

examples = [
    {
        "symbol": "COCHINSHIP",
        "action_type": "SPLIT",
        "ratio": 2.0,
        "ex_date": "2024-01-10",
        "desc": "Stock Split from Rs. 10/- to Rs. 5/-",
        "fetch_start": "2024-01-03",
        "fetch_end": "2024-01-17"
    },
    {
        "symbol": "CANBK",
        "action_type": "SPLIT",
        "ratio": 5.0,
        "ex_date": "2024-05-15",
        "desc": "Stock Split from Rs. 10/- to Rs. 2/-",
        "fetch_start": "2024-05-08",
        "fetch_end": "2024-05-22"
    },
    {
        "symbol": "BPCL",
        "action_type": "BONUS",
        "ratio": 2.0,
        "ex_date": "2024-06-21",
        "desc": "Bonus Issue in the ratio of 1:1",
        "fetch_start": "2024-06-14",
        "fetch_end": "2024-06-28"
    }
]

print("="*80)
print("REAL-DATA VALIDATION: 3 KNOWN SPLITS/BONUSES (RAW VS ADJUSTED)")
print("="*80)

for ex in examples:
    sym = ex["symbol"]
    ticker = f"{sym}.NS"
    df = yf.download(ticker, start=ex["fetch_start"], end=ex["fetch_end"], auto_adjust=False, progress=False)
    if df.empty:
        print(f"Failed to fetch {sym}")
        continue
    
    # Flatten MultiIndex columns if needed
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # Convert to candle dict list
    candles = []
    for idx, row in df.iterrows():
        dt_str = idx.strftime("%Y-%m-%d")
        candles.append({
            "date": dt_str,
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "close": float(row["Close"]),
            "volume": int(row["Volume"]),
        })

    action = [{
        "symbol": sym,
        "ex_date": ex["ex_date"],
        "action_type": ex["action_type"],
        "ratio": ex["ratio"],
        "purpose": ex["desc"]
    }]

    adj_candles = adjust_price_for_corporate_actions(candles, action)
    
    print(f"\n--- Symbol: {sym} | Action: {ex['action_type']} {ex['ratio']}:1 | Ex-Date: {ex['ex_date']} ---")
    print(f"Purpose: {ex['desc']}")
    print(f"{'Date':<12} | {'Raw Close':<10} | {'Adj Close':<10} | {'Raw Volume':<12} | {'Adj Volume':<12} | {'Adj Factor':<10}")
    print("-" * 75)
    for raw_c, adj_c in zip(candles, adj_candles):
        print(f"{raw_c['date']:<12} | {raw_c['close']:<10.2f} | {adj_c['close']:<10.2f} | {raw_c['volume']:<12} | {adj_c['volume']:<12} | {adj_c.get('adj_factor', 1.0):<10.2f}")
