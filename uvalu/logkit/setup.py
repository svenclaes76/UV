"""``init_logging()`` — build the logging pipeline once per process.

Async (default): ``uvalu`` logger -> ``QueueHandler`` (all four filters) ->
bounded ``queue.Queue`` -> ``QueueListener`` on a daemon thread -> console
``StreamHandler`` + ``RotatingFileHandler`` (formatters only). Non-blocking on
the caller (spec §9).

Synchronous (tests, or ``async: false``): one ``StreamHandler`` on the ``uvalu``
logger carrying the filters + a plain formatter; no queue, no file, no threads.
"""
from __future__ import annotations

import atexit
import logging
import logging.handlers
import os
import queue
import sys
import threading
import time

from uvalu.logkit import config as _config
from uvalu.logkit import filters as _filters
from uvalu.logkit.formatters import ColorTextFormatter, JsonFormatter

_LOGGER_ROOT = "uvalu"
_LEVEL_ALIAS = {"WARN": "WARNING", "FATAL": "CRITICAL"}
_LIVE_RELOAD_POLL_S = 5.0
_DAILY_SWEEP_S = 86400

_init_lock = threading.Lock()
_initialised = False
_synchronous = False
_listener: "logging.handlers.QueueListener | None" = None
_reload_stop: "threading.Event | None" = None


# ── helpers ────────────────────────────────────────────────────────────────

def _level(name) -> int:
    n = str(name).upper()
    return getattr(logging, _LEVEL_ALIAS.get(n, n), logging.INFO)


def _include_stack(cfg: dict, env: str) -> bool:
    mode = str(cfg.get("stack_traces") or "auto").lower()
    if mode == "always":
        return True
    if mode == "never":
        return False
    return env != "production"


def _console_formatter(con: dict, stack_fn):
    fmt = str(con.get("format") or "auto").lower()
    want_json = fmt == "json" or (fmt == "auto" and not _stderr_is_tty())
    if want_json:
        return JsonFormatter(include_stack=stack_fn)
    color_mode = str(con.get("color") or "auto").lower()
    color = color_mode == "always" or (
        color_mode == "auto" and _stderr_is_tty() and not os.environ.get("NO_COLOR")
    )
    return ColorTextFormatter(color=color, include_stack=stack_fn)


def _stderr_is_tty() -> bool:
    try:
        return bool(sys.stderr.isatty())
    except Exception:
        return False


def _build_sinks(cfg: dict, log_dir, stack_fn) -> list:
    sinks: list = []
    con = cfg.get("console", {})
    if con.get("enabled", True):
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(_console_formatter(con, stack_fn))
        sinks.append(sh)
    fl = cfg.get("file", {})
    if fl.get("enabled", True):
        from uvalu.logkit.retention import resolve_log_path
        path = resolve_log_path(cfg, log_dir)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            fh = logging.handlers.RotatingFileHandler(
                path,
                maxBytes=int(fl.get("max_bytes", 5 * 1024 * 1024)),
                backupCount=int(fl.get("backup_count", 10)),
                encoding="utf-8",
                delay=True,
            )
            fh.setFormatter(
                JsonFormatter(include_stack=stack_fn)
                if str(fl.get("format", "json")).lower() == "json"
                else ColorTextFormatter(color=False, include_stack=stack_fn)
            )
            sinks.append(fh)
        except OSError:
            # A read-only or missing log dir must not stop the app from
            # logging to the console.
            logging.getLogger("uvalu.logkit").warning(
                "file log handler disabled — %s not writable", path,
                extra={"event": "config.change", "key": "file.enabled"},
            )
    return sinks or [logging.NullHandler()]


def _apply_per_logger_levels(cfg: dict) -> None:
    for name, lvl in (cfg.get("per_logger_levels") or {}).items():
        logging.getLogger(name).setLevel(_level(lvl))


# ── public API ─────────────────────────────────────────────────────────────

def init_logging(*, synchronous: "bool | None" = None,
                 config_path=None, log_dir=None) -> None:
    """Idempotent. Safe to call on every Streamlit rerun and from multiple
    session threads at once. ``synchronous`` defaults to True under pytest."""
    global _initialised, _synchronous, _listener

    with _init_lock:
        if _initialised:
            return

        cfg = _config.load(config_path)
        if synchronous is None:
            synchronous = bool(os.environ.get("PYTEST_CURRENT_TEST"))
        _synchronous = synchronous

        env = _config.resolve_environment(cfg)
        stack_fn = lambda: _include_stack(_config.current(),  # noqa: E731
                                          _config.resolve_environment())

        root = logging.getLogger(_LOGGER_ROOT)
        for h in list(root.handlers):
            root.removeHandler(h)
        root.setLevel(logging.DEBUG if synchronous else _level(cfg.get("level", "INFO")))

        if synchronous:
            # Leave propagate on so pytest's caplog (a root handler) sees
            # uvalu.* records; add one filtered handler for tests that assert
            # on formatted output.
            root.propagate = True
            h = logging.StreamHandler(sys.stderr)
            h.setFormatter(ColorTextFormatter(color=False, include_stack=stack_fn))
            for f in _filters.all_filters():
                h.addFilter(f)
            root.addHandler(h)
            _initialised = True
            return

        root.propagate = False
        sinks = _build_sinks(cfg, log_dir, stack_fn)

        if not cfg.get("async", True):
            entry = sinks[0]
            for extra_sink in sinks[1:]:
                # rare: async off but >1 sink — chain them behind one handler
                entry = _Tee(entry, extra_sink)
            for f in _filters.all_filters():
                entry.addFilter(f)
            root.addHandler(entry)
        else:
            q: queue.Queue = queue.Queue(maxsize=int(cfg.get("queue_capacity", 10000)))
            qh = _RecordQueueHandler(q)
            for f in _filters.all_filters():
                qh.addFilter(f)
            root.addHandler(qh)
            _listener = logging.handlers.QueueListener(q, *sinks, respect_handler_level=True)
            _listener.start()
            atexit.register(_shutdown)

        _apply_per_logger_levels(cfg)
        logging.getLogger().setLevel(logging.WARNING)  # third-party noise floor
        _initialised = True

    # outside the lock: one-shot retention sweep + the hot-reload / daily-sweep thread
    _safe_sweep(cfg, log_dir)
    if cfg.get("hot_reload", True):
        _start_background_thread(config_path, log_dir)


def error_stats() -> dict:
    return _filters.error_stats()


# ── hot reload + daily sweep ───────────────────────────────────────────────

def _start_background_thread(config_path, log_dir) -> None:
    global _reload_stop
    if _reload_stop is not None:
        return
    _reload_stop = threading.Event()
    last_mtime = _config.file_mtime(config_path)
    last_sweep = [0.0]

    def _loop() -> None:
        nonlocal last_mtime
        while not _reload_stop.wait(_LIVE_RELOAD_POLL_S):
            m = _config.file_mtime(config_path)
            if m and m != last_mtime:
                last_mtime = m
                try:
                    cfg = _config.load(config_path)
                    _apply_live(cfg)
                    logging.getLogger("uvalu.logkit").info(
                        "logging config reloaded",
                        extra={"event": "config.change", "key": "logging.config.json"},
                    )
                except Exception:
                    logging.getLogger("uvalu.logkit").exception(
                        "logging config reload failed",
                        extra={"event": "job.failed", "job": "config_reload"},
                    )
            now = time.time()
            if now - last_sweep[0] >= _DAILY_SWEEP_S:
                last_sweep[0] = now
                _safe_sweep(_config.current(), log_dir)

    threading.Thread(target=_loop, name="logkit-hot-reload", daemon=True).start()


def _apply_live(cfg: dict) -> None:
    """Re-apply only the keys that are safe to change without a restart:
    level, per-logger levels. sampling / stack_traces / health_check_logging are
    read live from ``_config.current()`` by the filters and formatters."""
    logging.getLogger(_LOGGER_ROOT).setLevel(_level(cfg.get("level", "INFO")))
    _apply_per_logger_levels(cfg)


def _safe_sweep(cfg, log_dir) -> None:
    try:
        from uvalu.logkit import retention
        retention.sweep(cfg, log_dir)
    except Exception:
        logging.getLogger("uvalu.logkit").exception(
            "retention sweep failed",
            extra={"event": "job.failed", "job": "retention_sweep"},
        )


def _shutdown() -> None:
    global _listener
    if _listener is not None:
        try:
            _listener.stop()
        except Exception:
            pass
        _listener = None


# ── test support ───────────────────────────────────────────────────────────

def _reset_for_tests() -> None:
    """Tear down handlers + process-global state so the next ``init_logging``
    starts clean. Called by the autouse conftest fixture."""
    global _initialised, _reload_stop
    with _init_lock:
        _shutdown()
        if _reload_stop is not None:
            _reload_stop.set()
            _reload_stop = None
        root = logging.getLogger(_LOGGER_ROOT)
        for h in list(root.handlers):
            root.removeHandler(h)
        root.propagate = True
        _initialised = False
    _filters.reset()
    from uvalu.logkit import context
    context.clear()


class _RecordQueueHandler(logging.handlers.QueueHandler):
    """QueueHandler that enqueues the live ``LogRecord`` unchanged.

    The stock ``prepare()`` renders the record to text (merging the traceback
    into ``msg`` and dropping ``exc_info``) for cross-process pickling — which
    would put the stack in the ``message`` field and, worse, bypass the stack
    scrubbing the sink-side formatter does. This is a same-process thread
    handoff, so no rendering is needed; the filters have already run on the
    calling thread before ``emit``.
    """

    def prepare(self, record: logging.LogRecord) -> logging.LogRecord:
        return record


class _Tee(logging.Handler):
    """Fan one record out to two handlers — only used when ``async: false`` is
    combined with both console and file sinks."""

    def __init__(self, a: logging.Handler, b: logging.Handler) -> None:
        super().__init__()
        self._a, self._b = a, b

    def emit(self, record: logging.LogRecord) -> None:
        self._a.handle(record)
        self._b.handle(record)
