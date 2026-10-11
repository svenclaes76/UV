"""Data-schema versioning for Uvalu's on-disk data (VM-08, VM-09, VM-10).

Uvalu has no database: its "schema" is the layout of the encrypted JSON files
under ``data/`` and ``.cache/users.json``. The schema version is recorded in
``data/schema_version.json`` and only changes through numbered migrations in
this package (``m0001_baseline.py``, ``m0002_<name>.py``, …).

A migration module defines::

    NUMBER = 2                      # must match the file name, contiguous from 1
    DESCRIPTION = "What it changes, in one line"
    def up(ctx: MigrationContext) -> None: ...
    def down(ctx: MigrationContext) -> None: ...   # optional; without it the step is irreversible

``up`` must be idempotent: restoring an older backup re-runs the steps after
the backup's schema over the whole data directory (see ``backup.import_zip``).

Rules: every upgrade/downgrade first writes a snapshot ZIP of the data
(``data/migration-snapshots/``), holds a lock file, and records the schema
number after **each** step, so a crash mid-chain leaves an accurate number.
"""
from __future__ import annotations

import calendar
import importlib
import io
import json
import os
import pkgutil
import re
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from uvalu import buildinfo, logkit

ROOT = buildinfo.ROOT
DATA_DIR = ROOT / "data"
CACHE_DIR = ROOT / ".cache"
STATE_NAME = "schema_version.json"
SNAPSHOT_DIRNAME = "migration-snapshots"
LOCK_NAME = ".migrate.lock"
KEEP_SNAPSHOTS = 10
# Snapshots hold every user's data, so a deleted account must leave them too:
# the privacy notice promises removal from backups within 30 days.
SNAPSHOT_MAX_AGE_DAYS = 30
_PRUNE_EVERY_S = 3600
_LOCK_STALE_S = 15 * 60
_NAME_RE = re.compile(r"^m(\d{4})_\w+$")

# Files in .cache/ that are user data, not re-fetchable cache (included in snapshots).
CACHE_DATA_FILES = ("users.json",)
# Sub-directories of data/ a snapshot leaves out (backups of their own, or our own snapshots).
_SNAPSHOT_SKIP_DIRS = {SNAPSHOT_DIRNAME, "backups"}

_log = logkit.get_logger("uvalu.migrations")


class MigrationError(Exception):
    """A migration could not be applied; the message says what to do."""


class SchemaMismatch(MigrationError):
    def __init__(self, on_disk: "int | None", expected: int, message: str):
        super().__init__(message)
        self.on_disk = on_disk
        self.expected = expected


# ── context passed to migrations ─────────────────────────────────────────────

@dataclass(frozen=True)
class MigrationContext:
    data_dir: Path
    cache_dir: Path

    @property
    def state_file(self) -> Path:
        return self.data_dir / STATE_NAME

    @property
    def snapshot_dir(self) -> Path:
        return self.data_dir / SNAPSHOT_DIRNAME

    @property
    def users_file(self) -> Path:
        return self.cache_dir / "users.json"

    def user_dirs(self) -> "list[Path]":
        """Per-user portfolio folders, ``data/portfolio/<hash>/``."""
        base = self.data_dir / "portfolio"
        return sorted(p for p in base.iterdir() if p.is_dir()) if base.is_dir() else []

    def settings_files(self) -> "list[Path]":
        base = self.data_dir / "settings"
        return sorted(base.glob("*.json")) if base.is_dir() else []

    def read_json(self, path: Path):
        """Decrypt + parse one of Uvalu's encrypted JSON files."""
        from crypto import read_encrypted
        return json.loads(read_encrypted(path))

    def write_json(self, path: Path, value) -> None:
        from crypto import write_encrypted
        write_encrypted(path, json.dumps(value, indent=2))

    def has_data(self) -> bool:
        """True when this is an existing installation, not a fresh checkout."""
        if self.users_file.exists() or self.user_dirs() or self.settings_files():
            return True
        return any((self.data_dir / n).exists() for n in ("compliance", "portfolio.json"))


def default_context() -> MigrationContext:
    # read at call time so tests can monkeypatch DATA_DIR / CACHE_DIR
    return MigrationContext(DATA_DIR, CACHE_DIR)


# ── discovery ────────────────────────────────────────────────────────────────

def discover() -> "list[ModuleType]":
    from uvalu import migrations as pkg
    mods = []
    for info in pkgutil.iter_modules(pkg.__path__):
        m = _NAME_RE.match(info.name)
        if not m:
            continue
        mod = importlib.import_module(f"{pkg.__name__}.{info.name}")
        if getattr(mod, "NUMBER", None) != int(m.group(1)):
            raise MigrationError(f"{info.name}: NUMBER must be {int(m.group(1))}")
        if not callable(getattr(mod, "up", None)) or not getattr(mod, "DESCRIPTION", ""):
            raise MigrationError(f"{info.name}: needs DESCRIPTION and up(ctx)")
        mods.append(mod)
    mods.sort(key=lambda x: x.NUMBER)
    numbers = [x.NUMBER for x in mods]
    if numbers != list(range(1, len(numbers) + 1)):
        raise MigrationError(f"migration numbers must run 1..N without gaps, got {numbers}")
    return mods


def expected_version() -> int:
    """The schema version this code expects: the highest migration number."""
    return discover()[-1].NUMBER


def is_reversible(mod: ModuleType) -> bool:
    return callable(getattr(mod, "down", None))


# ── state file ───────────────────────────────────────────────────────────────

def read_state(ctx: "MigrationContext | None" = None) -> "dict | None":
    """The recorded state, or None when no schema version was ever recorded.
    Raises MigrationError when the file exists but cannot be read."""
    ctx = ctx or default_context()
    try:
        raw = ctx.state_file.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise MigrationError(f"{ctx.state_file} is unreadable: {exc}") from exc
    try:
        state = json.loads(raw)
        if not isinstance(state, dict) or not isinstance(state.get("schema_version"), int):
            raise ValueError("no integer schema_version")
    except ValueError as exc:
        raise MigrationError(f"{ctx.state_file} is corrupt: {exc}") from exc
    state.setdefault("history", [])
    return state


def current_version(ctx: "MigrationContext | None" = None) -> "int | None":
    state = read_state(ctx)
    return state["schema_version"] if state else None


def _write_state(ctx: MigrationContext, state: dict) -> None:
    ctx.data_dir.mkdir(parents=True, exist_ok=True)
    tmp = ctx.state_file.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, ctx.state_file)


def _history_entry(number: int, direction: str, snapshot: "str | None") -> dict:
    info = buildinfo.current()
    return {"number": number, "direction": direction, "at": buildinfo.utc_now_iso(),
            "app_version": info.display_version, "commit": info.commit, "snapshot": snapshot}


def _record(ctx: MigrationContext, state: dict, version: int, entry: dict) -> dict:
    state = {**state, "schema_version": version, "history": [*state.get("history", []), entry]}
    _write_state(ctx, state)
    return state


# ── lock ─────────────────────────────────────────────────────────────────────

class _Lock:
    def __init__(self, ctx: MigrationContext):
        self.path = ctx.data_dir / LOCK_NAME

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if time.time() - self.path.stat().st_mtime > _LOCK_STALE_S:
                self.path.unlink()
        except OSError:
            pass
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise MigrationError(f"another migration is running ({self.path} exists); "
                                 "wait for it, or delete the file if no migration is running")
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return self

    def __exit__(self, *exc):
        try:
            self.path.unlink()
        except OSError:
            pass


# ── snapshots ────────────────────────────────────────────────────────────────

def snapshot(ctx: MigrationContext, label: str) -> str:
    """ZIP the data (already encrypted at rest; no .env) before a migration.
    Returns the snapshot id (its file name without .zip)."""
    ctx.snapshot_dir.mkdir(parents=True, exist_ok=True)
    sid = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + f"-{label}"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if ctx.data_dir.is_dir():
            for p in sorted(ctx.data_dir.rglob("*")):
                rel = p.relative_to(ctx.data_dir)
                if not p.is_file() or rel.parts[0] in _SNAPSHOT_SKIP_DIRS or p.name == LOCK_NAME:
                    continue
                zf.write(p, arcname=f"data/{rel.as_posix()}")
        for name in CACHE_DATA_FILES:
            p = ctx.cache_dir / name
            if p.is_file():
                zf.write(p, arcname=f"cache/{name}")
    (ctx.snapshot_dir / f"{sid}.zip").write_bytes(buf.getvalue())
    _prune_snapshots(ctx)
    return sid


def _snapshot_time(path: Path) -> float:
    """When a snapshot was taken: from its id (20261011T144538Z-…), else the file time."""
    try:
        return calendar.timegm(time.strptime(path.name[:16], "%Y%m%dT%H%M%SZ"))
    except ValueError:
        return path.stat().st_mtime


def _prune_snapshots(ctx: MigrationContext) -> None:
    snaps = sorted(ctx.snapshot_dir.glob("*.zip"))
    for old in snaps[:-KEEP_SNAPSHOTS]:
        try:
            old.unlink()
        except OSError:
            pass
    prune_expired_snapshots(ctx)


_last_age_prune = 0.0


def prune_expired_snapshots(ctx: "MigrationContext | None" = None, *, force: bool = True) -> int:
    """Delete snapshots older than SNAPSHOT_MAX_AGE_DAYS. Returns how many.
    ``force=False`` runs at most once an hour (the start-up check calls it on
    every rerun)."""
    global _last_age_prune
    now = time.time()
    if not force and now - _last_age_prune < _PRUNE_EVERY_S:
        return 0
    _last_age_prune = now
    ctx = ctx or default_context()
    cutoff = now - SNAPSHOT_MAX_AGE_DAYS * 86400
    removed = 0
    for snap in ctx.snapshot_dir.glob("*.zip") if ctx.snapshot_dir.is_dir() else ():
        try:
            if _snapshot_time(snap) < cutoff:
                snap.unlink()
                removed += 1
        except OSError:
            pass
    if removed:
        _log.info("expired migration snapshots removed", extra={
            "event": "migration.snapshots_pruned", "removed": removed})
    return removed


def list_snapshots(ctx: "MigrationContext | None" = None) -> "list[str]":
    ctx = ctx or default_context()
    return sorted((p.stem for p in ctx.snapshot_dir.glob("*.zip")), reverse=True)


def restore_snapshot(snapshot_id: str, ctx: "MigrationContext | None" = None) -> int:
    """Put a snapshot's files back (stop the app first). Returns the file count.
    Files created after the snapshot are left in place; schema_version.json comes
    back from the snapshot, so the recorded version matches the restored data."""
    ctx = ctx or default_context()
    path = ctx.snapshot_dir / f"{snapshot_id}.zip"
    if not path.is_file():
        raise MigrationError(f"no snapshot {snapshot_id!r} in {ctx.snapshot_dir}")
    n = 0
    with _Lock(ctx), zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if name.startswith("data/"):
                dest = ctx.data_dir / name[len("data/"):]
            elif name.startswith("cache/") and name[len("cache/"):] in CACHE_DATA_FILES:
                dest = ctx.cache_dir / name[len("cache/"):]
            else:
                continue
            if ".." in Path(name).parts:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(name))
            n += 1
    reset_cache()
    _log.warning("data snapshot restored", extra={"event": "migration.snapshot_restored",
                                                   "snapshot": snapshot_id, "files": n})
    return n


# ── upgrade / downgrade ──────────────────────────────────────────────────────

def _baseline(ctx: MigrationContext, expected: int) -> dict:
    """First run with migrations: existing data is at schema 1 (the layout the
    baseline describes); a fresh install starts at the newest schema."""
    if ctx.has_data():
        version, direction = 1, "baseline"
    else:
        version, direction = expected, "fresh-install"
    state = _record(ctx, {"history": []}, version, _history_entry(version, direction, None))
    _log.info("data schema version recorded", extra={"event": "migration.baseline",
                                                     "schema_version": version, "kind": direction})
    return state


def upgrade(ctx: "MigrationContext | None" = None, *, target: "int | None" = None,
            from_version: "int | None" = None) -> "list[int]":
    """Apply pending migrations up to ``target`` (default: newest). Returns the
    numbers applied. ``from_version`` re-runs the steps after it even when the
    recorded version is already newer (restoring an older backup)."""
    ctx = ctx or default_context()
    mods = discover()
    expected = mods[-1].NUMBER
    target = expected if target is None else target
    if not 1 <= target <= expected:
        raise MigrationError(f"target {target} is outside 1..{expected}")
    with _Lock(ctx):
        state = read_state(ctx) or _baseline(ctx, expected)
        cur = state["schema_version"]
        if cur > expected:
            raise SchemaMismatch(cur, expected, mismatch_message(cur, expected))
        start = cur if from_version is None else min(cur, from_version)
        if cur > target and from_version is None:
            raise MigrationError(f"data is at schema {cur}, above {target} — use downgrade")
        pending = [m for m in mods if start < m.NUMBER <= target]
        if not pending:
            return []
        snap = snapshot(ctx, f"before-up-{start}-to-{target}")
        for m in pending:
            t0 = time.monotonic()
            try:
                m.up(ctx)
            except Exception as exc:
                _log.critical("data migration failed", exc_info=True,
                              extra={"event": "migration.failed", "number": m.NUMBER,
                                     "direction": "up", "snapshot": snap})
                raise MigrationError(
                    f"migration {m.NUMBER} ({m.DESCRIPTION}) failed: {exc}. Data is at schema "
                    f"{read_state(ctx)['schema_version']}; snapshot {snap} holds the data from "
                    f"before this run (python -m uvalu.migrations restore-snapshot {snap})") from exc
            state = _record(ctx, state, max(m.NUMBER, state["schema_version"]),
                            _history_entry(m.NUMBER, "up", snap))
            _log.info("data migration applied", extra={
                "event": "migration.applied", "number": m.NUMBER, "direction": "up",
                "description": m.DESCRIPTION, "duration_ms": int((time.monotonic() - t0) * 1000)})
        reset_cache()
        return [m.NUMBER for m in pending]


def downgrade(to: int, ctx: "MigrationContext | None" = None) -> "list[int]":
    """Undo migrations down to schema ``to``. Run it with the code that has the
    newer migrations — only that code knows their ``down()`` steps."""
    ctx = ctx or default_context()
    mods = {m.NUMBER: m for m in discover()}
    with _Lock(ctx):
        state = read_state(ctx)
        if state is None:
            raise MigrationError("no schema version recorded — nothing to downgrade")
        cur = state["schema_version"]
        if cur > max(mods):
            raise MigrationError(f"data is at schema {cur} but this code only knows up to "
                                 f"{max(mods)} — run the downgrade with the newer code")
        if not 1 <= to < cur:
            raise MigrationError(f"target {to} must be between 1 and {cur - 1}")
        path = [mods[n] for n in range(cur, to, -1)]
        blocked = [m for m in path if not is_reversible(m)]
        if blocked:
            snaps = [h.get("snapshot") for h in state["history"]
                     if h.get("direction") == "up" and h.get("number") == blocked[0].NUMBER]
            hint = f" Restore snapshot {snaps[-1]} instead." if snaps and snaps[-1] else ""
            raise MigrationError("cannot downgrade: irreversible migration(s) "
                                 + ", ".join(f"{m.NUMBER} ({m.DESCRIPTION})" for m in blocked) + "." + hint)
        snap = snapshot(ctx, f"before-down-{cur}-to-{to}")
        for m in path:
            m.down(ctx)
            state = _record(ctx, state, m.NUMBER - 1, _history_entry(m.NUMBER, "down", snap))
            _log.warning("data migration reverted", extra={
                "event": "migration.applied", "number": m.NUMBER, "direction": "down",
                "description": m.DESCRIPTION})
        reset_cache()
        return [m.NUMBER for m in path]


# ── start-up check (VM-09) ───────────────────────────────────────────────────

def mismatch_message(on_disk: "int | None", expected: int) -> str:
    info = buildinfo.current()
    who = f"this version ({info.display_version}, {info.commit}) expects {expected}"
    if on_disk is None:
        return f"Data schema version is unreadable; {who}. Fix or restore data/{STATE_NAME}."
    if on_disk < expected:
        return (f"Data schema is {on_disk}, {who}. Run \"python -m uvalu.migrations upgrade\" "
                "(run_app.py does this automatically) and start again.")
    return (f"Data schema is {on_disk}, {who}. The data was migrated by a newer version: run "
            f"\"python -m uvalu.migrations downgrade --to {expected}\" with the newer code, or "
            f"restore the snapshot taken before that migration, then start this version again.")


_compatible: "tuple[MigrationContext, int] | None" = None


def ensure_compatible(ctx: "MigrationContext | None" = None) -> int:
    """Refuse to run on data whose schema differs from what this code expects.
    No recorded version yet → record the baseline (changes no data) and go on.
    Returns the schema version; raises SchemaMismatch otherwise. A success is
    remembered for the process (app.py calls this on every rerun); a mismatch
    is re-checked every time, so fixing the data needs no restart."""
    global _compatible
    ctx = ctx or default_context()
    prune_expired_snapshots(ctx, force=False)
    if _compatible is not None and _compatible[0] == ctx:
        return _compatible[1]
    expected = expected_version()
    try:
        state = read_state(ctx)
    except MigrationError as exc:
        _log.critical("data schema version unreadable", extra={
            "event": "startup.schema_mismatch", "expected": expected, "error": str(exc)})
        raise SchemaMismatch(None, expected, mismatch_message(None, expected)) from exc
    if state is None:
        with _Lock(ctx):
            state = read_state(ctx) or _baseline(ctx, expected)
    on_disk = state["schema_version"]
    if on_disk != expected:
        msg = mismatch_message(on_disk, expected)
        _log.critical("data schema mismatch, refusing to start", extra={
            "event": "startup.schema_mismatch", "on_disk": on_disk, "expected": expected,
            "instruction": msg})
        raise SchemaMismatch(on_disk, expected, msg)
    _compatible = (ctx, on_disk)
    return on_disk


def reset_cache() -> None:
    """Forget a remembered successful check (tests; after a migration in-process)."""
    global _compatible
    _compatible = None
