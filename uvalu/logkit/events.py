"""Typed one-liner helpers so call sites stay terse and the ``event`` slugs stay
consistent across the app.

Phase 0 ships the API and its tests; the auth / mutation / external-call / job
call sites are wired in later phases (see docs/logging-implementation-plan.md).
"""
from __future__ import annotations

import time
from contextlib import contextmanager

from uvalu.logkit import get_logger


def auth_event(event: str, *, outcome: str = "ok", user_id=None, reason=None, **meta) -> None:
    """``auth.<event>`` — outcome one of ``ok`` / ``failed`` / ``revoked``. A
    non-``ok`` outcome logs at WARN, ``ok`` at INFO."""
    log = get_logger("uvalu.auth")
    extra = {"event": f"auth.{event}", "outcome": outcome, **meta}
    if user_id is not None:
        extra["user_id"] = user_id
    if reason:
        extra["reason"] = reason
    emit = log.warning if outcome in ("failed", "denied", "revoked") else log.info
    emit("auth %s: %s", event, outcome, extra=extra)


def authz_denied(*, action, actor=None, required_role=None, got_role=None,
                 resource=None, **meta) -> None:
    """``authz.denied`` — a role/ownership gate refused ``action``. ``actor`` is
    the acting user hash when the caller has it (the ``user_id`` context field
    also carries it); ``resource`` names the thing they were denied."""
    get_logger("uvalu.authz").warning(
        "authorization denied: %s", action,
        extra={
            "event": "authz.denied", "actor": actor, "action": action,
            "required_role": required_role, "got_role": got_role,
            "resource": resource, **meta,
        },
    )


def data_mutation(*, actor, action, entity_type, entity_id=None,
                  before=None, after=None, **meta) -> None:
    """``mutation`` — a create/update/delete. ``entity_id`` may be omitted for a
    collection-wide change (e.g. a watchlist replace). Pass ``before``/``after``
    only for cheap scalars — never a DataFrame or a money amount."""
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


def render_event(page, duration_ms: int, *, is_navigation: bool, outcome: str = "ok") -> None:
    """Page-render telemetry (spec §4 "API requests"). A real navigation logs at
    INFO; a timer/fragment re-render logs at DEBUG only when
    ``health_check_logging`` is on (uvalu has no health endpoint, but the 5s
    auto-rerun fragments are the equivalent churn — spec §11)."""
    from uvalu.logkit import config as _config
    log = get_logger("uvalu.render")
    extra = {"event": "render", "page": page, "outcome": outcome,
             "duration_ms": duration_ms, "kind": "navigation" if is_navigation else "rerun"}
    if is_navigation or outcome != "ok":
        log.info("rendered %s", page, extra=extra)
    elif _config.current().get("health_check_logging", False):
        log.debug("re-rendered %s", page, extra=extra)


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
def job(name: str, *, trigger=None, reraise: bool = True, **meta):
    """Bracket a background job with ``job.start`` / ``job.ok`` / ``job.failed``
    (+ ``latency_ms``). Use ``.note(**counts)`` to attach completion metadata.

    ``reraise=False`` for a top-level worker body with no caller that would
    catch — the failure is logged and swallowed so the (daemon) thread just
    ends. Leave it True when an outer ``try`` already handles the exception, to
    avoid a duplicate log from ``spawn``'s thread guard."""
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
        if reraise:
            raise
        return
    dt = int((time.perf_counter() - t0) * 1000)
    log.info("job complete: %s", name,
             extra={"event": "job.ok", "job": name, "latency_ms": dt, **result})
