import sqlite3
import pandas as pd

conn = sqlite3.connect("output/scanner.db")
cur = conn.cursor()

cur.execute("""
    SELECT count(*), count(DISTINCT flag_id), count(DISTINCT announcement_title)
    FROM outcomes
    WHERE is_material = 1
""")
print("Outcomes with is_material=1:", cur.fetchone())

cur.execute("""
    SELECT o.id, o.flag_id, f.symbol, f.company, f.is_control, o.horizon_days,
           o.announcement_date, o.announcement_title, o.announcement_url
    FROM outcomes o
    JOIN flags f ON o.flag_id = f.id
    WHERE o.is_material = 1
    LIMIT 10
""")
rows = cur.fetchall()
for r in rows:
    print(r)

conn.close()
