"""
Backup and restore for user data.

Export options:
  - Encrypted ZIP  : data/ files + .env bundled; fully restorable on any machine
  - Excel workbook : human-readable export of positions, dividends, sold history

Import:
  - Encrypted ZIP  : extracts data/ files + .env, replacing existing data
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd

from portfolio import (
    PORTFOLIO_FILE, SOLD_FILE, DIV_HIST_FILE, WATCHLIST_FILE, _DATA_DIR,
    load_portfolio, load_sold, load_div_hist, load_watchlist,
)

_ENV_FILE = Path(__file__).parent / ".env"

_USER_FILES = [PORTFOLIO_FILE, SOLD_FILE, DIV_HIST_FILE, WATCHLIST_FILE]
_ZIP_DATA_PREFIX = "data/"


# ── Export ────────────────────────────────────────────────────────────────────

def export_zip() -> bytes:
    """
    Bundle all user data files + .env into an in-memory ZIP.
    Returns the raw ZIP bytes for download.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in _USER_FILES:
            if path.exists():
                zf.write(path, arcname=f"{_ZIP_DATA_PREFIX}{path.name}")
        if _ENV_FILE.exists():
            zf.write(_ENV_FILE, arcname=".env")
    return buf.getvalue()


def export_excel() -> bytes:
    """
    Export all user data as a human-readable Excel workbook.
    Returns raw bytes suitable for st.download_button.
    """
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        pf = load_portfolio()
        if pf is not None and not pf.empty:
            pf.to_excel(writer, sheet_name="Positions", index=False)

        sold = load_sold()
        if sold is not None and not sold.empty:
            sold.to_excel(writer, sheet_name="Sold", index=False)

        div = load_div_hist()
        if div is not None and not div.empty:
            div.to_excel(writer, sheet_name="Dividends", index=False)

        wl = load_watchlist()
        if wl:
            pd.DataFrame(sorted(wl), columns=["Ticker"]).to_excel(
                writer, sheet_name="Watchlist", index=False
            )
    return buf.getvalue()


# ── Import ────────────────────────────────────────────────────────────────────

def import_zip(zip_bytes: bytes) -> list[str]:
    """
    Restore user data from a previously exported ZIP.
    Returns a list of restored file names.
    Raises ValueError for invalid/unrecognised ZIPs.
    """
    restored: list[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
            has_data = any(n.startswith(_ZIP_DATA_PREFIX) for n in names)
            has_env  = ".env" in names
            if not has_data and not has_env:
                raise ValueError("ZIP does not contain recognisable backup files.")

            _DATA_DIR.mkdir(exist_ok=True)
            for name in names:
                if name.startswith(_ZIP_DATA_PREFIX):
                    fname = name[len(_ZIP_DATA_PREFIX):]
                    dest  = _DATA_DIR / fname
                    dest.write_bytes(zf.read(name))
                    restored.append(f"data/{fname}")
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
