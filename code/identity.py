"""
Identity resolution module.
Resolves case email -> user_id -> all current and historical identifiers.
"""
import csv
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class UserIdentity:
    user_id: str
    current_name: str
    current_email: str
    current_phone: str
    current_email_hash: str
    snapshot_updated_at: str
    # All emails (current + historical)
    all_emails: Set[str] = field(default_factory=set)
    all_phones: Set[str] = field(default_factory=set)
    all_email_hashes: Set[str] = field(default_factory=set)
    all_names: Set[str] = field(default_factory=set)


class IdentityResolver:
    """Resolves emails to user identities, including historical email lookups."""

    def __init__(self, dataset_dir: str):
        self.dataset_dir = dataset_dir
        self.users_by_id: Dict[str, UserIdentity] = {}
        self.email_to_user_id: Dict[str, str] = {}  # lowercased email -> user_id
        self._load()

    def _load(self):
        # Load current identities
        id_path = os.path.join(self.dataset_dir, "user_identities.csv")
        with open(id_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                uid = row["user_id"]
                identity = UserIdentity(
                    user_id=uid,
                    current_name=row["name"],
                    current_email=row["email"],
                    current_phone=row["phone"],
                    current_email_hash=row["email_hash"],
                    snapshot_updated_at=row.get("updated_at", ""),
                )
                identity.all_emails.add(row["email"].lower())
                identity.all_phones.add(row["phone"])
                identity.all_email_hashes.add(row["email_hash"])
                if row["name"]:
                    identity.all_names.add(row["name"])
                self.users_by_id[uid] = identity
                self.email_to_user_id[row["email"].lower()] = uid

        # Load audit log for historical identifiers
        audit_path = os.path.join(self.dataset_dir, "user_audit_log.csv")
        with open(audit_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                uid = row["user_id"]
                if uid not in self.users_by_id:
                    continue
                identity = self.users_by_id[uid]
                field_name = row.get("field_name", "")
                old_val = row.get("old_value", "")
                new_val = row.get("new_value", "")

                if field_name == "email":
                    if old_val:
                        identity.all_emails.add(old_val.lower())
                        # Map old email to this user
                        self.email_to_user_id[old_val.lower()] = uid
                    if new_val:
                        identity.all_emails.add(new_val.lower())
                        self.email_to_user_id[new_val.lower()] = uid
                elif field_name == "phone":
                    if old_val:
                        identity.all_phones.add(old_val)
                    if new_val:
                        identity.all_phones.add(new_val)
                elif field_name == "email_hash":
                    if old_val:
                        identity.all_email_hashes.add(old_val)
                    if new_val:
                        identity.all_email_hashes.add(new_val)
                elif field_name == "name":
                    if old_val:
                        identity.all_names.add(old_val)
                    if new_val:
                        identity.all_names.add(new_val)

    def resolve(self, email: str) -> Optional[UserIdentity]:
        """Resolve an email (case-insensitive) to a UserIdentity."""
        uid = self.email_to_user_id.get(email.lower())
        if uid:
            return self.users_by_id.get(uid)
        return None

    def get_all_identifiers(self, user_id: str) -> Optional[UserIdentity]:
        """Get all identifiers for a user_id."""
        return self.users_by_id.get(user_id)
