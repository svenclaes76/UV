"""uvalu logging system (**logkit**).

Structured JSON logs to a colorized terminal + a rotating local file, one config
file (``logging.config.json``), correlation ids propagated into background
threads, secret/PII redaction, sampling, and recurring-error grouping. See
``docs/logging.md`` for the record schema and ``docs/logging-implementation-plan.md``
for the rollout.

Phase 0 wires the pipeline and the ``app.py`` boot hooks; individual call sites
(auth, mutations, external calls, jobs) are instrumented in later phases.

    from uvalu import logkit
    logkit.init_logging()          # idempotent; safe every rerun
    logkit.begin_run()             # fresh correlation id per script run
    logkit.bind(email=user_email)  # attach the authenticated user
    log = logkit.get_logger("uvalu.auth")
"""
from __future__ import annotations

import logging


def get_logger(name: str = "uvalu") -> logging.Logger:
    """Return a logger under the ``uvalu`` tree (all handlers/filters live on
    that root). A bare or non-``uvalu`` name is prefixed."""
    if name != "uvalu" and not name.startswith("uvalu."):
        name = "uvalu." + name
    return logging.getLogger(name)


from uvalu.logkit.context import (begin_run, bind, clear, correlation_id,  # noqa: E402
                                  ensure_run, spawn, user_hash, user_id)
from uvalu.logkit.setup import error_stats, init_logging  # noqa: E402
from uvalu.logkit.events import (auth_event, authz_denied, config_change,  # noqa: E402
                                 data_mutation, external_call, job, render_event)

__all__ = [
    "init_logging", "get_logger", "begin_run", "ensure_run", "bind", "clear",
    "correlation_id", "user_id", "user_hash", "spawn", "error_stats",
    "auth_event", "authz_denied", "config_change", "data_mutation",
    "external_call", "job", "render_event",
]
