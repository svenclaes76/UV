"""
Backup and restore for user data.

Export options:
  - Encrypted ZIP  : per-user data dir + .env bundled; fully restorable on any machine
  - Excel workbook : human-readable export of positions, dividends, sold history

Import:
  - Encrypted ZIP  : extracts files back into the current user's data dir + .env
"""

from __future__ import annotations

import io
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd

from portfolio import user_data_dir, load_portfolio, load_sold, load_div_hist, load_watchlist
from settings import _settings_file, _SHARED_FILE

_ENV_FILE        = Path(__file__).parent / ".env"
_ZIP_DATA_PREFIX = "data/"
_ZIP_SETTINGS_KEY        = "data/settings.json"
_ZIP_SHARED_SETTINGS_KEY = "data/shared_settings.json"

_PORTFOLIO_FILENAMES = ("portfolio.json", "sold.json", "dividends_history.json", "watchlist.json")


# ── Export ────────────────────────────────────────────────────────────────────

def export_zip(email: str = "") -> bytes:
    """
    Bundle the current user's data files + settings + .env into an in-memory ZIP.
    Returns the raw ZIP bytes for download.
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
        if _ENV_FILE.exists():
            zf.write(_ENV_FILE, arcname=".env")
    return buf.getvalue()


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
                    _ENV_FILE.write_bytes(zf.read(name))
                    restored.append(".env")
    except zipfile.BadZipFile:
        raise ValueError("File is not a valid ZIP archive.")
    return restored


def backup_filename(ext: str) -> str:
    """Generate a timestamped filename for the backup download."""
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    return f"uv_backup_{ts}.{ext}"
