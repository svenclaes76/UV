# Logging System — Implementation Plan

Derived from `uvalu-logging-requirements.md` (the spec), mapped onto uvalu's
actual architecture: a single-process Streamlit app that serves every session
from pooled threads, spawns raw `threading.Thread` background workers in five
places, has **no HTTP request/response layer of its own** (Tornado owns that),
and currently logs nothing — 23 stray `print()` calls and `except Exception:
pass` swallow-everything handlers throughout.

The spec's v1 scope is: **structured logs to terminal + a rotating local file,
driven by one config file. No admin portal, no syslog, no paging.** Section 12
(admin portal) is explicitly deferred; this plan only keeps the door open for it
(stable schema, an `error_stats()` hook).

---

## 1. Design decisions (recommended defaults)

| # | Decision | Recommendation | Rationale |
|---|---|---|---|
| D1 | Logging backend | stdlib `logging` + `QueueHandler`/`QueueListener` | Async/non-blocking (spec §9) with zero new deps. |
| D2 | Config file format | **JSON** — `logging.config.json` at repo root, committed with defaults | No new dep (`settings.py` is already JSON); trivially writable by the future admin portal (spec §12 "portal writes to the same config file"). TOML would match `.streamlit/config.toml` but stdlib `tomllib` is read-only. |
| D3 | JSON log formatter | Hand-rolled `logging.Formatter` subclass | ~40 lines; avoids pinning `python-json-logger`. |
| D4 | Console format | Colorized key=value line when `stderr.isatty()` **and** `NO_COLOR` unset; JSON otherwise | Readable while scrolling a terminal (spec §8); greppable when piped/redirected. Overridable per-config. |
| D5 | File format | One JSON object per line, always | The stable schema (spec §11) — never colorized, never reformatted. |
| D6 | Log file location | `logs/uvalu.log` under repo root (add `logs/` to `.gitignore`) | Mirrors `.cache/` / `data/` convention. |
| D7 | Correlation ID unit | One UUID4 per **script run** (Streamlit rerun), propagated into child threads via `contextvars` | Streamlit has no request; a rerun is the closest analogue. |
| D8 | User identifier in logs | `sha256(email.lower())[:16]` — the **same hash `portfolio.py` / `settings.py` already use for data-dir slugs** | Pseudonymous (spec §13), and log `user_id` lines up 1:1 with the user's on-disk directory for debugging. |
| D9 | Environment tag | New `UVALU_ENV` env var in `.env` (`development` \| `staging` \| `production`), default `development` | No env concept exists today. |
| D10 | Build/version tag | Parse `[project].version` from `pyproject.toml` once at startup via stdlib `tomllib` | Single source of truth; no duplicated constant. |
| D11 | Retention | Default **31 days**, size-capped rotation as the hard disk-fill guard | Spec §6 "1 month"; §11 "must not fill the disk". |
| D12 | Account deletion (spec §11, §13) | Keep the pseudonymous hash in historical logs; log the deletion event; **no back-scrub** in v1. Ship `scripts/scrub_log_user.py` as the manual erasure tool. | The hash carries no raw identifier, so retained logs are pseudonymised, not personal data. Rewriting append-only audit logs on every deletion is worse for audit integrity. |
| D13 | Health-check / auto-rerun noise (spec §11) | The 5 s `_auto_rerun` fragment ticks are uvalu's "health-check noise". Render-telemetry logs for fragment/timer reruns are **DEBUG + sampled to ~0** by default; a genuine page navigation logs at INFO. | Keeps the terminal readable. |

**All decisions confirmed (2026-09-06):** JSON config file (D2), colorized
console (D4), add `UVALU_ENV` (D9), keep the pseudonymous hash with no
back-scrub (D12). Phase 0 can start.

---

## 2. Log record schema (freeze before any instrumentation — spec §11)

One JSON object per line. `metadata.schema_version` lets the future admin
portal migrate.

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
    "endpoint": "yfinance.download",
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

| Field | Source | Notes |
|---|---|---|
| `timestamp` | `time.gmtime` in the formatter | UTC, ISO-8601, ms precision, `Z` suffix (spec §3, §11 timezone). |
| `level` | record | Python `WARNING` rendered as `WARN`; `CRITICAL` kept. |
| `service` | constant | Always `"uvalu"` (single service today). |
| `module` | logger name | Dotted: `uvalu.auth`, `uvalu.screener.fetch`, `uvalu.render`, `uvalu.job`. |
| `correlation_id` | `contextvars` (see §4) | Always present; generated at run start. |
| `user_id` | `contextvars`, set after auth | `null` when unauthenticated (login screen, cold boot). |
| `message` | caller | Short, human, **no interpolated identifiers or values** — those go in `metadata`. |
| `metadata.event` | caller | Machine slug for filtering: `auth.login.ok`, `auth.login.failed`, `authz.denied`, `mutation`, `config.change`, `job.start/ok/failed`, `external_call.ok/failed`, `render`. |
| `metadata.stack` | formatter | Full traceback in `development`/`staging`; omitted in `production` (replaced by `error_type` + `error_fingerprint`) — spec §4, §10, §13. |

---

## 3. Module layout — `uvalu/logkit/`

New package (name avoids any ambiguity with stdlib `logging`).

```
uvalu/logkit/
  __init__.py      # public API: init_logging, get_logger, begin_run, ensure_run,
                   #             bind, user_hash, spawn, error_stats, and the
                   #             event helpers re-exported from events.py
  config.py        # load logging.config.json, defaults, mtime hot-reload poll
  setup.py         # init_logging(): queue + listener + handlers; idempotent singleton
  formatters.py    # JsonFormatter, ColorTextFormatter
  filters.py       # ContextFilter, RedactionFilter, SamplingFilter, FingerprintFilter
  context.py       # ContextVars, correlation-id lifecycle, spawn() thread wrapper
  events.py        # auth_event, authz_denied, data_mutation, config_change,
                   #   external_call() ctx mgr, job() ctx mgr
  retention.py     # startup + once-daily purge of rotated files older than retention_days
```

### 3.1 `setup.init_logging()`

- Module-level `_initialised` flag + `threading.Lock` — safe when two session
  threads hit a cold process simultaneously (same pattern as
  `screener._warm_live_cache`).
- Builds: `QueueHandler` on the root `uvalu` logger → bounded `queue.Queue`
  (`queue_capacity`, default 10 000) → `QueueListener` on a daemon thread
  fanning out to:
  - `StreamHandler(sys.stderr)` with `ColorTextFormatter` or `JsonFormatter`
    per D4.
  - `RotatingFileHandler(path, maxBytes=max_bytes, backupCount=backup_count)`
    with `JsonFormatter`.
- Queue-full policy: block for CRITICAL/ERROR/WARN; drop-and-count for
  INFO/DEBUG (the count is itself logged once per minute).
- Attaches `ContextFilter`, `RedactionFilter`, `SamplingFilter`,
  `FingerprintFilter` to the handlers (not the logger, so child loggers can't
  bypass them).
- Installs `sys.excepthook` and `threading.excepthook` → CRITICAL structured
  record, then chains to the original hook.
- Calls `retention.sweep()` once, and arms the daily sweep on the listener
  thread.
- In tests (`PYTEST_CURRENT_TEST` set, or an explicit `synchronous=True`): skip
  the queue/listener, no file handler, attach a plain `StreamHandler` so
  `caplog` works.

### 3.2 `context.py`

```python
_CORRELATION_ID: ContextVar[str | None] = ContextVar("uv_correlation_id", default=None)
_USER_ID:        ContextVar[str | None] = ContextVar("uv_user_id", default=None)

def begin_run() -> None            # new UUID4, clear user — top of app.py per rerun
def ensure_run() -> None           # set one only if missing — fragment / dialog entry
def bind(*, user_id=None) -> None
def user_hash(email: str) -> str | None
def spawn(target, *args, name=None, **kwargs) -> threading.Thread
    # ctx = contextvars.copy_context(); Thread(target=lambda: ctx.run(_guard, target, args, kwargs))
    # _guard wraps target in try/except -> logkit.get_logger("uvalu.job").exception(...)
```

`spawn()` replaces the raw `threading.Thread(...)` at all five current sites:

| Site | Worker |
|---|---|
| `screener.fetch_fundamentals_nowait` | fundamentals background fetch (`_run_fetch`) |
| `uvalu/store.py::_UniverseStore.get` | off-thread universe re-score (`_recompute`) |
| `uvalu/data.py::load_portfolio_risk` | risk-report compute (`_run`) |
| `portfolio.py::ensure_value_history_fresh` | value-history backfill (`_run`) |
| (any future) | — |

### 3.3 `filters.py`

- **`ContextFilter`** — injects `correlation_id`, `user_id`, `environment`,
  `build_version`, `schema_version`, `service` onto every record.
- **`RedactionFilter`** — the enforcement point for spec §5. Recursively scans
  `record.args` and `metadata`:
  - Key denylist (case-insensitive substring): `password`, `passwd`, `pwd`,
    `secret`, `token`, `jwt`, `authorization`, `bearer`, `auth_secret`,
    `encryption_key`, `api_key`, `apikey`, `cookie`, `session`, `crumb`,
    `password_hash`, `private_key`.
  - Value regexes: JWT (`eyJ[\w-]+\.[\w-]+\.[\w-]+`), Fernet token
    (`gAAAAA[\w-]{20,}`), bcrypt (`\$2[aby]\$\d\d\$`), 64-hex
    (`\b[0-9a-f]{64}\b` — AUTH_SECRET / ENCRYPTION_KEY / an un-hashed email
    hash source), bare email (`[\w.+-]+@[\w-]+\.\w+` → replaced with its
    `user_hash`), ≥13 consecutive digits (card / SSN heuristic → masked).
  - Replacement: `"[redacted]"`.
- **`SamplingFilter`** — per `(logger_name, level)` token-bucket or 1-in-N rate
  from `config.sampling` (spec §9). Bypassed for WARN and above.
- **`FingerprintFilter`** — on records with `exc_info`: fingerprint =
  `sha1(logger + exc_type + top_app_frame(file:func:lineno) + normalized_msg)`
  truncated to 6 hex. Keeps a process `dict[fp] -> {count, first, last}`;
  stamps `error_fingerprint` + `error_count`; lets the **first** occurrence and
  then every 10th (or once/5 min) through at full severity, the rest at DEBUG
  (spec §10 "aggregate as one issue rather than flooding"). `error_stats()`
  returns this dict for the future admin spike indicator (spec §12/§14) —
  without building the indicator.

### 3.4 `events.py` — typed helpers (keeps call sites one-liners)

```python
auth_event(event, *, user_id=None, outcome, reason=None, **meta)
authz_denied(*, user_id, action, required_role, got_role, resource=None)
data_mutation(*, actor, action, entity_type, entity_id, before=None, after=None, **meta)
config_change(*, actor, key, old, new, scope)         # scope = "shared" | f"user:{hash}"
with external_call("yfinance.download", params={...}) as call:   # times it, logs ok/failed
    ...
    call.note(status="rate_limited", retries=4)
with job("universe_rescore", trigger="cache_version_advance", items=n):  # start/ok/failed + duration
    ...
```

---

## 4. Config file — `logging.config.json` (committed default)

```json
{
  "level": "INFO",
  "environment": null,
  "console": { "enabled": true, "format": "auto", "color": "auto" },
  "file": {
    "enabled": true,
    "path": "logs/uvalu.log",
    "max_bytes": 5242880,
    "backup_count": 10,
    "format": "json"
  },
  "retention_days": 31,
  "async": true,
  "queue_capacity": 10000,
  "stack_traces": "auto",
  "health_check_logging": false,
  "hot_reload": true,
  "per_logger_levels": { "uvalu.render": "WARNING" },
  "sampling": {
    "uvalu.screener.fetch": { "level": "INFO", "rate": 0.05 },
    "uvalu.render":         { "level": "DEBUG", "rate": 0.0 }
  }
}
```

- Read at startup by `config.load()`.
- `environment: null` → fall back to `UVALU_ENV`, then `"development"`.
- `format: "auto"` → JSON unless `stderr.isatty()`; `color: "auto"` → on iff tty
  and `NO_COLOR` unset.
- `stack_traces: "auto"` → full in dev/staging, `error_type`+fingerprint only in
  prod.
- **Hot reload** (spec §10): a daemon thread polls the file mtime every ~5 s.
  Live-applied: `level`, `per_logger_levels`, `sampling`, `stack_traces`,
  `health_check_logging`. Requires restart (logged as a WARN on change):
  `file.path`, `async`, `queue_capacity`, `file.max_bytes/backup_count`. Total
  size cap is `max_bytes * (backup_count + 1)` ≈ 55 MB with the defaults.
- `.gitignore` gains `logs/`. `docs/configuration.md` gains a "Logging" section.
  `.env.example` gains `UVALU_ENV=development`.

---

## 5. What gets instrumented, and where

### 5.1 Authentication events (spec §4) — `auth.py`, `uvalu/authgate.py`

| Location | Event | Level |
|---|---|---|
| `auth.login()` success | `auth.login.ok` (user_id, role, was_invited) | INFO |
| `auth.login()` bad email / bad password | `auth.login.failed` (reason: `unknown_user` \| `bad_password`, user_id if known) — **never the password** | WARN |
| `auth.login()` suspended | `auth.login.failed` (reason: `suspended`) | WARN |
| `auth._store_broken()` true in `login`/`register` | `auth.store.unreadable` | CRITICAL |
| `auth.register()` / `invite_user()` | `mutation` (action `user.create` / `user.invite`, actor, entity_id = new user hash, role, bootstrap_admin flag) | INFO |
| `authgate.recover_session_from_cookie()` restores a session | `auth.session.restored` | INFO |
| `authgate.handle_logout()` | `auth.logout` | INFO |
| `authgate.auth_wall()` kills a live session (deleted / suspended / role changed under it) | `auth.session.revoked` (reason) | WARN |
| `auth.verify_token()` returns `(None, None)` on a non-empty token | `auth.token.invalid` (sampled) | DEBUG |

### 5.2 Authorization failures (spec §4)

| Location | Event |
|---|---|
| `settings.py` admin gate on "Screening & veto rules" | `authz.denied` (action `settings.write_shared`) |
| `uvalu/components.py` viewer gate (star button, add-ticker form) | `authz.denied` (action `watchlist.write`) |
| `uvalu/pages_/admin.py` non-admin reaching Admin | `authz.denied` (action `admin.view`) |
| `backup.get_backup_bytes()` `PermissionError` | `authz.denied` (action `backup.download`, resource = backup_id) |
| `auth.set_role/set_status/delete_user` "last active admin" blocks | `authz.denied` (action `admin.self_lockout_blocked`) |

All at WARN, `actor` = acting user hash.

### 5.3 Data mutations (spec §4) — actor + entity id on every one

| Module | Calls |
|---|---|
| `portfolio.py` | `add_position`, `remove_positions`, `update_positions`, `sell_position`, `add_closed_trade`, `add_dividend`, `update_div_hist`, `save_watchlist`, `save_manual_tickers`, `save_targets`, `save_cash`, `record_value_snapshot` |
| `settings.py` | `save_shared_settings` → `config_change` per changed key (old→new); `save_settings` → same, `scope=user:<hash>` |
| `auth.py` | `set_role`, `set_status`, `reset_password` (no password value), `delete_user` |
| `backup.py` | `create_backup`, `import_zip`, `restore_backup`, `export_env_key` (**CRITICAL** — master-secret export, spec §4 config-change + it is security-relevant) |

`entity_type`/`entity_id`: `ticker:<TICKER>`, `user:<hash>`, `backup:<id>`,
`setting:<key>`. `before`/`after` only where cheap (row counts, the scalar
value) — never a full DataFrame.

### 5.4 External calls — timing + outcome (spec §4, §10)

Wrap every yfinance batch in `external_call(...)`:

| Module | Call | `endpoint` |
|---|---|---|
| `prices.py::fetch_prices` | daily + 1-minute downloads, `fast_info` fallback | `yfinance.download.5d`, `yfinance.download.1m`, `yfinance.fast_info` |
| `marketdata.py::_download_closes` | `yf.download` batch (+ retry loop → `retries`) | `yfinance.download.history` |
| `marketdata.py::dividends` | `yf.Ticker().dividends` | `yfinance.dividends` |
| `screener.py::_fetch_one` / `_run_fetch` | per-ticker fundamentals (aggregate: 1 summary log per fetch run, per-ticker at sampled DEBUG) | `yfinance.quoteSummary` |
| `fetch_tickers.py` | the six stockanalysis.com scrapes | `stockanalysis.<exchange>` |
| `portfolio.py::backfill_value_history` | `yf.download` history + benchmarks | `yfinance.download.backfill` |

Records `params` (ticker count, period — **never full ticker lists at INFO**),
`latency_ms`, `status` (`ok` \| `empty` \| `rate_limited` \| `failed`),
`retries`. `status_code` where the upstream error carries one.

### 5.5 Background jobs — start / complete / failure (spec §4)

Wrap the four worker bodies in `job(...)`:

| Job name | Trigger | Completion metadata |
|---|---|---|
| `fundamentals_fetch` | stale tickers on a page load | `items`, `fetched`, `failed`, `cached`, `cancelled` |
| `universe_rescore` | `_cache_version()` advanced / exchange toggle | `exchanges`, `rows`, `duration_ms` |
| `risk_report` | Dashboard/Risk cache miss | `tickers`, `duration_ms`, `outcome` |
| `value_history_backfill` | stale `value_history.json` | `segments`, `rows_written` |

Failure path logs `job.failed` with `exc_info` (the `_run` wrappers currently
stash the exception and re-raise on the consuming rerun — keep that; just add
the log).

### 5.6 Errors & exceptions (spec §4, §10)

- Every current `except Exception: pass` / `except Exception: return None` in
  `portfolio._load`, `settings.load_*`, `crypto.*`, `prices.*`, `marketdata.*`,
  `uvalu.data.prefetch_portfolio_data`, `uvalu.store._recompute`,
  `fetch_tickers.*`: keep the swallow, add `get_logger(__name__).exception(...)`
  with a `reason`. Behaviour unchanged; the failure stops being invisible.
- `app.py`: wrap `_nav.run()` in `try/except` → `get_logger("uvalu.render")
  .exception("page render failed", extra={"event": "render", ...})`, re-raise so
  Streamlit still shows its error box.
- `sys.excepthook` + `threading.excepthook` from `init_logging()` catch the rest.
- Input parameters that triggered an error (spec §10): the `external_call` /
  `job` context managers already carry sanitized `params`; on exception they are
  attached to the error record automatically.

### 5.7 Render telemetry + noise control (spec §11)

- One `render` log at the end of `app.py` after `_nav.run()`: `page`
  (`_nav.url_path`), `user_id`, `duration_ms`, `outcome`.
- INFO when the `url_path` changed since the last run in this session (a real
  navigation); DEBUG otherwise (fragment tick / widget interaction), gated by
  `health_check_logging` and `sampling["uvalu.render"]`.
- `uvalu/ui.py::_auto_rerun` and `enter_dialog`: call `logkit.ensure_run()` so
  fragment/dialog reruns (which skip `app.py`) still carry a correlation id.

### 5.8 `print()` cleanup

The 23 `print()` calls (`screener.py`, `marketdata.py`, `fetch_tickers.py`,
`uvalu/data.py`, `run_app.py`) become `get_logger(...).debug/info(...)`.
`run_app.py`'s cert-generation prints stay as `print` (pre-app bootstrap, before
logging is configured).

---

## 6. Testing (`tests/`)

The repo runs pytest + Streamlit `AppTest` heavily and has a pyflakes
undefined-name gate (`tests/test_static_analysis.py` over `app.py` + `uvalu/**`
— the new package must pass it).

- **`tests/conftest.py`**: extend `isolated_data` (or add an autouse fixture) to
  call `logkit.init_logging(synchronous=True, log_dir=tmp_path)` — no listener
  thread, no real file, no queue — and reset `logkit` module state
  (`_initialised`, fingerprint dict, contextvars) between tests, same way it
  already resets `uvalu.store._STORE` and the risk-compute dicts.
- **`tests/test_logkit.py`** (new):
  - schema: every emitted record has the 8 top-level fields; `timestamp` is
    UTC-ms-`Z`; `WARNING`→`WARN`.
  - `RedactionFilter`: log a dict with a fake JWT, a 64-hex string, a bcrypt
    hash, a raw email → assert none appear in the formatted output; email is
    replaced by its hash.
  - context propagation: `begin_run()` → `spawn()` a worker that logs → the
    child record carries the parent `correlation_id` and `user_id`.
  - `SamplingFilter`: `rate: 0.0` drops all INFO for that logger, keeps WARN.
  - `FingerprintFilter`: same exception twice → stable `error_fingerprint`,
    `error_count` increments, 2nd is demoted.
  - `retention.sweep()`: files older than `retention_days` deleted, newer kept,
    active file untouched.
  - `init_logging()` idempotent under concurrent calls from two threads.
- **Extend existing suites** per phase: `test_auth.py`, `test_authgate.py`,
  `test_portfolio.py`, `test_pages_settings.py`, `test_backup.py`,
  `test_prices.py`, `test_marketdata.py`, `test_screener_cache.py`,
  `test_store.py` — assert the right `event` slug is emitted with the right
  `actor` / `entity_id`, using `caplog`.

---

## 7. Rollout phases

Each phase is independently shippable, test-green, and behaviour-preserving.

### Phase 0 — scaffolding, no behaviour change ✅ (branch `feat/logging-phase-0`)
`uvalu/logkit/` package (`__init__`, `config`, `setup`, `formatters`, `filters`,
`redaction`, `context`, `events`, `retention`); `logging.config.json`; `logs/`
in `.gitignore`; `UVALU_ENV` in `.env.example` + `docs/configuration.md`;
`pyproject.toml` version parsed via `tomllib` in `filters._read_pyproject_version`.
`app.py`: `logkit.init_logging()` + `begin_run()` right after `load_dotenv`,
`bind(email=_email)` after `set_user`, `try/except` around `_nav.run()`.
`conftest.py` autouse `_logkit_isolated` fixture (synchronous, file-less, state
reset). `docs/logging.md`. `tests/test_logkit.py` — 37 tests. Full suite
965 passed. **No call sites instrumented yet.**

### Phase 1 — auth & authz (highest audit value, smallest surface)
§5.1 + §5.2. Extend `test_auth.py`, `test_authgate.py`, `test_pages_admin.py`,
`test_pages_settings.py`.

### Phase 2 — data mutations & config changes
§5.3. Extend `test_portfolio.py`, `test_pages_settings.py`, `test_backup.py`.

### Phase 3 — external calls & background jobs
§5.4 + §5.5 + `spawn()` swap at the 5 sites + `print()` cleanup (§5.8). Extend
`test_prices.py`, `test_marketdata.py`, `test_screener_cache.py`,
`test_store.py`, `test_fetch_tickers.py`.

### Phase 4 — render telemetry, global hooks, fingerprinting
§5.6 + §5.7. `sys`/`threading` excepthooks. `FingerprintFilter` +
`error_stats()`. Tune `sampling["uvalu.render"]`.

### Phase 5 — hardening & docs
Queue load-test under the `_auto_rerun` 5 s cadence; tune `queue_capacity` +
drop policy. Retention disk-fill guard test. `docs/architecture.md` "Logging &
observability" section. `CHANGELOG.md` entry. Bump `pyproject.toml`. Lock the
prod stack-trace / health-check / deletion decisions in `docs/logging.md`.

---

## 8. Spec coverage checklist

| Spec § | Requirement | Covered by |
|---|---|---|
| §2 | 5 levels | schema `level`, `WARNING`→`WARN` map |
| §3 | required fields, structured JSON not free-text | §2 schema, `JsonFormatter`, `events.py` typed helpers |
| §4 | auth / authz / API / mutations / errors / jobs / config | §5.1–§5.6 |
| §5 | never log secrets / PII / raw bodies | `RedactionFilter` (§3.3) + a test |
| §6 | terminal + file, 1-month retention, config-file-driven | §3.1 handlers, `retention.py`, §4 config |
| §7 | terminal access = process access; encrypt when persisted beyond terminal | v1 = local file only, documented in `docs/logging.md`; encryption deferred with the persistence-beyond-terminal phase |
| §8 | ERROR/CRITICAL visually distinct in terminal | `ColorTextFormatter` (D4) |
| §9 | async / non-blocking, sampling | `QueueHandler`/`QueueListener`, `SamplingFilter` |
| §10 | correlation id, contextual logging, structured fields, stack traces dev-only, input params, timing, env+version, runtime level, fingerprinting | §3.2 context, `stack_traces:auto`, `external_call`/`job` params+timing, hot-reload, `FingerprintFilter` |
| §11 | rotation & disk limits, terminal-vs-file, config file, schema stability, health-check noise, UTC, account deletion | `RotatingFileHandler` + `retention.py`, D6, §4, §2 `schema_version`, D13, `time.gmtime`, D12 |
| §12 | admin portal | **out of scope** — only `error_stats()` hook + stable schema keep the door open |
| §13 | GDPR-aligned: no raw PII, reference user ids | D8 hash, `RedactionFilter` email→hash, D12 |
| §14 | monitoring is separate | `error_stats()` deliberately a plain dict, not a dashboard |
| §15 | single-tenant | no per-tenant scoping; `service` is a constant |

---

## 9. Risks & watch-outs

- **Streamlit re-exec / multiple ScriptRunner threads** hitting `init_logging()`
  at once — the singleton lock (§3.1) is load-bearing; test it.
- **`contextvars` across `@st.fragment` / `@st.dialog`** — fragment reruns don't
  re-enter `app.py`; `ensure_run()` in `_auto_rerun` and `enter_dialog` is the
  fix. Missing one = orphaned records with a stale/`null` correlation id.
- **Queue backpressure** under the 5 s auto-rerun fragments across several open
  tabs — bounded queue + drop-INFO-on-full + a once/minute "dropped N" counter.
- **`RotatingFileHandler` on Windows** (dev is Win11) — a rotation while another
  thread holds the file open can raise `PermissionError`. `QueueListener` funnels
  all writes through **one** thread, which sidesteps it; still worth a test on
  Windows.
- **pyflakes gate** — `uvalu/logkit/**` is scanned by
  `tests/test_static_analysis.py`; keep it undefined-name clean.
- **Test log noise / file creation** — the `synchronous=True` fixture path must
  be the default in the test env, or CI fills `logs/` and slows down.
- **Double-logging** — root Python logger vs the `uvalu` logger. Set
  `logging.getLogger("uvalu").propagate = False` and attach handlers only there;
  leave third-party (`yfinance`, `urllib3`, `streamlit`) at WARNING on the root
  with no uvalu handlers.
