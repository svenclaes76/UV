"""
Compliance records for "Uvalu — Legal Requirements for Launch".

signal_history  REC-7 / REC-11: badge-change log and daily signal snapshots
settings_audit  REC-9 / REC-11: planned changes, shared-settings changes, model versions

Both write append-only files under data/compliance/. They are regulatory
evidence: keep them in the server-level backup (the per-user backup ZIPs do
not include them). See docs/legal/compliance-implementation-plan.md.
"""
