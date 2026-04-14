import sqlite3

conn = sqlite3.connect(r'G:\Saved Games\DCS.C130J\user_data.db')
cur = conn.cursor()

print("=== SCHEMA ===")
cur.execute("SELECT sql FROM sqlite_master WHERE type='table'")
for r in cur.fetchall():
    print(r[0])
    print()

print("=== ROUTES ===")
cur.execute("SELECT * FROM routes")
cols = [d[0] for d in cur.description]
print(cols)
for row in cur.fetchall():
    print(row)
    print()

print("=== CUSTOM_DATA ===")
cur.execute("SELECT * FROM custom_data")
cols = [d[0] for d in cur.description]
print(cols)
for row in cur.fetchall():
    print(row)

conn.close()
