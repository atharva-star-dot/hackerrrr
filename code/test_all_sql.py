import os
import sqlite3

db_dir = 'dataset/evidence/databases'
for f in os.listdir(db_dir):
    if f.endswith('.sql'):
        path = os.path.join(db_dir, f)
        conn = sqlite3.connect(':memory:')
        try:
            with open(path, 'r', encoding='utf-8') as fp:
                conn.executescript(fp.read())
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            # count total rows
            total_rows = 0
            for t in tables:
                total_rows += conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            print(f"{f}: OK ({len(tables)} tables, {total_rows} rows)")
        except Exception as e:
            print(f"{f}: ERROR: {e}")
