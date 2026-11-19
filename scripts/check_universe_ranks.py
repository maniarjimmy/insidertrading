import os
import pandas as pd

df = pd.read_csv("data/nifty500.csv")
print("Total rows in nifty500.csv:", len(df))
print("Columns:", list(df.columns))
if "Rank" in df.columns or "rank" in df.columns:
    rank_col = "Rank" if "Rank" in df.columns else "rank"
    mid_small = df[(df[rank_col] >= 210) & (df[rank_col] <= 500)]
    print(f"Constituents with rank 210-500: {len(mid_small)}")
    print("Sample symbols in rank 210-500:", mid_small["Symbol"].tolist()[:10])
else:
    print("No Rank column")
