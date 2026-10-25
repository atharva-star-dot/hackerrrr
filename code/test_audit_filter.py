# Test evidence file captured_at filter
manifest_captured_at = "2026-09-17T12:00:00Z"
audit_at = "2026-09-15T12:00:00Z"
print("Should be excluded:", manifest_captured_at > audit_at)
