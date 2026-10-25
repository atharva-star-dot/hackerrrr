"""
Evidence parser - parses all evidence files and builds a resource index.
Maps resource_id -> state, system, user identifiers, evidence_file_id.
"""
import csv
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class ResourceRecord:
    """A resource found in evidence."""
    resource_id: str
    system_id: str
    data_category: str  # maps to deletion_rules categories
    state: str  # PRESENT, ABSENT, REDACTED, ANONYMIZED, ACTIVE, BLOCKED, DISABLED
    evidence_id: str
    captured_at: str
    # User linkage
    user_id: Optional[str] = None
    email: Optional[str] = None
    email_hash: Optional[str] = None
    phone: Optional[str] = None
    name: Optional[str] = None
    customer_reference: Optional[str] = None  # e.g. user_XX
    # Extra metadata
    extra: Dict[str, Any] = field(default_factory=dict)


# Mapping from resource_id prefix to (system_id, data_category)
RESOURCE_PREFIX_MAP = {
    "account_": ("account_service", "USER_PROFILE"),
    "search_": ("search_service", "SEARCH_INDEX_ENTRY"),
    "analytics_": ("analytics_platform", "ANALYTICS_PROFILE"),
    "support_": ("support_platform", "SUPPORT_MESSAGE"),  # default, may be SUPPORT_ATTACHMENT
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


def classify_support_resource(resource_id: str, data_category_hint: str) -> str:
    """Classify a support resource as MESSAGE or ATTACHMENT based on evidence."""
    if data_category_hint == "SUPPORT_ATTACHMENT":
        return "SUPPORT_ATTACHMENT"
    return "SUPPORT_MESSAGE"


class EvidenceParser:
    """Parses all evidence files and builds a resource index."""

    def __init__(self, dataset_dir: str):
        self.dataset_dir = dataset_dir
        self.evidence_dir = os.path.join(dataset_dir, "evidence")
        self.evidence_manifest: Dict[str, dict] = {}  # file_id -> {path, origin, captured_at}
        self.resources: List[ResourceRecord] = []
        self._load_manifest()

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
                # PNG and PDF need vision - handled separately by agent
            except Exception as e:
                print(f"Warning: Failed to parse {file_id} ({filepath}): {e}")
        return self.resources

    def _parse_sql(self, file_id: str, filepath: str, meta: dict):
        """Parse SQL INSERT statements to extract resource records."""
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        captured_at = meta["captured_at"]
        # Find all INSERT statements
        insert_pattern = re.compile(
            r"INSERT\s+INTO\s+\"?(\w+)\"?\s+VALUES\s*\((.+?)\)\s*;",
            re.IGNORECASE | re.DOTALL
        )
        # Also get CREATE TABLE to understand columns
        create_pattern = re.compile(
            r"CREATE\s+TABLE\s+(\w+)\s*\((.+?)\)\s*;",
            re.IGNORECASE | re.DOTALL
        )

        tables = {}
        for m in create_pattern.finditer(content):
            table_name = m.group(1)
            cols_str = m.group(2)
            cols = []
            for col_def in cols_str.split(","):
                col_def = col_def.strip()
                if col_def:
                    col_name = col_def.split()[0].strip()
                    cols.append(col_name)
            tables[table_name] = cols

        for m in insert_pattern.finditer(content):
            table_name = m.group(1)
            values_str = m.group(2)
            # Parse values (handle quoted strings)
            values = self._parse_sql_values(values_str)
            cols = tables.get(table_name, [])
            if not cols or len(values) != len(cols):
                continue

            row = dict(zip(cols, values))
            resource_id = row.get("resource_id", "")
            if not resource_id:
                continue

            system_id, data_category = get_system_and_category(resource_id)

            # Determine system_id from table name hints
            if "failover" in table_name or "primary" in table_name or "regional" in table_name or "reporting" in table_name:
                if resource_id.startswith("account_"):
                    system_id = "account_service"

            # Determine state
            state = "PRESENT"
            account_status = row.get("account_status", "")
            if account_status == "DELETED":
                state = "ABSENT"

            rec = ResourceRecord(
                resource_id=resource_id,
                system_id=system_id,
                data_category=data_category,
                state=state,
                evidence_id=file_id,
                captured_at=captured_at,
                user_id=row.get("user_id"),
                email=row.get("email"),
                email_hash=row.get("email_hash"),
                phone=row.get("phone"),
                name=row.get("full_name"),
                customer_reference=row.get("user_id"),
                extra={"table": table_name, "raw": row},
            )
            self.resources.append(rec)

    def _parse_sql_values(self, values_str: str) -> List[str]:
        """Parse SQL VALUES clause handling quoted strings."""
        values = []
        current = ""
        in_quotes = False
        i = 0
        while i < len(values_str):
            c = values_str[i]
            if c == "'" and not in_quotes:
                in_quotes = True
                i += 1
                continue
            elif c == "'" and in_quotes:
                if i + 1 < len(values_str) and values_str[i + 1] == "'":
                    current += "'"
                    i += 2
                    continue
                else:
                    in_quotes = False
                    i += 1
                    continue
            elif c == "," and not in_quotes:
                values.append(current.strip())
                current = ""
                i += 1
                continue
            else:
                current += c
                i += 1
        values.append(current.strip())
        return values

    def _parse_json(self, file_id: str, filepath: str, meta: dict):
        """Parse JSON evidence files."""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        captured_at = meta["captured_at"]
        origin = meta["origin"]

        if "service_exports" in data:
            self._parse_service_resource_export(file_id, data, captured_at)
        elif "snapshots" in data:
            self._parse_snapshot_bundle(file_id, data, captured_at)
        elif "connectors" in data:
            self._parse_connector_config(file_id, data, captured_at)
        elif "export_jobs" in data:
            self._parse_export_jobs(file_id, data, captured_at)
        elif "audit_entries" in data or "records" in data:
            self._parse_audit_ledger(file_id, data, captured_at)
        elif "manifests" in data:
            self._parse_export_manifest(file_id, data, captured_at)
        else:
            # Try to extract any recognizable structures
            self._parse_generic_json(file_id, data, captured_at)

    def _parse_service_resource_export(self, file_id: str, data: dict, captured_at: str):
        """Parse service_resource_export JSON files (evidence_62, 65, 68, etc.)."""
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

                    # Determine state from the record
                    state = self._determine_state_from_record(record, resource_id, section_name)

                    rec = ResourceRecord(
                        resource_id=resource_id,
                        system_id=system_id,
                        data_category=data_category,
                        state=state,
                        evidence_id=file_id,
                        captured_at=record.get("observed_at", captured_at),
                        email=record.get("email"),
                        phone=record.get("phone"),
                        email_hash=record.get("email_hash"),
                        name=record.get("requester_name") or record.get("full_name"),
                        customer_reference=record.get("customer_reference") or record.get("subject_reference"),
                        extra=record,
                    )
                    self.resources.append(rec)

    def _determine_state_from_record(self, record: dict, resource_id: str, section_name: str) -> str:
        """Determine the state of a resource from its record data."""
        status_code = record.get("status_code")
        if status_code == 404:
            return "ABSENT"

        # For analytics profiles - check if anonymized (no PII fields)
        if resource_id.startswith("analytics_"):
            email = record.get("email")
            phone = record.get("phone")
            email_hash = record.get("email_hash")
            customer_ref = record.get("customer_reference")
            if not email and not phone and not email_hash and not customer_ref:
                return "ANONYMIZED"
            return "PRESENT"  # still identifiable = PRESENT (needs ANONYMIZE)

        # For support tickets - check if redacted
        if resource_id.startswith("support_"):
            email = record.get("requester_email")
            phone = record.get("requester_phone")
            name = record.get("requester_name")
            customer_ref = record.get("customer_reference")
            if not email and not phone and not name:
                if customer_ref:
                    return "REDACTED"  # only reference remains
                return "REDACTED"
            return "PRESENT"

        # For data flows / connectors
        if resource_id.startswith("data_flow_"):
            enabled = record.get("enabled")
            if enabled is False:
                return "DISABLED"
            return "ACTIVE"

        # For backups
        if resource_id.startswith("backup_"):
            restore_allowed = record.get("restore_allowed")
            if restore_allowed is False:
                return "BLOCKED"
            return "ACTIVE"

        # For tombstones
        if resource_id.startswith("tombstone_"):
            # Check if PII is still present
            email = record.get("email")
            phone = record.get("phone")
            name = record.get("name")
            email_hash = record.get("email_hash")
            if email or phone or name or email_hash:
                return "PRESENT"  # PII exposed, needs REDACT
            return "REDACTED"  # properly redacted

        # For audit records - they should be retained
        if resource_id.startswith("audit_record_"):
            return "PRESENT"  # retained per policy

        # Default
        if status_code == 200 or record.get("rows", 0) > 0:
            return "PRESENT"

        return "PRESENT"

    def _parse_snapshot_bundle(self, file_id: str, data: dict, captured_at: str):
        """Parse customer_data_snapshot_bundle JSON files."""
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

                # Determine state
                state = self._determine_state_from_record(record, resource_id, collection)

                # For tombstones specifically
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
                    email=record.get("email"),
                    phone=record.get("phone"),
                    email_hash=record.get("email_hash"),
                    name=record.get("name"),
                    customer_reference=record.get("subject_reference") or record.get("user_id"),
                    extra=record,
                )
                self.resources.append(rec)

    def _parse_connector_config(self, file_id: str, data: dict, captured_at: str):
        """Parse connector configuration JSON files."""
        connectors = data.get("connectors", [])
        for conn in connectors:
            resource_id = conn.get("resource_id", "")
            if not resource_id:
                continue
            state = "ACTIVE" if conn.get("enabled", True) else "DISABLED"
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
        """Parse export jobs JSON files."""
        jobs = data.get("export_jobs", [])
        for job in jobs:
            resource_id = job.get("resource_id", "")
            if not resource_id:
                continue
            state = "PRESENT"
            if job.get("status") == "deleted" or job.get("status") == "expired":
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
        """Parse security audit ledger JSON files."""
        entries = data.get("audit_entries", data.get("records", []))
        if isinstance(entries, list):
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
        """Parse export manifest JSON files."""
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
        """Try to extract resources from any JSON structure."""
        # Walk the data looking for resource_id fields
        self._walk_json(file_id, data, captured_at, [])

    def _walk_json(self, file_id: str, obj: Any, captured_at: str, path: list):
        """Recursively walk JSON to find resource records."""
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
        """Parse log files to extract resource state information."""
        captured_at = meta["captured_at"]
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()

        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Parse key=value log format
            record = self._parse_log_line(line)
            if not record:
                continue

            resource_id = record.get("resource_id", "")
            if not resource_id:
                continue

            event = record.get("event", "")
            service = record.get("service", "")
            system_id = service if service else "unknown_service"
            _, data_category = get_system_and_category(resource_id)

            # Determine state from log event
            state = self._determine_state_from_log(record, resource_id, event)
            if state is None:
                continue  # Skip non-state-revealing events

            timestamp = record.get("timestamp", captured_at)

            rec = ResourceRecord(
                resource_id=resource_id,
                system_id=system_id,
                data_category=data_category,
                state=state,
                evidence_id=file_id,
                captured_at=timestamp,
                email=record.get("email") or record.get("customer_email") or record.get("lookup_key") if "@" in record.get("lookup_key", "") else None,
                customer_reference=record.get("customer_reference") or (record.get("lookup_key") if record.get("lookup_key", "").startswith("user_") else record.get("subject_reference")),
                extra=record,
            )
            self.resources.append(rec)

    def _parse_log_line(self, line: str) -> Optional[dict]:
        """Parse a key=value log line."""
        result = {}
        # Extract timestamp at start
        ts_match = re.match(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\s+", line)
        if ts_match:
            result["timestamp"] = ts_match.group(1)
            line = line[ts_match.end():]

        # Parse key=value pairs
        kv_pattern = re.compile(r'(\w+)=("(?:[^"\\]|\\.)*"|[^\s]+)')
        for m in kv_pattern.finditer(line):
            key = m.group(1)
            val = m.group(2).strip('"')
            if val == "null":
                val = None
            result[key] = val

        return result if result else None

    def _determine_state_from_log(self, record: dict, resource_id: str, event: str) -> Optional[str]:
        """Determine resource state from a log event."""
        # Only process completed events
        if "_completed" not in event and "_read_completed" not in event:
            if "_started" in event:
                return None  # Skip start events

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
            if result_val == "hit":
                return "PRESENT"
            elif result_val == "miss":
                return "ABSENT"
            return None

        if resource_id.startswith("analytics_"):
            email = record.get("email")
            phone = record.get("phone")
            email_hash = record.get("email_hash")
            customer_ref = record.get("customer_reference")
            if not email and not phone and not email_hash and not customer_ref:
                return "ANONYMIZED"
            return "PRESENT"

        if resource_id.startswith("support_"):
            email = record.get("requester_email")
            phone = record.get("requester_phone")
            name = record.get("requester_name")
            customer_ref = record.get("customer_reference")
            if not email and not phone and not name:
                return "REDACTED"
            return "PRESENT"

        if resource_id.startswith("data_flow_"):
            enabled = record.get("enabled")
            if enabled == "false":
                return "DISABLED"
            return "ACTIVE"

        if resource_id.startswith("backup_"):
            restore_allowed = record.get("restore_allowed")
            if restore_allowed == "false":
                return "BLOCKED"
            return "ACTIVE"

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
        """Parse text evidence files (handover format)."""
        captured_at = meta["captured_at"]
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()

        for line in lines:
            line = line.strip()
            if not line or not line.startswith("- "):
                continue
            # Format: - TIMESTAMP | system | resource_id | CATEGORY | STATUS | identifier
            parts = [p.strip() for p in line[2:].split("|")]
            if len(parts) < 6:
                continue

            timestamp, system_id, resource_id, category_str, status_str, identifier = parts[0], parts[1], parts[2], parts[3], parts[4], parts[5]

            _, data_category = get_system_and_category(resource_id)

            # Override data_category from txt if provided
            if category_str in ("USER_PROFILE", "SEARCH_INDEX_ENTRY", "ANALYTICS_PROFILE",
                                "SUPPORT_MESSAGE", "SUPPORT_ATTACHMENT", "SECURITY_AUDIT_LOG",
                                "BACKUP_ARCHIVE", "DATA_FLOW", "USER_EXPORT", "MARKETING_PROFILE",
                                "ACCOUNT_TOMBSTONE", "LEGAL_HOLD_RECORD"):
                data_category = category_str

            # Map status to our states
            state_map = {
                "NOT_FOUND": "ABSENT",
                "FOUND": "PRESENT",
                "IDENTIFIABLE": "PRESENT",  # PII still present
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

    def get_evidence_for_user(self, identity, audit_at: str) -> List[ResourceRecord]:
        """Get all evidence records linked to a user identity, captured at or before audit_at."""
        results = []
        all_emails = {e.lower() for e in identity.all_emails if e}
        all_refs = {identity.user_id}
        all_hashes = {h for h in identity.all_email_hashes if h}
        all_phones = {p for p in identity.all_phones if p}

        for rec in self.resources:
            # Time filter
            if rec.captured_at > audit_at:
                continue

            # Check linkage
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
