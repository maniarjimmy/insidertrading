import sqlite3

con = sqlite3.connect('output/scanner.db')
cur = con.cursor()
cur.execute("SELECT catalyst_state, count(*) FROM flags WHERE is_control = 0 GROUP BY catalyst_state")
print("catalyst_state counts (is_control=0):", cur.fetchall())

# Also check what was queried in previous scripts or where 111 / 44 came from!
# Let's search git history or previous scripts for 111 and 44!
con.close()
