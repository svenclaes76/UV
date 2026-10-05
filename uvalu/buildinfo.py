"""Build metadata: which version of Uvalu is running (VM-02, VM-04..VM-06).

The version itself is set in exactly one place, ``pyproject.toml``. Everything
else about a build — commit, build time, environment, release or dev — is
written to ``build_info.json`` by ``tools/stamp_build.py`` when the app is
deployed/started (``run_app.py`` runs it), never by hand. The file is
git-ignored.

When the stamp is missing (tests, ``streamlit run app.py`` directly) the same
fields are computed in-process from git once per process (``source="runtime"``).

Every place that shows or logs a version reads it from :func:`current` — the UI
never hard-codes a version (VD-10).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
import tomllib
from dataclasses import asdict, dataclass, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
STAMP_FILE = ROOT / "build_info.json"
STATIC_DIR = ROOT / "static"
VERSION_JSON = STATIC_DIR / "version.json"

# CalVer YYYY.MM.N (VM-01) — two-digit month; N is the release's sequence number
# within that month, from 1. Example: 2026.10.2 = the second release of October 2026.
CALVER_RE = re.compile(r"^(?P<year>\d{4})\.(?P<month>0[1-9]|1[0-2])\.(?P<n>[1-9]\d*)$")

ENVIRONMENTS = ("development", "test", "production")
_ENV_ALIASES = {
    "dev": "development", "develop": "development", "development": "development", "local": "development",
    "test": "test", "testing": "test", "staging": "test", "acceptance": "test",
    "prod": "production", "production": "production", "live": "production",
}
_ENV_LABELS = {"development": "DEV", "test": "TEST", "production": "PROD"}


@dataclass(frozen=True)
class BuildInfo:
    version: str           # "2026.10.1" — from pyproject.toml
    display_version: str   # "2026.10.1", or "2026.10.1-dev+a1b2c3d" / "...+a1b2c3d.dirty"
    commit: str            # short hash, "unknown" without git
    commit_full: str
    built_at: str          # ISO-8601 UTC, seconds, "Z"
    environment: str       # "development" | "test" | "production" | anything else = non-production
    is_release: bool
    dirty: bool
    source: str            # "stamp" | "runtime"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def environment_label(self) -> str:
        return environment_label(self.environment)

    @property
    def tag(self) -> str:
        return f"v{self.version}"

    def to_dict(self) -> dict:
        return asdict(self)


# ── helpers ──────────────────────────────────────────────────────────────────

def is_calver(version: str) -> bool:
    return bool(CALVER_RE.match(version or ""))


def normalize_environment(value: "str | None") -> str:
    v = str(value or "development").strip().lower()
    return _ENV_ALIASES.get(v, v or "development")


def environment_label(env: str) -> str:
    return _ENV_LABELS.get(env, (env or "?").upper()[:4])


def read_pyproject_version(path: Path = PYPROJECT) -> str:
    try:
        with path.open("rb") as fh:
            return str(tomllib.load(fh)["project"]["version"])
    except Exception:
        return "0.0.0"


def display_version(version: str, *, is_release: bool, commit: str, dirty: bool) -> str:
    """``2026.10.1`` for a release; ``2026.10.1-dev+a1b2c3d[.dirty]`` otherwise (VM-06).
    A dev build is named after the last release it is built on (plan D2)."""
    if is_release:
        return version
    local = commit if commit and commit != "unknown" else "unknown"
    return f"{version}-dev+{local}{'.dirty' if dirty else ''}"


def utc_now_iso(ts: "float | None" = None) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts if ts is not None else time.time()))


def _git(root: Path, *args: str) -> "str | None":
    try:
        out = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                             timeout=5, check=True)
        return out.stdout.strip()
    except Exception:
        return None


def _runtime_environment() -> str:
    try:
        from uvalu.logkit import config as _config
        return normalize_environment(_config.resolve_environment())
    except Exception:
        return normalize_environment(os.environ.get("UVALU_ENV"))


# ── compute / load / write ───────────────────────────────────────────────────

def compute(root: Path = ROOT, *, environment: "str | None" = None,
            now: "float | None" = None) -> BuildInfo:
    """Derive build metadata from pyproject + git. Never raises."""
    version = read_pyproject_version(root / "pyproject.toml")
    full = _git(root, "rev-parse", "HEAD") or ""
    commit = full[:7] if full else "unknown"
    status = _git(root, "status", "--porcelain", "--untracked-files=no")
    dirty = bool(status) if status is not None else False
    # A release is HEAD == the *annotated* tag v<version>, with a clean tree (plan D3).
    ref = _git(root, "for-each-ref", f"refs/tags/v{version}",
               "--format=%(objecttype) %(*objectname)") or ""
    kind, _, peeled = ref.partition(" ")
    is_release = bool(full) and kind == "tag" and peeled == full and not dirty
    env = normalize_environment(environment) if environment else _runtime_environment()
    return BuildInfo(
        version=version,
        display_version=display_version(version, is_release=is_release, commit=commit, dirty=dirty),
        commit=commit, commit_full=full or "unknown", built_at=utc_now_iso(now),
        environment=env, is_release=is_release, dirty=dirty, source="runtime",
    )


def load(path: "Path | None" = None) -> "BuildInfo | None":
    try:
        raw = json.loads((path or STAMP_FILE).read_text(encoding="utf-8"))
        fields = {f: raw[f] for f in BuildInfo.__dataclass_fields__ if f != "source"}
        return BuildInfo(**fields, source="stamp")
    except Exception:
        return None


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def write(info: BuildInfo, path: "Path | None" = None) -> None:
    data = info.to_dict()
    data.pop("source", None)
    _atomic_write(path or STAMP_FILE, json.dumps(data, indent=2) + "\n")


def public_dict(info: BuildInfo, *, schema_version: "int | None" = None) -> dict:
    """The machine-readable shape served at /app/static/version.json (VD-07)."""
    return {
        "service": "uvalu",
        "version": info.version,
        "display_version": info.display_version,
        "commit": info.commit,
        "built_at": info.built_at,
        "environment": info.environment,
        "is_release": info.is_release,
        "schema_version": schema_version,
    }


def write_public(info: BuildInfo, *, schema_version: "int | None" = None,
                 path: "Path | None" = None) -> None:
    _atomic_write(path or VERSION_JSON, json.dumps(public_dict(info, schema_version=schema_version), indent=2) + "\n")


# ── process-wide accessor ────────────────────────────────────────────────────

_lock = threading.Lock()
_current: "BuildInfo | None" = None


def current() -> BuildInfo:
    """The running build, read once per process: the stamp if present, else computed.
    The environment always reflects the running process (``UVALU_ENV``)."""
    global _current
    with _lock:
        if _current is None:
            info = load()
            if info is None:
                info = compute()
            else:
                info = replace(info, environment=_runtime_environment())
            _current = info
        return _current


def build_id(info: "BuildInfo | None" = None) -> str:
    info = info or current()
    return f"{info.display_version}@{info.built_at}"


def reset() -> None:
    """Forget the cached build (tests)."""
    global _current
    with _lock:
        _current = None
