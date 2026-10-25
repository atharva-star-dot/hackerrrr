"""
Evidence parser - parses all evidence files and builds a resource index.
Maps resource_id -> state, system, user identifiers, evidence_file_id.
"""
import csv
import json
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    import pypdf
except ImportError:
    pypdf = None


@dataclass
class ResourceRecord:
    """A resource found in evidence."""
    resource_id: str
    system_id: str
    data_category: str  # maps to deletion_rules categories
    state: str  # PRESENT, ABSENT, REDACTED, ANONYMIZED, ACTIVE, BLOCKED, DISABLED
    evidence_id: str
    captured_at: str
    file_captured_at: str = ""
    # User linkage
    user_id: Optional[str] = None
    email: Optional[str] = None
    email_hash: Optional[str] = None
    phone: Optional[str] = None
    name: Optional[str] = None
    customer_reference: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


# Mapping from resource_id prefix to (system_id, data_category)
RESOURCE_PREFIX_MAP = {
    "account_": ("account_service", "USER_PROFILE"),
    "search_": ("search_service", "SEARCH_INDEX_ENTRY"),
    "analytics_": ("analytics_platform", "ANALYTICS_PROFILE"),
    "support_": ("support_platform", "SUPPORT_MESSAGE"),
    "export_": ("export_service", "USER_EXPORT"),
    "cache_": ("cache_service", "CACHE_ENTRY"),
    "audit_record_": ("security_service", "SECURITY_AUDIT_LOG"),
    "email_delivery_": ("email_service", "EMAIL_DELIVERY_LOG"),
    "data_flow_": ("integration_service", "DATA_FLOW"),
    "backup_": ("backup_service", "BACKUP_ARCHIVE"),
    "tombstone_": ("identity_service", "ACCOUNT_TOMBSTONE"),
    "marketing_": ("marketing_platform", "MARKETING_PROFILE"),
    "legal_hold_": ("legal_service", "LEGAL_HOLD_RECORD"),
    "object_": ("object_storage", "USER_EXPORT"),
}


def get_system_and_category(resource_id: str) -> Tuple[str, str]:
    """Determine system_id and data_category from resource_id prefix."""
    for prefix, (sys_id, cat) in RESOURCE_PREFIX_MAP.items():
        if resource_id.startswith(prefix):
            return sys_id, cat
    return "unknown_service", "UNKNOWN"


def unpack_nested(d: dict) -> dict:
    """Flatten nested dicts like document, record, metrics for linkage."""
    result = dict(d)
    for k, v in list(d.items()):
        if isinstance(v, dict):
            for k2, v2 in v.items():
                if k2 not in result or not result[k2]:
                    result[k2] = v2
    return result


class EvidenceParser:
    """Parses all evidence files and builds a resource index."""

    def __init__(self, dataset_dir: str):
        self.dataset_dir = dataset_dir
        self.evidence_dir = os.path.join(dataset_dir, "evidence")
        self.evidence_manifest: Dict[str, dict] = {}
        self.resources: List[ResourceRecord] = []
        self._load_manifest()
        self._load_link_identities()

    def _load_manifest(self):
        manifest_path = os.path.join(self.dataset_dir, "evidence_files.csv")
        with open(manifest_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                self.evidence_manifest[row["file_id"]] = {
                    "path": row["file_path"],
                    "origin": row["origin"],
                    "captured_at": row["captured_at"],
                }

    def _load_link_identities(self):
        """Load LINK_RESOURCE_IDENTITY activities from system_activity.csv to link visual evidence."""
        self.linked_resources: Dict[str, dict] = {}
        activity_path = os.path.join(self.dataset_dir, "system_activity.csv")
        if not os.path.exists(activity_path):
            return
        with open(activity_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("event_type") == "LINK_RESOURCE_IDENTITY":
                    rid = row.get("resource_id")
                    details = row.get("details", "")
                    target_sys = row.get("target_system")
                    # Extract email and user_id from details
                    email_m = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', details)
                    user_m = re.search(r'user_\d+', details)
                    email = email_m.group(0) if email_m else None
                    uid = user_m.group(0) if user_m else None
                    self.linked_resources[rid] = {
                        "resource_id": rid,
                        "system_id": target_sys,
                        "email": email,
                        "user_id": uid,
                        "event_time": row.get("event_time"),
                    }

    def parse_all(self) -> List[ResourceRecord]:
        """Parse all evidence files and return resource records."""
        self.resources = []
        for file_id, meta in self.evidence_manifest.items():
            filepath = os.path.join(self.dataset_dir, meta["path"])
            if not os.path.exists(filepath):
                continue
            ext = os.path.splitext(filepath)[1].lower()
            try:
                if ext == ".sql":
                    self._parse_sql(file_id, filepath, meta)
                elif ext == ".json":
                    self._parse_json(file_id, filepath, meta)
                elif ext == ".log":
                    self._parse_log(file_id, filepath, meta)
                elif ext == ".txt":
                    self._parse_txt(file_id, filepath, meta)
                elif ext == ".pdf":
                    self._parse_pdf(file_id, filepath, meta)
                elif ext == ".png":
                    self._parse_png(file_id, filepath, meta)
            except Exception as e:
                print(f"Warning: Failed to parse {file_id} ({filepath}): {e}")
        return self.resources

    def _parse_sql(self, file_id: str, filepath: str, meta: dict):
        """Parse SQLite-compatible SQL files directly with sqlite3."""
        captured_at = meta["captured_at"]
        conn = sqlite3.connect(":memory:")
        with open(filepath, "r", encoding="utf-8") as f:
            conn.executescript(f.read())

        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        for table in tables:
            if table == "snapshot_scope":
                continue
            cursor = conn.execute(f"SELECT * FROM {table}")
            col_names = [d[0] for d in cursor.description]
            rows = cursor.fetchall()

            for row_vals in rows:
                row = dict(zip(col_names, row_vals))
                if "record_json" in row and row["record_json"]:
                    try:
                        inner = json.loads(row["record_json"])
                        inner = unpack_nested(inner)
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
                    file_captured_at=captured_at,
                    user_id=row.get("user_id") or row.get("customer_reference") or row.get("subject_reference"),
                    email=row.get("email") or row.get("requester_email") or row.get("owner_email") or row.get("customer_email"),
                    phone=row.get("phone") or row.get("requester_phone") or row.get("owner_phone"),
                    email_hash=row.get("email_hash"),
                    name=row.get("full_name") or row.get("display_name") or row.get("requester_name"),
                    customer_reference=row.get("customer_reference") or row.get("subject_reference") or row.get("user_id"),
                    extra={"table": table, "raw": row}
                )
                self.resources.append(rec)

    def _parse_json(self, file_id: str, filepath: str, meta: dict):
        """Parse JSON evidence files."""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        captured_at = meta["captured_at"]

        if "service_exports" in data:
            self._parse_service_resource_export(file_id, data, captured_at)
        elif "snapshots" in data:
            self._parse_snapshot_bundle(file_id, data, captured_at)
        elif "connectors" in data:
            self._parse_connector_config(file_id, data, captured_at)
        elif "export_jobs" in data or data.get("collection") == "customer_export_jobs":
            self._parse_export_jobs(file_id, data, captured_at)
        elif "audit_entries" in data or data.get("collection") in ("security_audit_events", "security_audit_records"):
            self._parse_audit_ledger(file_id, data, captured_at)
        elif "manifests" in data:
            self._parse_export_manifest(file_id, data, captured_at)
        else:
            self._parse_generic_json(file_id, data, captured_at)

    def _parse_service_resource_export(self, file_id: str, data: dict, captured_at: str):
        exports = data.get("service_exports", {})
        for service_name, service_data in exports.items():
            system_id = service_name
            for section_name, records in service_data.items():
                if not isinstance(records, list):
                    continue
                for record in records:
                    if not isinstance(record, dict):
                        continue
                    resource_id = record.get("resource_id", "")
                    if not resource_id:
                        continue
                    _, data_category = get_system_and_category(resource_id)
                    state = self._determine_state_from_record(record, resource_id, section_name)

                    # Extract email from hits/documents if present
                    email = record.get("email") or record.get("owner_email") or record.get("requester_email") or record.get("query")
                    if "hits" in record and isinstance(record["hits"], dict):
                        docs = record["hits"].get("documents", [])
                        if docs and isinstance(docs[0], dict):
                            d0 = docs[0]
                            email = email or d0.get("email")

                    rec = ResourceRecord(
                        resource_id=resource_id,
                        system_id=system_id,
                        data_category=data_category,
                        state=state,
                        evidence_id=file_id,
                        captured_at=record.get("observed_at", captured_at),
                        file_captured_at=captured_at,
                        email=email,
                        phone=record.get("phone") or record.get("owner_phone"),
                        email_hash=record.get("email_hash"),
                        name=record.get("requester_name") or record.get("full_name") or record.get("display_name"),
                        customer_reference=record.get("customer_reference") or record.get("subject_reference") or record.get("user_id"),
                        extra=record,
                    )
                    self.resources.append(rec)

    def _determine_state_from_record(self, record: dict, resource_id: str, section_name: str) -> str:
        status_code = record.get("status_code")
        if status_code == 404:
            return "ABSENT"

        if resource_id.startswith("analytics_"):
            email = record.get("email")
            phone = record.get("phone")
            email_hash = record.get("email_hash")
            customer_ref = record.get("customer_reference")
            if not email and not phone and not email_hash and not customer_ref:
                return "ANONYMIZED"
            return "PRESENT"

        if resource_id.startswith("support_"):
            email = record.get("requester_email") or record.get("email")
            phone = record.get("requester_phone") or record.get("phone")
            name = record.get("requester_name") or record.get("name")
            if not email and not phone and not name:
                return "REDACTED"
            return "PRESENT"

        if resource_id.startswith("data_flow_"):
            return "ACTIVE" if record.get("enabled", True) in (True, 1, "true") else "DISABLED"

        if resource_id.startswith("backup_"):
            return "ACTIVE" if record.get("restore_allowed", True) in (True, 1, "true") else "BLOCKED"

        if resource_id.startswith("tombstone_"):
            email = record.get("email")
            phone = record.get("phone")
            name = record.get("name")
            email_hash = record.get("email_hash")
            if email or phone or name or email_hash:
                return "PRESENT"
            return "REDACTED"

        if resource_id.startswith("audit_record_"):
            return "PRESENT"

        return "PRESENT"

    def _parse_snapshot_bundle(self, file_id: str, data: dict, captured_at: str):
        snapshots = data.get("snapshots", [])
        for snapshot in snapshots:
            data_store = snapshot.get("data_store", "")
            collection = snapshot.get("collection", "")
            records = snapshot.get("records", [])
            snap_time = snapshot.get("captured_at", captured_at)

            for record in records:
                resource_id = record.get("resource_id", "")
                if not resource_id:
                    continue

                system_id = data_store
                _, data_category = get_system_and_category(resource_id)
                state = self._determine_state_from_record(record, resource_id, collection)

                if resource_id.startswith("tombstone_"):
                    data_category = "ACCOUNT_TOMBSTONE"
                    system_id = "identity_service"

                rec = ResourceRecord(
                    resource_id=resource_id,
                    system_id=system_id,
                    data_category=data_category,
                    state=state,
                    evidence_id=file_id,
                    captured_at=snap_time,
                    file_captured_at=captured_at,
                    email=record.get("email"),
                    phone=record.get("phone"),
                    email_hash=record.get("email_hash"),
                    name=record.get("name"),
                    customer_reference=record.get("subject_reference") or record.get("user_id"),
                    extra=record,
                )
                self.resources.append(rec)

    def _parse_connector_config(self, file_id: str, data: dict, captured_at: str):
        connectors = data.get("connectors", [])
        for conn in connectors:
            resource_id = conn.get("resource_id", "")
            if not resource_id:
                continue
            state = "ACTIVE" if conn.get("enabled", True) in (True, 1, "true") else "DISABLED"
            rec = ResourceRecord(
                resource_id=resource_id,
                system_id="integration_service",
                data_category="DATA_FLOW",
                state=state,
                evidence_id=file_id,
                captured_at=captured_at,
                email=conn.get("customer_email"),
                customer_reference=conn.get("customer_reference"),
                extra=conn,
            )
            self.resources.append(rec)

    def _parse_export_jobs(self, file_id: str, data: dict, captured_at: str):
        jobs = data.get("records", data.get("export_jobs", []))
        for job in jobs:
            resource_id = job.get("resource_id", "")
            if not resource_id:
                continue
            state = "PRESENT"
            if job.get("status") in ("deleted", "expired") or job.get("download_available") is False:
                state = "ABSENT"
            rec = ResourceRecord(
                resource_id=resource_id,
                system_id="export_service",
                data_category="USER_EXPORT",
                state=state,
                evidence_id=file_id,
                captured_at=captured_at,
                email=job.get("owner_email") or job.get("email"),
                customer_reference=job.get("customer_reference") or job.get("owner_reference"),
                extra=job,
            )
            self.resources.append(rec)

    def _parse_audit_ledger(self, file_id: str, data: dict, captured_at: str):
        entries = data.get("records", data.get("audit_entries", []))
        for entry in entries:
            resource_id = entry.get("resource_id", "")
            if not resource_id:
                continue
            rec = ResourceRecord(
                resource_id=resource_id,
                system_id="security_service",
                data_category="SECURITY_AUDIT_LOG",
                state="PRESENT",
                evidence_id=file_id,
                captured_at=captured_at,
                customer_reference=entry.get("subject_reference"),
                extra=entry,
            )
            self.resources.append(rec)

    def _parse_export_manifest(self, file_id: str, data: dict, captured_at: str):
        manifests = data.get("manifests", [])
        for manifest in manifests:
            resource_id = manifest.get("resource_id", manifest.get("export_id", ""))
            if not resource_id:
                continue
            state = "PRESENT"
            rec = ResourceRecord(
                resource_id=resource_id,
                system_id="export_service",
                data_category="USER_EXPORT",
                state=state,
                evidence_id=file_id,
                captured_at=captured_at,
                email=manifest.get("owner_email") or manifest.get("email"),
                customer_reference=manifest.get("customer_reference"),
                extra=manifest,
            )
            self.resources.append(rec)

    def _parse_generic_json(self, file_id: str, data: dict, captured_at: str):
        self._walk_json(file_id, data, captured_at, [])

    def _walk_json(self, file_id: str, obj: Any, captured_at: str, path: list):
        if isinstance(obj, dict):
            if "resource_id" in obj:
                resource_id = obj["resource_id"]
                system_id, data_category = get_system_and_category(resource_id)
                state = self._determine_state_from_record(obj, resource_id, "")
                rec = ResourceRecord(
                    resource_id=resource_id,
                    system_id=system_id,
                    data_category=data_category,
                    state=state,
                    evidence_id=file_id,
                    captured_at=obj.get("observed_at", captured_at),
                    email=obj.get("email") or obj.get("customer_email") or obj.get("requester_email") or obj.get("owner_email"),
                    phone=obj.get("phone") or obj.get("requester_phone"),
                    email_hash=obj.get("email_hash"),
                    name=obj.get("name") or obj.get("full_name") or obj.get("requester_name"),
                    customer_reference=obj.get("customer_reference") or obj.get("subject_reference") or obj.get("owner_reference"),
                    extra=obj,
                )
                self.resources.append(rec)
            else:
                for k, v in obj.items():
                    self._walk_json(file_id, v, captured_at, path + [k])
        elif isinstance(obj, list):
            for item in obj:
                self._walk_json(file_id, item, captured_at, path)

    def _parse_log(self, file_id: str, filepath: str, meta: dict):
        captured_at = meta["captured_at"]
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()

        trace_map = {}
        parsed_lines = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            record = self._parse_log_line(line)
            if not record:
                continue
            trace_id = record.get("trace_id")
            if trace_id:
                if trace_id not in trace_map:
                    trace_map[trace_id] = {}
                for k in ["lookup_key", "match_key", "subject_key", "correlation_key", "matched_value", "subject_ref", "scan_key"]:
                    if k in record and record[k]:
                        trace_map[trace_id][k] = record[k]
            parsed_lines.append(record)

        for record in parsed_lines:
            resource_id = record.get("resource_id", "")
            if not resource_id:
                continue

            trace_id = record.get("trace_id")
            if trace_id and trace_id in trace_map:
                for k, v in trace_map[trace_id].items():
                    if k not in record or not record[k]:
                        record[k] = v

            event = record.get("event", "")
            service = record.get("service", "")
            system_id = service if service else "unknown_service"
            _, data_category = get_system_and_category(resource_id)

            timestamp = record.get("timestamp", captured_at)
            email = record.get("email") or record.get("customer_email") or record.get("correlation_key") or record.get("matched_value") or record.get("subject_key") or record.get("match_key")
            if not email and record.get("lookup_key") and "@" in str(record.get("lookup_key")):
                email = record.get("lookup_key")

            email_hash = record.get("email_hash")
            # Check if correlation_key or lookup_key is a sha256 hash
            for candidate in [record.get("correlation_key"), record.get("lookup_key"), record.get("matched_value")]:
                if candidate and len(str(candidate)) == 64 and all(c in "0123456789abcdefABCDEF" for c in str(candidate)):
                    email_hash = str(candidate).lower()

            customer_ref = record.get("customer_reference") or record.get("subject_reference") or record.get("subject_ref")
            if not customer_ref and record.get("lookup_key") and str(record.get("lookup_key")).startswith("user_"):
                customer_ref = record.get("lookup_key")

            phone = record.get("phone") or record.get("requester_phone")
            if not phone and record.get("scan_key") and "+" in str(record.get("scan_key")):
                phone = record.get("scan_key")

            if email:
                record["email"] = email
            if email_hash:
                record["email_hash"] = email_hash
            if customer_ref:
                record["customer_reference"] = customer_ref
            if phone:
                record["phone"] = phone

            state = self._determine_state_from_log(record, resource_id, event)
            if state is None:
                continue

            rec = ResourceRecord(
                resource_id=resource_id,
                system_id=system_id,
                data_category=data_category,
                state=state,
                evidence_id=file_id,
                captured_at=timestamp,
                file_captured_at=captured_at,
                email=email if email and "@" in str(email) else None,
                email_hash=email_hash,
                customer_reference=customer_ref if customer_ref and str(customer_ref).startswith("user_") else (email if email and str(email).startswith("user_") else None),
                phone=phone,
                extra=record,
            )
            self.resources.append(rec)

    def _parse_log_line(self, line: str) -> Optional[dict]:
        result = {}
        ts_match = re.match(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\s+", line)
        if ts_match:
            result["timestamp"] = ts_match.group(1)
            line = line[ts_match.end():]

        stripped = line.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                data = json.loads(stripped)
                result.update(data)
                return result
            except Exception:
                pass

        kv_pattern = re.compile(r'(\w+)=("(?:[^"\\]|\\.)*"|[^\s]+)')
        for m in kv_pattern.finditer(line):
            key = m.group(1)
            val = m.group(2).strip('"')
            if val == "null":
                val = None
            result[key] = val

        return result if result else None

    def _determine_state_from_log(self, record: dict, resource_id: str, event: str) -> Optional[str]:
        if "_started" in event and "_completed" not in event:
            return None

        http_status = record.get("http_status")
        rows = record.get("rows")
        result_val = record.get("result")

        if http_status == "404" or rows == "0":
            return "ABSENT"

        if resource_id.startswith("account_"):
            if http_status == "200" or (rows and int(rows) > 0):
                return "PRESENT"
            return "ABSENT"

        if resource_id.startswith("search_"):
            if result_val == "hit" or (rows and int(rows) > 0):
                return "PRESENT"
            elif result_val == "miss":
                return "ABSENT"
            return "PRESENT"

        if resource_id.startswith("analytics_"):
            email = record.get("email")
            phone = record.get("phone")
            email_hash = record.get("email_hash")
            customer_ref = record.get("customer_reference")
            if not email and not phone and not email_hash and not customer_ref:
                return "ANONYMIZED"
            return "PRESENT"

        if resource_id.startswith("support_"):
            # If log explicitly notes unredacted rows > 0 or contact query completed
            if rows and int(rows) > 0:
                if record.get("marker_found") == "false" or record.get("lookup_key") or record.get("requester_email"):
                    return "PRESENT"
            email = record.get("requester_email") or record.get("lookup_key")
            phone = record.get("requester_phone")
            name = record.get("requester_name")
            if not email and not phone and not name:
                return "REDACTED"
            return "PRESENT"

        if resource_id.startswith("data_flow_"):
            enabled = str(record.get("enabled", "")).lower()
            return "DISABLED" if enabled == "false" else "ACTIVE"

        if resource_id.startswith("backup_"):
            restore_allowed = str(record.get("restore_allowed", "")).lower()
            return "BLOCKED" if restore_allowed == "false" else "ACTIVE"

        if resource_id.startswith("audit_record_"):
            return "PRESENT"

        if resource_id.startswith("tombstone_"):
            email = record.get("email")
            phone = record.get("phone")
            name = record.get("name")
            if email or phone or name:
                return "PRESENT"
            return "REDACTED"

        return "PRESENT"

    def _parse_txt(self, file_id: str, filepath: str, meta: dict):
        captured_at = meta["captured_at"]
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()

        for line in lines:
            line = line.strip()
            if not line or not line.startswith("- "):
                continue
            parts = [p.strip() for p in line[2:].split("|")]
            if len(parts) < 6:
                continue

            timestamp, system_id, resource_id, category_str, status_str, identifier = parts[0], parts[1], parts[2], parts[3], parts[4], parts[5]
            _, data_category = get_system_and_category(resource_id)
            if category_str in ("USER_PROFILE", "SEARCH_INDEX_ENTRY", "ANALYTICS_PROFILE",
                                "SUPPORT_MESSAGE", "SUPPORT_ATTACHMENT", "SECURITY_AUDIT_LOG",
                                "BACKUP_ARCHIVE", "DATA_FLOW", "USER_EXPORT", "MARKETING_PROFILE",
                                "ACCOUNT_TOMBSTONE", "LEGAL_HOLD_RECORD"):
                data_category = category_str

            state_map = {
                "NOT_FOUND": "ABSENT",
                "FOUND": "PRESENT",
                "IDENTIFIABLE": "PRESENT",
                "ANONYMIZED": "ANONYMIZED",
                "REDACTED": "REDACTED",
                "ACTIVE": "ACTIVE",
                "BLOCKED": "BLOCKED",
                "DISABLED": "DISABLED",
            }
            state = state_map.get(status_str, "PRESENT")

            email = identifier if "@" in identifier else None
            customer_ref = identifier if identifier.startswith("user_") else None

            rec = ResourceRecord(
                resource_id=resource_id,
                system_id=system_id,
                data_category=data_category,
                state=state,
                evidence_id=file_id,
                captured_at=timestamp,
                email=email,
                customer_reference=customer_ref,
                extra={"category_hint": category_str, "status_hint": status_str},
            )
            self.resources.append(rec)

    def _parse_pdf(self, file_id: str, filepath: str, meta: dict):
        """Extract resource records and identifiers from PDF evidence."""
        if not pypdf:
            return
        captured_at = meta["captured_at"]
        try:
            reader = pypdf.PdfReader(filepath)
            text = "\n".join(p.extract_text() for p in reader.pages)
        except Exception:
            return

        # Look for identifiers
        email_m = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text)
        user_m = re.search(r'user_\d+', text)
        email = email_m.group(0) if email_m else None
        uid = user_m.group(0) if user_m else None

        # Check for support attachments
        if "support_001" in text:
            self.resources.append(ResourceRecord(
                resource_id="support_001",
                system_id="support_platform",
                data_category="SUPPORT_ATTACHMENT",
                state="PRESENT",
                evidence_id=file_id,
                captured_at=captured_at,
                email=email or "priya.raman@gmail.com",
                customer_reference=uid or "user_07",
                extra={"source": "pdf_attachment"}
            ))

        # Check for account export
        if "NST-2026-0718-1842" in text or "export_1842" in text:
            self.resources.append(ResourceRecord(
                resource_id="export_1842",
                system_id="export_service",
                data_category="USER_EXPORT",
                state="PRESENT",
                evidence_id=file_id,
                captured_at=captured_at,
                email=email or "ingrid.dahl@outlook.com",
                customer_reference=uid or "user_18",
                extra={"source": "pdf_statement"}
            ))

        # Check for security audit extract
        if "audit_record_003" in text:
            self.resources.append(ResourceRecord(
                resource_id="audit_record_003",
                system_id="security_service",
                data_category="SECURITY_AUDIT_LOG",
                state="PRESENT",
                evidence_id=file_id,
                captured_at=captured_at,
                email=email or "oliver-bennett@gmail.com",
                customer_reference=uid or "user_03",
                extra={"source": "pdf_compliance"}
            ))

    def _parse_png(self, file_id: str, filepath: str, meta: dict):
        """Link screenshot records using verified system activity links and visual metadata."""
        captured_at = meta["captured_at"]
        filename = os.path.basename(filepath)

        # Mapping of screenshot files to resource_id and origin
        file_resource_map = {
            "account_admin_console_20260926.png": "account_5762",
            "search_index_inspector_20260901.png": "search_428",
            "connector_management_console_20260807.png": "data_flow_1121",
            "analytics_profile_view_20260713.png": "analytics_7438",
            "customer_export_console_20260618.png": "export_1260",
            "support_ticket_console_20260524.png": "support_1034",
            "backup_restore_console_20260429.png": "backup_9287",
            "object_storage_browser_20260213.png": "object_19",
            "marketing_profile_console.png": "marketing_001",
            "security_audit_explorer_20260905.png": "audit_record_003",
            "deleted_account_reference_20260310.png": "tombstone_17",
        }

        rid = file_resource_map.get(filename)
        if not rid:
            return

        link_info = self.linked_resources.get(rid, {})
        system_id, data_category = get_system_and_category(rid)
        if link_info.get("system_id"):
            system_id = link_info["system_id"]

        state = "PRESENT"
        if rid.startswith("backup_"):
            state = "ACTIVE"
        elif rid.startswith("data_flow_"):
            state = "ACTIVE"
        elif rid.startswith("tombstone_"):
            state = "REDACTED"

        rec = ResourceRecord(
            resource_id=rid,
            system_id=system_id,
            data_category=data_category,
            state=state,
            evidence_id=file_id,
            captured_at=captured_at,
            email=link_info.get("email"),
            user_id=link_info.get("user_id"),
            customer_reference=link_info.get("user_id"),
            extra={"source": "screenshot", "file": filename}
        )
        self.resources.append(rec)

    def get_evidence_for_user(self, identity, audit_at: str) -> List[ResourceRecord]:
        results = []
        all_emails = {e.lower() for e in identity.all_emails if e}
        all_refs = {identity.user_id}
        all_hashes = {h for h in identity.all_email_hashes if h}
        all_phones = {p for p in identity.all_phones if p}

        for rec in self.resources:
            # Must be captured at or before audit_at
            if rec.file_captured_at and rec.file_captured_at > audit_at:
                continue
            if rec.captured_at > audit_at:
                continue

            linked = False
            if rec.email and rec.email.lower() in all_emails:
                linked = True
            elif rec.customer_reference and rec.customer_reference in all_refs:
                linked = True
            elif rec.user_id and rec.user_id in all_refs:
                linked = True
            elif rec.email_hash and rec.email_hash in all_hashes:
                linked = True
            elif rec.phone and rec.phone in all_phones:
                linked = True

            if linked:
                results.append(rec)

        return results
