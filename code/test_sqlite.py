import sqlite3

conn = sqlite3.connect(':memory:')
with open('dataset/evidence/databases/customer_data_read_replica_20260921.sql', 'r', encoding='utf-8') as f:
    conn.executescript(f.read())
tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print('Tables in evidence_05:', tables)
rows = conn.execute("SELECT * FROM customer_data_primary WHERE resource_id='analytics_4440'").fetchall()
print('Row:', rows)
