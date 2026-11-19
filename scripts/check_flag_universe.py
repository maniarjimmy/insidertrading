import sqlite3
import pandas as pd

univ_df = pd.read_csv("data/nifty500.csv")
univ_ranks = dict(zip(univ_df["Symbol"], univ_df["Rank"]))
univ_symbols_mid_small = set(univ_df[(univ_df["Rank"] >= 210) & (univ_df["Rank"] <= 500)]["Symbol"])
univ_symbols_all = set(univ_df["Symbol"])

conn = sqlite3.connect("output/scanner.db")
cur = conn.cursor()

cur.execute("SELECT DISTINCT symbol, is_control FROM flags")
flag_syms = cur.fetchall()
print(f"Total distinct (symbol, is_control) pairs in DB: {len(flag_syms)}")

real_syms = set(s[0] for s in flag_syms if s[1] == 0)
ctrl_syms = set(s[0] for s in flag_syms if s[1] in (1, 2))

print(f"Real flag distinct symbols: {len(real_syms)}")
print(f"  In mid-small universe (210-500): {len(real_syms.intersection(univ_symbols_mid_small))}")
print(f"  In Nifty 500 total: {len(real_syms.intersection(univ_symbols_all))}")
out_of_univ = real_syms - univ_symbols_all
print(f"  Out of Nifty 500: {out_of_univ}")

ranks_real = [univ_ranks.get(s, 999) for s in real_syms]
print(f"Rank distribution of real flag symbols: min={min(ranks_real)}, max={max(ranks_real)}, median={pd.Series(ranks_real).median()}")

conn.close()
