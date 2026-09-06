"""Correlation-ID + user-ID context, and a context-preserving thread spawn.

Streamlit has no request object; the closest unit of work is a single script
run (a rerun). ``begin_run()`` stamps a fresh correlation id at the top of
``app.py`` on every run; ``ensure_run()`` covers ``@st.fragment`` / ``@st.dialog``
reruns that never re-enter ``app.py``. ``spawn()`` copies the current
``contextvars`` into a new daemon thread so a background worker's log records
carry the same correlation id + user id as the run that started it.
"""
from __future__ import annotations

import contextvars
import hashlib
import threading
import uuid
from typing import Callable

_correlation_id: contextvars.ContextVar["str | None"] = contextvars.ContextVar(
    "uv_correlation_id", default=None)
_user_id: contextvars.ContextVar["str | None"] = contextvars.ContextVar(
    "uv_user_id", default=None)


def begin_run() -> str:
    """Start a new logical run: fresh correlation id, cleared user. Call once at
    the very top of ``app.py`` on every rerun."""
    cid = uuid.uuid4().hex
    _correlation_id.set(cid)
    _user_id.set(None)
    return cid


def ensure_run() -> str:
    """Set a correlation id only if none is bound yet — for fragment / dialog
    reruns, which don't re-execute ``app.py``'s ``begin_run()``."""
    cid = _correlation_id.get()
    if cid is None:
        cid = uuid.uuid4().hex
        _correlation_id.set(cid)
    return cid


def correlation_id() -> "str | None":
    return _correlation_id.get()


def user_id() -> "str | None":
    return _user_id.get()


def user_hash(email: "str | None") -> "str | None":
    """``sha256(lower(email))[:16]`` — the same pseudonymous id ``portfolio.py``
    and ``settings.py`` derive for on-disk directory slugs, so a log line's
    ``user_id`` lines up with the user's data directory. Blank/None -> None."""
    e = (email or "").strip().lower()
    if not e:
        return None
    return hashlib.sha256(e.encode()).hexdigest()[:16]


def bind(*, user_id: "str | None" = None, email: "str | None" = None) -> None:
    """Attach the authenticated user to the current context. Pass a pre-hashed
    ``user_id``, or an ``email`` to hash here."""
    if email is not None:
        user_id = user_hash(email)
    _user_id.set(user_id)


def clear() -> None:
    """Drop both context values (test teardown; logout)."""
    _correlation_id.set(None)
    _user_id.set(None)


def spawn(target: Callable, *args, name: "str | None" = None,
          daemon: bool = True, **kwargs) -> threading.Thread:
    """``threading.Thread`` whose target runs inside a COPY of the caller's
    ``contextvars`` (so correlation id / user id propagate into the worker), with
    any exception logged as ``job.failed`` instead of vanishing on the worker
    thread. Starts the thread and returns it.
    """
    ctx = contextvars.copy_context()
    job_name = name or getattr(target, "__name__", "?")

    def _run() -> None:
        try:
            ctx.run(target, *args, **kwargs)
        except BaseException:  # noqa: BLE001 — outer net; re-raise would only reach threading.excepthook
            from uvalu.logkit import get_logger
            get_logger("uvalu.job").exception(
                "uncaught exception in spawned worker",
                extra={"event": "thread.uncaught", "job": job_name},
            )

    t = threading.Thread(target=_run, name=name, daemon=daemon)
    t.start()
    return t
