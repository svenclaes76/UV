"""
Backup and restore for user data.

Export options:
  - Encrypted ZIP  : per-user data dir + shared/user settings (all already
                     Fernet-encrypted at rest individually) — no .env, so a
                     routine backup carries no secret that could decrypt
                     other users' data or forge a session
  - .env key export: this deployment's AUTH_SECRET/ENCRYPTION_KEY, a
                     separate, deliberate action (export_env_key()) — only
                     needed once, to migrate onto a brand-new machine; never
                     bundled into the routine backup history
  - Excel workbook : human-readable export of positions, dividends, sold history

Import:
  - Encrypted ZIP  : extracts files back into the current user's data dir.
                     A .env entry in an older backup (pre this design) is
                     skipped, not restored — see import_zip().
"""

from __future__ import annotations

import io
import json
import secrets
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from crypto import read_encrypted, write_encrypted
from portfolio import user_data_dir, load_portfolio, load_sold, load_div_hist, load_watchlist
from settings import _settings_file, _SHARED_FILE

_ENV_FILE        = Path(__file__).parent / ".env"
_ZIP_DATA_PREFIX = "data/"
_ZIP_SETTINGS_KEY        = "data/settings.json"
_ZIP_SHARED_SETTINGS_KEY = "data/shared_settings.json"

_PORTFOLIO_FILENAMES = ("portfolio.json", "sold.json", "dividends_history.json", "watchlist.json")

# ── Backup history (Admin portal) ─────────────────────────────────────────────
# A real, growing history of on-demand backups — every entry is a genuine
# export_zip() snapshot saved to disk with a timestamp, listed and restorable
# from the Admin portal. There is no scheduler anywhere in this app, so unlike
# the design mockup's "Scheduled vs Manual" distinction, every entry here is
# honestly typed "Manual" — see the Phase 4 plan notes for why.
_BACKUPS_DIR     = Path(__file__).parent / "data" / "backups"
_BACKUPS_MANIFEST = _BACKUPS_DIR / "manifest.json"


# ── Export ────────────────────────────────────────────────────────────────────

def export_zip(email: str = "") -> bytes:
    """
    Bundle the current user's data files + settings into an in-memory ZIP.
    Returns the raw ZIP bytes for download.

    Deliberately does NOT include .env (AUTH_SECRET/ENCRYPTION_KEY) — every
    file bundled here is already individually Fernet-encrypted at rest, so a
    backup without .env is still safe to create, list, and hand around; it's
    useless without the key, which is the point of encryption at rest.
    .env used to be bundled here so a backup was "fully restorable on any
    machine," but that meant every backup in the Admin portal's shared,
    freely-downloadable history also carried the one secret that decrypts
    every user's data and can forge a session as anyone. See
    export_env_key() for the separate, deliberate way to move that secret
    between machines now.
    """
    buf = io.BytesIO()
    udir = user_data_dir(email)
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in _PORTFOLIO_FILENAMES:
            path = udir / fname
            if path.exists():
                zf.write(path, arcname=f"{_ZIP_DATA_PREFIX}{fname}")
        settings_path = _settings_file(email) if email else None
        if settings_path and settings_path.exists():
            zf.write(settings_path, arcname=_ZIP_SETTINGS_KEY)
        if _SHARED_FILE.exists():
            zf.write(_SHARED_FILE, arcname=_ZIP_SHARED_SETTINGS_KEY)
    return buf.getvalue()


def export_env_key() -> bytes | None:
    """
    Raw bytes of this deployment's .env file (AUTH_SECRET, ENCRYPTION_KEY) —
    its master secrets. Returns None if no .env exists.

    Deliberately separate from export_zip()/create_backup(): anyone holding
    this can decrypt every user's data and sign in as anyone, on any
    account, so it shouldn't be something that accumulates in the same
    shared, any-admin-downloadable backup history as routine data snapshots.
    Only needed once, when standing up a new deployment that must read an
    existing one's encrypted data — the caller should treat the result as
    sensitive as the secrets it contains and not persist it anywhere.
    """
    if not _ENV_FILE.exists():
        return None
    return _ENV_FILE.read_bytes()


def export_excel() -> bytes:
    """
    Export all user data as a human-readable Excel workbook.
    Returns raw bytes suitable for st.download_button.
    """
    pf   = load_portfolio()
    sold = load_sold()
    div  = load_div_hist()
    wl   = load_watchlist()

    has_data = (
        (pf   is not None and not pf.empty) or
        (sold  is not None and not sold.empty) or
        (div   is not None and not div.empty) or
        bool(wl)
    )
    if not has_data:
        raise ValueError("No portfolio data found to export.")

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        if pf is not None and not pf.empty:
            pf.to_excel(writer, sheet_name="Positions", index=False)
        if sold is not None and not sold.empty:
            sold.to_excel(writer, sheet_name="Sold", index=False)
        if div is not None and not div.empty:
            div.to_excel(writer, sheet_name="Dividends", index=False)
        if wl:
            pd.DataFrame(sorted(wl), columns=["Ticker"]).to_excel(
                writer, sheet_name="Watchlist", index=False
            )
    return buf.getvalue()


# ── Import ────────────────────────────────────────────────────────────────────

def import_zip(zip_bytes: bytes, email: str = "") -> list[str]:
    """
    Restore user data from a previously exported ZIP into the current user's dirs.
    Returns a list of restored file names.
    Raises ValueError for invalid/unrecognised ZIPs.
    """
    restored: list[str] = []
    udir = user_data_dir(email)
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
            has_data = any(n.startswith(_ZIP_DATA_PREFIX) for n in names)
            has_env  = ".env" in names
            if not has_data and not has_env:
                raise ValueError("ZIP does not contain recognisable backup files.")

            for name in names:
                if name == _ZIP_SHARED_SETTINGS_KEY:
                    _SHARED_FILE.parent.mkdir(parents=True, exist_ok=True)
                    _SHARED_FILE.write_bytes(zf.read(name))
                    restored.append("shared settings")
                elif name == _ZIP_SETTINGS_KEY:
                    dest = _settings_file(email) if email else None
                    if dest:
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_bytes(zf.read(name))
                        restored.append("settings")
                elif name.startswith(_ZIP_DATA_PREFIX):
                    fname = name[len(_ZIP_DATA_PREFIX):]
                    if fname in _PORTFOLIO_FILENAMES:
                        (udir / fname).write_bytes(zf.read(name))
                        restored.append(fname)
                elif name == ".env":
                    # Older backups (from before export_zip() stopped
                    # bundling .env) may still have one -- skip it rather
                    # than overwrite this server's live encryption/signing
                    # keys as a side effect of restoring a data snapshot.
                    # export_env_key() is the deliberate, separate way to
                    # move keys between machines now.
                    continue
    except zipfile.BadZipFile:
        raise ValueError("File is not a valid ZIP archive.")
    return restored


def backup_filename(ext: str) -> str:
    """Generate a timestamped filename for the backup download."""
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    return f"uv_backup_{ts}.{ext}"


# ── Backup history (Admin portal) ─────────────────────────────────────────────

def _load_backup_manifest() -> list[dict]:
    if not _BACKUPS_MANIFEST.exists():
        return []
    try:
        return json.loads(read_encrypted(_BACKUPS_MANIFEST))
    except Exception:
        return []


def _save_backup_manifest(entries: list[dict]) -> None:
    _BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    write_encrypted(_BACKUPS_MANIFEST, json.dumps(entries, indent=2))


def list_backups() -> list[dict]:
    """All backup entries, newest first."""
    return sorted(_load_backup_manifest(), key=lambda e: e.get("created_at", ""), reverse=True)


def create_backup(email: str) -> dict:
    """
    Snapshot the given user's data via export_zip() and save it to disk as a
    new backup-history entry. Returns the new entry.
    """
    _BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    zip_bytes = export_zip(email)
    backup_id = secrets.token_hex(8)
    filename  = f"{backup_id}.zip"
    (_BACKUPS_DIR / filename).write_bytes(zip_bytes)

    entry = {
        "id":         backup_id,
        "email":      email,
        "type":       "Manual",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "size_bytes": len(zip_bytes),
        "filename":   filename,
    }
    entries = _load_backup_manifest()
    entries.append(entry)
    _save_backup_manifest(entries)
    return entry


def get_backup_bytes(backup_id: str, requester_email: str | None = None) -> bytes:
    """
    Raw ZIP bytes for a backup-history entry, for st.download_button.

    requester_email — if given, raises PermissionError unless it matches the
    entry's own creator. Scopes direct *downloads* to "your own backups
    only" (backups can contain another user's real portfolio holdings, and
    every entry is otherwise visible/downloadable by any Admin regardless of
    who created it). restore_backup() below deliberately does NOT pass this
    — restoring someone else's snapshot back into their own account is a
    legitimate cross-admin recovery action, distinct from casually
    downloading and inspecting their personal data.
    """
    entries = {e["id"]: e for e in _load_backup_manifest()}
    entry = entries.get(backup_id)
    if not entry:
        raise ValueError("Backup not found.")
    if requester_email is not None and entry.get("email") != requester_email:
        raise PermissionError("You can only download your own backups.")
    path = _BACKUPS_DIR / entry["filename"]
    if not path.exists():
        raise ValueError("Backup file is missing from disk.")
    return path.read_bytes()


def restore_backup(backup_id: str, email: str) -> list[str]:
    """Restore a backup-history entry into the given user's data dirs."""
    return import_zip(get_backup_bytes(backup_id), email)
