# Logging

uvalu logs through **`uvalu/logkit/`** — structured JSON to a colorized
terminal and a rotating local file, driven by one config file
(`logging.config.json`). This page is the reference for the record schema, what
is and isn't logged, and the operational decisions. The phased rollout lives in
[logging-implementation-plan.md](logging-implementation-plan.md); the config-key
table is in [configuration.md](configuration.md#logging).

> **Status:** Phase 0 (pipeline + schema + `app.py` boot hooks) is in place.
> Individual call sites — auth, data mutations, external calls, background jobs —
> are instrumented in Phases 1–4.

---

## Quick start

```python
from uvalu import logkit

log = logkit.get_logger("uvalu.screener")          # name is prefixed to the uvalu.* tree
log.info("universe rebuilt", extra={"event": "job.ok", "rows": 1843})
log.warning("thin fundamentals row", extra={"event": "data_quality", "ticker": "XYZ.BR"})

try:
    ...
except Exception:
    log.exception("scrape failed", extra={"event": "external_call.failed",
                                          "endpoint": "stockanalysis.paris"})
```

Prefer the typed helpers in `logkit` over raw `extra=` dicts where one fits —
they keep the `event` slugs consistent:

```python
logkit.auth_event("login.ok", outcome="ok", user_id=uid, role="Analyst")
logkit.authz_denied(actor=uid, action="settings.write_shared", required_role="Admin", got_role="Viewer")
logkit.data_mutation(actor=uid, action="position.add", entity_type="ticker", entity_id="AAA.BR")
logkit.config_change(actor=uid, key="max_debt_equity", old=500.0, new=400.0, scope="shared")

with logkit.external_call("yfinance.download.history", params={"tickers": 42, "period": "5y"}) as call:
    ...
    call.note(status="rate_limited", retries=4)

with logkit.job("universe_rescore", trigger="cache_version_advance", items=n) as j:
    ...
    j.note(rows=1843)
```

### Correlation id

`app.py` calls `logkit.begin_run()` at the top of every rerun — a fresh
UUID4 stamped onto a `contextvars` slot, cleared of any user. After the auth
gate resolves the user, `logkit.bind(email=...)` attaches the pseudonymous
`user_id`.

Fragment (`@st.fragment`) and dialog (`@st.dialog`) reruns don't re-enter
`app.py`; call `logkit.ensure_run()` at their entry point so their records
still carry a correlation id (wired into `uvalu/ui.py` in Phase 4).

Background work must be started with **`logkit.spawn(target, ...)`** instead of
`threading.Thread(...).start()` — it copies the current context into the worker
(so its logs share the parent run's `correlation_id` / `user_id`) and logs any
crash as `job.failed` instead of letting it vanish on the worker thread.

---

## Record schema (v1)

One JSON object per line in the file sink. `metadata.schema_version` is the
migration handle for the future admin portal.

```json
{
  "timestamp": "2026-09-06T14:23:11.482Z",
  "level": "ERROR",
  "service": "uvalu",
  "module": "uvalu.marketdata",
  "correlation_id": "9f3a1c2e7b4d4e5a8b2f1d6c9e0a3f7b",
  "user_id": "1a2b3c4d5e6f7a8b",
  "message": "Price-history fetch failed",
  "metadata": {
    "schema_version": 1,
    "environment": "production",
    "build_version": "1.4.0",
    "event": "external_call.failed",
    "endpoint": "yfinance.download.history",
    "params": {"tickers": 42, "period": "5y"},
    "latency_ms": 3140,
    "status": "rate_limited",
    "retries": 4,
    "error_type": "YFRateLimitError",
    "error_fingerprint": "b7c1e0",
    "error_count": 12
  }
}
```

| Field | Notes |
|---|---|
| `timestamp` | UTC, ISO-8601, millisecond precision, `Z` suffix. Always UTC (`time.gmtime`). |
| `level` | `DEBUG` / `INFO` / `WARN` / `ERROR` / `CRITICAL`. Python `WARNING` is rendered `WARN`. |
| `service` | Always `"uvalu"` (single service today). |
| `module` | Logger name, dotted: `uvalu.auth`, `uvalu.screener.fetch`, `uvalu.render`, `uvalu.job`, … |
| `correlation_id` | UUID4 hex; per script run, propagated into `logkit.spawn` workers. `null` only before `begin_run()` runs. |
| `user_id` | `sha256(lower(email))[:16]` — the **same hash `portfolio.py` / `settings.py` use for data-dir slugs**. `null` when unauthenticated. |
| `message` | Short, human. **No interpolated identifiers or secret/PII values** — those go in `metadata`, and the redaction filter scrubs the message too. |
| `metadata.event` | Machine slug for filtering: `auth.login.ok`, `auth.login.failed`, `authz.denied`, `mutation`, `config.change`, `job.start`/`job.ok`/`job.failed`, `external_call.ok`/`external_call.failed`, `render`. |
| `metadata.stack` | Full traceback in `development` / `staging`; omitted in `production` (only `error_type` + `error_fingerprint` remain). Controlled by `stack_traces`. |
| `metadata.error_fingerprint` / `error_count` | Recurring exceptions with the same root cause share a 6-hex fingerprint; only the 1st and every 10th occurrence is emitted, carrying the running count. |

The colorized console line is a rendering of the same record, not a separate
format:

```
2026-09-06T14:23:11.482Z  ERROR    uvalu.marketdata  [9f3a1c2e/1a2b3c4d]  Price-history fetch failed  ·  event=external_call.failed  endpoint=yfinance.download.history  latency_ms=3140  status=rate_limited
```

WARN / ERROR / CRITICAL lines are wrapped in their level color so they stand out
while scrolling (spec §8).

---

## What is logged

| Category | Where | Phase |
|---|---|---|
| Auth events — login ok/failed (+ reason, never the password), logout, register/invite, session restore, session revocation | `auth.py`, `uvalu/authgate.py` | 1 |
| Authorization denials — admin/viewer gates, `PermissionError` on backup download, last-admin lockout blocks | `settings.py`, `uvalu/components.py`, `uvalu/pages_/admin.py`, `backup.py`, `auth.py` | 1 |
| Data mutations — portfolio CRUD, watchlist/targets, settings writes, admin user changes, backups | `portfolio.py`, `settings.py`, `auth.py`, `backup.py` | 2 |
| Config / feature-flag changes — shared & per-user settings, exchange toggles, master-key export (CRITICAL) | `settings.py`, `backup.py` | 2 |
| External calls — every yfinance / stockanalysis batch: endpoint, ticker count, `latency_ms`, outcome, retries | `prices.py`, `marketdata.py`, `screener.py`, `fetch_tickers.py`, `portfolio.py` | 3 |
| Background jobs — start / complete / failure + counts for the 4 workers | `screener.py`, `uvalu/store.py`, `uvalu/data.py`, `portfolio.py` | 3 |
| Errors & exceptions — every currently-swallowed `except` gets an `.exception()` (behaviour unchanged); `sys`/`threading` excepthooks | app-wide | 3–4 |
| Render telemetry — page, user, `duration_ms`, outcome; INFO for real navigations, DEBUG+sampled for timer/fragment reruns | `app.py`, `uvalu/ui.py` | 4 |

## What is NOT logged (spec §5)

Enforced by `RedactionFilter` over every record's message and `extra` metadata,
not left to callers:

- Passwords, JWTs, API keys, `AUTH_SECRET` / `ENCRYPTION_KEY`, Fernet tokens,
  bcrypt hashes, session cookies, the yfinance crumb — scrubbed by key name
  (denylist substring) and by value pattern.
- Raw email addresses — rewritten to `user:<hash>` in place.
- 13+ digit runs (card / SSN heuristic) — masked.

`tests/test_logkit.py` logs a payload containing each of these and asserts none
survive into the formatted output.

---

## Operational decisions

- **Timezone** — every timestamp is UTC. No local-time anywhere.
- **Retention** — 31 days (`retention_days`). Rotated backups past that age are
  deleted at startup and roughly daily. The active file is size-capped by
  `RotatingFileHandler` (≈55 MB total with defaults) as the hard disk-fill
  guard.
- **Terminal vs. file** — both, always (unless disabled in config). The terminal
  is ephemeral; the file at `logs/uvalu.log` is the reviewable history. `logs/`
  is gitignored.
- **Access (current phase)** — logs are the terminal where uvalu runs plus a
  local file; access is equivalent to access to the host. No separate ACL layer
  until logs are persisted beyond the host (syslog / admin portal — deferred).
- **Encryption** — the local log file is **not** encrypted at rest in this
  phase. It contains no secrets or raw PII by construction (redaction filter);
  encryption arrives with the persist-beyond-host phase (spec §7).
- **Account deletion** (spec §11, §13, decision **D12**) — `user_id` in logs is
  a non-reversible `sha256(email)[:16]` hash with no raw identifier retained, so
  historical logs are pseudonymised, not personal data. On account deletion the
  deletion event is logged; historical records are **not** rewritten (rewriting
  append-only audit logs on every deletion is worse for audit integrity than
  retaining an opaque hash). `scripts/scrub_log_user.py` is the manual tool for
  an explicit erasure request.
- **Health-check noise** — uvalu has no health endpoint of its own, but the 5 s
  `_auto_rerun` fragments are the equivalent high-frequency, low-value churn.
  Render telemetry for timer/fragment reruns is DEBUG and sampled to ~0 by
  default (`health_check_logging: false`, `sampling."uvalu.render"`).

---

## Testing

The autouse `_logkit_isolated` fixture in `tests/conftest.py` puts logkit in
**synchronous** mode (no queue thread, no file) and resets its process-global
state between tests. Assert on events with pytest's `caplog`; assert on the
formatted schema / redaction by constructing a `LogRecord` and running the
filter + `JsonFormatter` directly (see `tests/test_logkit.py`).
