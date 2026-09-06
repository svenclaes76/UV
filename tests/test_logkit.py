"""Unit tests for uvalu/logkit/ — Phase 0 of the logging system.

The autouse ``_logkit_isolated`` fixture in conftest.py already puts logkit in
synchronous, file-less mode and resets its process-global state around every
test. These tests exercise the schema, redaction, context propagation,
sampling, error fingerprinting, retention purge and idempotent init directly —
mostly by driving a ``LogRecord`` through the filters + formatter rather than
through the handler tree, so assertions don't depend on capture plumbing.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import sys
import threading
import time

import pytest

from uvalu import logkit
from uvalu.logkit import config as _config
from uvalu.logkit import filters as _filters
from uvalu.logkit import retention as _retention
from uvalu.logkit import setup as _setup
from uvalu.logkit.formatters import ColorTextFormatter, JsonFormatter


# ── helpers ────────────────────────────────────────────────────────────────

def _record(msg="hello", *, name="uvalu.test", level=logging.INFO, args=(),
            exc_info=None, **extra) -> logging.LogRecord:
    rec = logging.LogRecord(name, level, __file__, 10, msg, args, exc_info)
    for k, v in extra.items():
        setattr(rec, k, v)
    return rec


def _through_filters(rec: logging.LogRecord) -> "logging.LogRecord | None":
    for f in _filters.all_filters():
        if not f.filter(rec):
            return None
    return rec


def _json_line(rec: logging.LogRecord, *, include_stack=True) -> dict:
    rec = _through_filters(rec)
    assert rec is not None
    return json.loads(JsonFormatter(include_stack=include_stack).format(rec))


def _exc_info(exc_factory):
    try:
        exc_factory()
    except Exception:  # noqa: BLE001
        return sys.exc_info()
    raise AssertionError("factory did not raise")


# ── schema ─────────────────────────────────────────────────────────────────

def test_json_record_has_all_top_level_fields():
    entry = _json_line(_record("something happened", event="job.ok", rows=3))
    assert set(entry) == {
        "timestamp", "level", "service", "module",
        "correlation_id", "user_id", "message", "metadata",
    }
    assert entry["service"] == "uvalu"
    assert entry["module"] == "uvalu.test"
    assert entry["message"] == "something happened"
    md = entry["metadata"]
    assert md["schema_version"] == 1
    assert md["event"] == "job.ok"
    assert md["rows"] == 3
    assert md["environment"] == "development"
    assert md["build_version"] and md["build_version"] != "unknown"


def test_timestamp_is_utc_iso8601_millis():
    entry = _json_line(_record())
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", entry["timestamp"])


def test_python_warning_level_renders_as_warn():
    assert _json_line(_record(level=logging.WARNING))["level"] == "WARN"
    assert _json_line(_record(level=logging.CRITICAL))["level"] == "CRITICAL"


def test_build_version_matches_pyproject():
    import tomllib
    from pathlib import Path
    want = tomllib.loads(
        (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text()
    )["project"]["version"]
    assert _json_line(_record())["metadata"]["build_version"] == want


def test_context_filter_uses_bound_correlation_and_user():
    logkit.begin_run()
    logkit.bind(email="Alice@Example.com")
    entry = _json_line(_record())
    assert entry["correlation_id"] and len(entry["correlation_id"]) == 32
    assert entry["user_id"] == hashlib.sha256(b"alice@example.com").hexdigest()[:16]


def test_explicit_user_id_on_record_wins_over_context():
    logkit.begin_run()
    logkit.bind(email="alice@example.com")
    entry = _json_line(_record(user_id="deadbeefdeadbeef"))
    assert entry["user_id"] == "deadbeefdeadbeef"


# ── environment / stack traces ─────────────────────────────────────────────

def test_environment_follows_uvalu_env(monkeypatch):
    monkeypatch.setenv("UVALU_ENV", "production")
    assert _json_line(_record())["metadata"]["environment"] == "production"


def test_config_environment_overrides_env_var(monkeypatch):
    monkeypatch.setenv("UVALU_ENV", "production")
    monkeypatch.setattr(_config, "_current",
                        {**_config.DEFAULTS, "environment": "staging"})
    assert _config.resolve_environment() == "staging"


def test_include_stack_auto_is_off_in_production_only():
    assert _setup._include_stack({"stack_traces": "auto"}, "development") is True
    assert _setup._include_stack({"stack_traces": "auto"}, "staging") is True
    assert _setup._include_stack({"stack_traces": "auto"}, "production") is False
    assert _setup._include_stack({"stack_traces": "always"}, "production") is True
    assert _setup._include_stack({"stack_traces": "never"}, "development") is False


def test_stack_included_or_omitted_per_flag():
    ei = _exc_info(lambda: 1 / 0)
    with_stack = _json_line(_record("boom", level=logging.ERROR, exc_info=ei),
                            include_stack=True)["metadata"]
    assert "stack" in with_stack and "ZeroDivisionError" in with_stack["stack"]
    assert with_stack["error_type"] == "ZeroDivisionError"

    ei = _exc_info(lambda: 1 / 0)
    no_stack = _json_line(_record("boom", level=logging.ERROR, exc_info=ei),
                          include_stack=False)["metadata"]
    assert "stack" not in no_stack
    assert no_stack["error_type"] == "ZeroDivisionError"


def test_exception_args_in_stack_are_scrubbed():
    ei = _exc_info(lambda: (_ for _ in ()).throw(
        ValueError("token eyJhbGc.eyJzdWI.sig_9 for bob@example.com")))
    entry = _json_line(_record("failed", level=logging.ERROR, exc_info=ei))
    blob = json.dumps(entry)
    assert "eyJhbGc.eyJzdWI.sig_9" not in blob
    assert "bob@example.com" not in blob
    assert "[redacted]" in entry["metadata"]["stack"]


def test_message_field_never_carries_the_traceback():
    ei = _exc_info(lambda: 1 / 0)
    entry = _json_line(_record("handled", level=logging.ERROR, exc_info=ei))
    assert entry["message"] == "handled"
    assert "Traceback" not in entry["message"]


def test_record_queue_handler_keeps_exc_info_and_msg_intact():
    import queue as _q
    from uvalu.logkit.setup import _RecordQueueHandler

    ei = _exc_info(lambda: 1 / 0)
    q = _q.Queue()
    qh = _RecordQueueHandler(q)
    rec = _record("handled", level=logging.ERROR, exc_info=ei)
    qh.emit(rec)
    out = q.get_nowait()
    assert out.exc_info is ei          # not rendered away for pickling
    assert out.msg == "handled"


# ── redaction (spec §5) ───────────────────────────────────────────────────

@pytest.mark.parametrize("secret", [
    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.abcDEF-_123",   # JWT
    "gAAAAA" + "B" * 40,                                    # Fernet token
    "$2b$12$" + "A" * 53,                                   # bcrypt hash
    "a" * 64,                                               # 64-hex (AUTH_SECRET / ENCRYPTION_KEY)
    "4111 1111 1111 1111",                                  # 16-digit run
])
def test_secret_patterns_scrubbed_from_message(secret):
    entry = _json_line(_record(f"leaked value = {secret} end"))
    assert secret not in json.dumps(entry)
    assert "[redacted]" in entry["message"]


def test_raw_email_in_message_replaced_by_hash():
    entry = _json_line(_record("user bob@example.com signed in"))
    blob = json.dumps(entry)
    assert "bob@example.com" not in blob
    assert f"user:{logkit.user_hash('bob@example.com')}" in entry["message"]


def test_sensitive_metadata_keys_blanked():
    entry = _json_line(_record(
        "auth attempt",
        password="hunter2", jwt_token="eyJ.a.b", api_key="sk-live-123",
        role="Analyst",
    ))
    md = entry["metadata"]
    assert md["password"] == "[redacted]"
    assert md["jwt_token"] == "[redacted]"
    assert md["api_key"] == "[redacted]"
    assert md["role"] == "Analyst"          # non-sensitive key untouched


def test_nested_metadata_is_scrubbed():
    entry = _json_line(_record("cfg", after={"secret": "x", "max_debt_equity": 400.0}))
    assert entry["metadata"]["after"]["secret"] == "[redacted]"
    assert entry["metadata"]["after"]["max_debt_equity"] == 400.0


# ── correlation-id propagation into threads ───────────────────────────────

def test_spawn_propagates_context_into_worker():
    logkit.begin_run()
    logkit.bind(email="alice@example.com")
    parent_cid = logkit.correlation_id()
    seen: dict = {}

    def _work():
        seen["cid"] = logkit.correlation_id()
        seen["uid"] = logkit.user_id()

    logkit.spawn(_work, name="test-worker").join(timeout=2)
    assert seen["cid"] == parent_cid
    assert seen["uid"] == hashlib.sha256(b"alice@example.com").hexdigest()[:16]


def test_spawn_logs_worker_crash_as_job_failed(caplog):
    caplog.set_level(logging.DEBUG, logger="uvalu")
    logkit.begin_run()

    def _boom():
        raise RuntimeError("worker exploded")

    logkit.spawn(_boom, name="doomed-worker").join(timeout=2)
    failures = [r for r in caplog.records
                if getattr(r, "event", None) == "job.failed"
                and getattr(r, "job", None) == "doomed-worker"]
    assert failures and failures[0].exc_info is not None


# ── sampling (spec §9) ───────────────────────────────────────────────────

def test_sampling_drops_configured_level_keeps_warn(monkeypatch):
    monkeypatch.setattr(_config, "_current", {
        **_config.DEFAULTS,
        "sampling": {"uvalu.render": {"level": "DEBUG", "rate": 0.0}},
    })
    sf = _filters.sampling_filter
    assert sf.filter(_record(name="uvalu.render", level=logging.DEBUG)) is False
    # INFO on that logger isn't the sampled level -> passes
    assert sf.filter(_record(name="uvalu.render", level=logging.INFO)) is True
    # WARN is never sampled
    assert sf.filter(_record(name="uvalu.render", level=logging.WARNING)) is True
    # a logger with no rule passes
    assert sf.filter(_record(name="uvalu.other", level=logging.DEBUG)) is True


def test_sampling_keeps_one_in_n(monkeypatch):
    monkeypatch.setattr(_config, "_current", {
        **_config.DEFAULTS,
        "sampling": {"uvalu.noisy": {"rate": 0.25}},
    })
    _filters.reset()
    kept = sum(
        _filters.sampling_filter.filter(_record(name="uvalu.noisy", level=logging.INFO))
        for _ in range(100)
    )
    assert 20 <= kept <= 30


# ── error fingerprinting (spec §10) ─────────────────────────────────────

def test_fingerprint_is_stable_and_counts_and_dedupes():
    _filters.reset()
    ff = _filters.fingerprint_filter

    def raise_ve(n):
        try:
            raise ValueError(f"bad row {n}")
        except ValueError:
            return sys.exc_info()

    r1 = _record("err", level=logging.ERROR, exc_info=raise_ve(1))
    assert ff.filter(r1) is True
    assert r1.error_count == 1
    fp = r1.error_fingerprint

    # digit-normalised message -> same fingerprint; occurrences 2..9 dropped
    dropped = 0
    for n in range(2, 10):
        r = _record("err", level=logging.ERROR, exc_info=raise_ve(n))
        keep = ff.filter(r)
        assert r.error_fingerprint == fp
        assert r.error_count == n
        dropped += (keep is False)
    assert dropped == 8

    # 10th occurrence passes again, carrying the running count
    r10 = _record("err", level=logging.ERROR, exc_info=raise_ve(10))
    assert ff.filter(r10) is True
    assert r10.error_count == 10


def test_error_stats_exposes_the_table():
    _filters.reset()
    try:
        raise KeyError("x")
    except KeyError:
        _filters.fingerprint_filter.filter(_record("e", level=logging.ERROR, exc_info=sys.exc_info()))
    stats = logkit.error_stats()
    assert len(stats) == 1
    (entry,) = stats.values()
    assert entry["count"] == 1 and entry["first"] <= entry["last"]


# ── retention purge (spec §6, §11) ─────────────────────────────────────

def test_retention_sweep_deletes_only_aged_backups(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    active = logs / "uvalu.log"
    old = logs / "uvalu.log.7"
    fresh = logs / "uvalu.log.1"
    for p in (active, old, fresh):
        p.write_text("x")
    aged = time.time() - 40 * 86400
    import os
    os.utime(old, (aged, aged))

    cfg = {**_config.DEFAULTS, "retention_days": 31,
           "file": {**_config.DEFAULTS["file"], "path": "logs/uvalu.log"}}
    removed = _retention.sweep(cfg, log_dir=tmp_path)

    assert removed == 1
    assert not old.exists()
    assert fresh.exists() and active.exists()


def test_retention_sweep_noop_when_folder_missing(tmp_path):
    cfg = {**_config.DEFAULTS, "file": {**_config.DEFAULTS["file"], "path": "logs/uvalu.log"}}
    assert _retention.sweep(cfg, log_dir=tmp_path) == 0


# ── idempotent init ───────────────────────────────────────────────────────

def test_init_logging_is_idempotent_under_concurrent_calls(tmp_path):
    _setup._reset_for_tests()
    barrier = threading.Barrier(6)

    def _init():
        barrier.wait()
        _setup.init_logging(synchronous=True, log_dir=tmp_path)

    threads = [threading.Thread(target=_init) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=3)

    handlers = logging.getLogger("uvalu").handlers
    assert len(handlers) == 1


# ── user hash contract ──────────────────────────────────────────────────

def test_user_hash_matches_the_data_dir_slug_scheme():
    # Same formula portfolio._user_dir / settings._settings_file use.
    assert logkit.user_hash("Foo@Bar.com") == hashlib.sha256(b"foo@bar.com").hexdigest()[:16]
    assert logkit.user_hash("") is None
    assert logkit.user_hash(None) is None


# ── event helpers (events.py) ──────────────────────────────────────────

def _captured():
    """Attach a list-capturing handler (with the real filters) to the uvalu
    logger and return (handler, records)."""
    recs: list[logging.LogRecord] = []

    class _H(logging.Handler):
        def emit(self, record):
            recs.append(record)

    h = _H(level=logging.DEBUG)
    for f in _filters.all_filters():
        h.addFilter(f)
    logging.getLogger("uvalu").addHandler(h)
    return h, recs


def test_auth_event_levels_and_fields():
    h, recs = _captured()
    try:
        logkit.begin_run()
        logkit.auth_event("login.ok", outcome="ok", user_id="abc123", role="Admin")
        logkit.auth_event("login.failed", outcome="failed", reason="bad_password")
    finally:
        logging.getLogger("uvalu").removeHandler(h)
    ok, failed = recs
    assert ok.name == "uvalu.auth" and ok.levelno == logging.INFO
    assert ok.event == "auth.login.ok" and ok.user_id == "abc123" and ok.role == "Admin"
    assert failed.levelno == logging.WARNING
    assert failed.event == "auth.login.failed" and failed.reason == "bad_password"


def test_authz_denied_shape():
    h, recs = _captured()
    try:
        logkit.authz_denied(action="admin.view", actor="u1", required_role="Admin",
                            got_role="Viewer", resource="page:admin")
    finally:
        logging.getLogger("uvalu").removeHandler(h)
    (rec,) = recs
    assert rec.name == "uvalu.authz" and rec.levelno == logging.WARNING
    assert rec.event == "authz.denied" and rec.action == "admin.view"
    assert rec.got_role == "Viewer" and rec.resource == "page:admin"


def test_data_mutation_shape():
    h, recs = _captured()
    try:
        logkit.data_mutation(actor="u1", action="user.create", entity_type="user",
                             entity_id="deadbeef", bootstrap_admin=True)
    finally:
        logging.getLogger("uvalu").removeHandler(h)
    (rec,) = recs
    assert rec.name == "uvalu.mutation" and rec.event == "mutation"
    assert rec.action == "user.create" and rec.entity_id == "deadbeef"
    assert rec.bootstrap_admin is True


# ── console formatter ───────────────────────────────────────────────────

def test_color_formatter_wraps_error_lines_and_plain_mode_does_not():
    rec = _through_filters(_record("kaboom", level=logging.ERROR, event="render"))
    colored = ColorTextFormatter(color=True, include_stack=False).format(rec)
    plain = ColorTextFormatter(color=False, include_stack=False).format(rec)
    assert "\033[" in colored
    assert "\033[" not in plain
    assert "kaboom" in plain and "event=render" in plain
