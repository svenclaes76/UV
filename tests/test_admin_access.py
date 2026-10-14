"""L16: the 24-month record of admin actions on another user's account."""

from datetime import datetime, timedelta, timezone

import pytest

from uvalu.compliance import admin_access
from uvalu.logkit.context import user_hash


def test_record_stores_pseudonymous_ids_action_and_time(tmp_path):
    path = tmp_path / "access.jsonl"
    admin_access.record("Boss@Example.com", "user@example.com", "reset_two_factor", path=path)
    (rec,) = admin_access.for_user("USER@example.com", path=path)
    assert rec["actor"] == user_hash("boss@example.com")
    assert rec["target"] == user_hash("user@example.com")
    assert rec["action"] == "reset_two_factor"
    assert "user@example.com" not in path.read_text(encoding="utf-8")   # no plain emails


def test_unknown_actions_are_refused(tmp_path):
    with pytest.raises(ValueError):
        admin_access.record("a@example.com", "b@example.com", "peeked", path=tmp_path / "x.jsonl")


def test_records_older_than_24_months_are_pruned(tmp_path):
    path = tmp_path / "access.jsonl"
    old = datetime.now(timezone.utc) - timedelta(days=admin_access.ADMIN_ACCESS_KEEP_DAYS + 1)
    admin_access.record("a@example.com", "b@example.com", "role_change", at=old, path=path)
    admin_access.record("a@example.com", "b@example.com", "status_change", path=path)
    assert [r["action"] for r in admin_access.for_user("b@example.com", path=path)] == ["status_change"]
