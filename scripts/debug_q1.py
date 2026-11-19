import os
import sqlite3
import pandas as pd

conn = sqlite3.connect("output/scanner.db")
cur = conn.cursor()

cur.execute("SELECT is_control, count(*) FROM flags GROUP BY is_control")
print("Flags by is_control:", cur.fetchall())

cur.execute("SELECT count(*) FROM flags WHERE is_control = 0")
print("Total real flags:", cur.fetchone()[0])

cur.execute("SELECT catalyst_state, count(*) FROM flags WHERE is_control = 0 GROUP BY catalyst_state")
print("Real flags by catalyst_state in DB:", cur.fetchall())

cur.execute("""
    SELECT horizon_days, is_material, count(*)
    FROM outcomes o
    JOIN flags f ON o.flag_id = f.id
    WHERE f.is_control = 0
    GROUP BY horizon_days, is_material
""")
print("Outcomes by horizon_days and is_material (is_control=0):", cur.fetchall())

for h in [1, 3, 5, 10]:
    cur.execute(f"""
        SELECT count(DISTINCT f.id)
        FROM flags f
        JOIN outcomes o ON f.id = o.flag_id
        WHERE f.is_control = 0 AND o.horizon_days = {h} AND o.is_material = 1
    """)
    print(f"Flags with material outcome at horizon {h}:", cur.fetchone()[0])

conn.close()
