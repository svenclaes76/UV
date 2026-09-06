"""Typed one-liner helpers so call sites stay terse and the ``event`` slugs stay
consistent across the app.

Phase 0 ships the API and its tests; the auth / mutation / external-call / job
call sites are wired in later phases (see docs/logging-implementation-plan.md).
"""
from __future__ import annotations

import time
from contextlib import contextmanager

from uvalu.logkit import get_logger


def auth_event(event: str, *, outcome: str, user_id=None, reason=None, **meta) -> None:
    """``auth.<event>`` — outcome one of ``ok`` / ``failed`` / ``revoked``."""
    log = get_logger("uvalu.auth")
    extra = {"event": f"auth.{event}", "outcome": outcome, **meta}
    if user_id is not None:
        extra["user_id"] = user_id
    if reason:
        extra["reason"] = reason
    emit = log.warning if outcome in ("failed", "denied", "revoked") else log.info
    emit("auth %s: %s", event, outcome, extra=extra)


def authz_denied(*, actor, action, required_role=None, got_role=None, resource=None) -> None:
    get_logger("uvalu.authz").warning(
        "authorization denied: %s", action,
        extra={
            "event": "authz.denied", "actor": actor, "action": action,
            "required_role": required_role, "got_role": got_role, "resource": resource,
        },
    )


def data_mutation(*, actor, action, entity_type, entity_id,
                  before=None, after=None, **meta) -> None:
    get_logger("uvalu.mutation").info(
        "data mutation: %s", action,
        extra={
            "event": "mutation", "actor": actor, "action": action,
            "entity_type": entity_type, "entity_id": entity_id,
            "before": before, "after": after, **meta,
        },
    )


def config_change(*, actor, key, old, new, scope) -> None:
    get_logger("uvalu.config").info(
        "config change: %s", key,
        extra={
            "event": "config.change", "actor": actor, "key": key,
            "old": old, "new": new, "scope": scope,
        },
    )


class _Note:
    def __init__(self, state: dict) -> None:
        self._state = state

    def note(self, **kw) -> None:
        if "status" in kw:
            self._state["status"] = kw.pop("status")
        self._state["extra"].update(kw)


@contextmanager
def external_call(endpoint: str, *, params=None, logger: str = "uvalu.external"):
    """Time an outbound call; log ``external_call.ok`` / ``.<status>`` / ``.failed``
    with ``latency_ms``. Use ``.note(status=..., retries=...)`` inside the block."""
    log = get_logger(logger)
    state = {"status": "ok", "extra": {}}
    t0 = time.perf_counter()
    try:
        yield _Note(state)
    except Exception:
        dt = int((time.perf_counter() - t0) * 1000)
        log.exception(
            "external call failed: %s", endpoint,
            extra={"event": "external_call.failed", "endpoint": endpoint,
                   "params": params, "latency_ms": dt, "status": "failed",
                   **state["extra"]},
        )
        raise
    dt = int((time.perf_counter() - t0) * 1000)
    status = state["status"]
    emit = log.info if status == "ok" else log.warning
    emit(
        "external call: %s", endpoint,
        extra={"event": f"external_call.{'ok' if status == 'ok' else status}",
               "endpoint": endpoint, "params": params, "latency_ms": dt,
               "status": status, **state["extra"]},
    )


@contextmanager
def job(name: str, *, trigger=None, **meta):
    """Bracket a background job with ``job.start`` / ``job.ok`` / ``job.failed``
    (+ ``latency_ms``). Use ``.note(**counts)`` to attach completion metadata."""
    log = get_logger("uvalu.job")
    t0 = time.perf_counter()
    log.info("job start: %s", name,
             extra={"event": "job.start", "job": name, "trigger": trigger, **meta})
    result: dict = {}
    try:
        yield _Note({"status": "ok", "extra": result})
    except Exception:
        dt = int((time.perf_counter() - t0) * 1000)
        log.exception("job failed: %s", name,
                      extra={"event": "job.failed", "job": name, "latency_ms": dt, **result})
        raise
    dt = int((time.perf_counter() - t0) * 1000)
    log.info("job complete: %s", name,
             extra={"event": "job.ok", "job": name, "latency_ms": dt, **result})
