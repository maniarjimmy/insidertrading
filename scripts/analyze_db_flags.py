import sqlite3
import pandas as pd

conn = sqlite3.connect("output/scanner.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Get all real flags
df_flags = pd.read_sql_query("SELECT * FROM flags WHERE is_control = 0", conn)
print("Real flags shape:", df_flags.shape)
print("catalyst_state distribution:")
print(df_flags["catalyst_state"].value_counts())

# Now let's check outcomes
df_outcomes = pd.read_sql_query("""
    SELECT o.*, f.symbol, f.scan_date, f.catalyst_state
    FROM outcomes o
    JOIN flags f ON o.flag_id = f.id
    WHERE f.is_control = 0
""", conn)
print("\nOutcomes count:", len(df_outcomes))
print("Horizon days present in outcomes:", df_outcomes["horizon_days"].value_counts().to_dict())

# Let's see at 3-day and 10-day:
for h in [3, 10]:
    sub = df_outcomes[df_outcomes["horizon_days"] == h]
    print(f"\n--- Horizon {h} days ---")
    print(f"Total flags with horizon {h}: {len(sub)}")
    print(pd.crosstab(sub["catalyst_state"], sub["is_material"], margins=True))

conn.close()
