import os
import sys
sys.path.insert(0, '.')
import sqlite3
import json
import re
import csv
from code.evidence import ResourceRecord, get_system_and_category

def parse_sql_file(file_id: str, filepath: str, meta: dict) -> list:
    captured_at = meta["captured_at"]
    conn = sqlite3.connect(":memory:")
    with open(filepath, "r", encoding="utf-8") as f:
        conn.executescript(f.read())

    records = []
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    for table in tables:
        if table == "snapshot_scope":
            continue
        cursor = conn.execute(f"SELECT * FROM {table}")
        col_names = [d[0] for d in cursor.description]
        rows = cursor.fetchall()
        for row_vals in rows:
            row = dict(zip(col_names, row_vals))
            
            # Check if record_json is present
            if "record_json" in row and row["record_json"]:
                try:
                    inner = json.loads(row["record_json"])
                    for k, v in inner.items():
                        if k not in row or not row[k]:
                            row[k] = v
                except Exception:
                    pass

            resource_id = row.get("resource_id", "")
            if not resource_id:
                continue

            system_id, data_category = get_system_and_category(resource_id)
            if "failover" in table or "replica" in table or "primary" in table:
                if resource_id.startswith("account_"):
                    system_id = "account_service"
                elif resource_id.startswith("search_"):
                    system_id = "search_service"
                elif resource_id.startswith("analytics_"):
                    system_id = "analytics_platform"

            # Determine state
            state = "PRESENT"
            if "account_status" in row:
                st = row["account_status"]
                state = "ABSENT" if st == "DELETED" else "PRESENT"
            elif "enabled" in row:
                state = "ACTIVE" if row["enabled"] in (1, "1", True) else "DISABLED"
            elif "restore_allowed" in row:
                state = "ACTIVE" if row["restore_allowed"] in (1, "1", True) else "BLOCKED"
            elif resource_id.startswith("analytics_"):
                if not row.get("email") and not row.get("phone") and not row.get("email_hash") and not row.get("user_id"):
                    state = "ANONYMIZED"
                else:
                    state = "PRESENT"
            elif resource_id.startswith("support_"):
                if not row.get("requester_email") and not row.get("requester_phone") and not row.get("requester_name"):
                    state = "REDACTED"
                else:
                    state = "PRESENT"

            rec = ResourceRecord(
                resource_id=resource_id,
                system_id=system_id,
                data_category=data_category,
                state=state,
                evidence_id=file_id,
                captured_at=captured_at,
                user_id=row.get("user_id") or row.get("customer_reference") or row.get("subject_reference"),
                email=row.get("email") or row.get("requester_email") or row.get("owner_email") or row.get("customer_email"),
                phone=row.get("phone") or row.get("requester_phone") or row.get("owner_phone"),
                email_hash=row.get("email_hash"),
                name=row.get("full_name") or row.get("display_name") or row.get("requester_name"),
                customer_reference=row.get("customer_reference") or row.get("subject_reference") or row.get("user_id"),
                extra={"table": table, "raw": row}
            )
            records.append(rec)
    return records

# Test on evidence_05
meta = {"captured_at": "2026-09-21T10:00:00Z"}
recs = parse_sql_file("evidence_05", "dataset/evidence/databases/customer_data_read_replica_20260921.sql", meta)
print("evidence_05 parsed records count:", len(recs))
analytics_4440 = [r for r in recs if r.resource_id == "analytics_4440"]
print("analytics_4440:", analytics_4440)
search_8911 = [r for r in recs if r.resource_id == "search_8911"]
print("search_8911:", search_8911)
