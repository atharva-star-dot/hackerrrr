"""
Activity module - parses system_activity.csv for deletion, sync, restore events.
"""
import csv
import os
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class ActivityEvent:
    activity_id: str
    event_type: str
    system_id: str
    resource_id: str
    reported_result: str  # SUCCESS, FAILED, PARTIAL
    event_time: str
    details: str


class ActivityStore:
    """Stores and queries system activity events."""

    def __init__(self, dataset_dir: str):
        self.dataset_dir = dataset_dir
        self.events: List[ActivityEvent] = []
        self.events_by_resource: Dict[str, List[ActivityEvent]] = {}
        self.events_by_system: Dict[str, List[ActivityEvent]] = {}
        self._load()

    def _load(self):
        path = os.path.join(self.dataset_dir, "system_activity.csv")
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                evt = ActivityEvent(
                    activity_id=row.get("activity_id", ""),
                    event_type=row.get("event_type", ""),
                    system_id=row.get("system_id", ""),
                    resource_id=row.get("resource_id", ""),
                    reported_result=row.get("reported_result", ""),
                    event_time=row.get("event_time", ""),
                    details=row.get("details", ""),
                )
                self.events.append(evt)

                rid = evt.resource_id
                if rid not in self.events_by_resource:
                    self.events_by_resource[rid] = []
                self.events_by_resource[rid].append(evt)

                sid = evt.system_id
                if sid not in self.events_by_system:
                    self.events_by_system[sid] = []
                self.events_by_system[sid].append(evt)

    def get_events_for_resource(self, resource_id: str, before: Optional[str] = None) -> List[ActivityEvent]:
        """Get all events for a resource, optionally filtered by time."""
        events = self.events_by_resource.get(resource_id, [])
        if before:
            events = [e for e in events if e.event_time <= before]
        return sorted(events, key=lambda e: e.event_time)

    def get_classify_events(self) -> List[ActivityEvent]:
        """Get all CLASSIFY_REQUEST events."""
        return [e for e in self.events if e.event_type == "CLASSIFY_REQUEST"]

    def get_events_for_resources(self, resource_ids: set, before: Optional[str] = None) -> List[ActivityEvent]:
        """Get all events for a set of resource IDs."""
        results = []
        for rid in resource_ids:
            results.extend(self.get_events_for_resource(rid, before))
        return sorted(results, key=lambda e: e.event_time)
