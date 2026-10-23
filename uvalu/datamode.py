"""Data modes: where the app's data comes from and what the app may do with it.

docs/demo-mode-plan.md §1. One setting, ``UVALU_DATA_MODE``, picks a profile:

- ``personal`` (default): today's app. Yahoo Finance and the stockanalysis.com
  lists, fetched live; sign-in on; edits saved. For the founder only (L2).
- ``demo``: the Streamlit Community Cloud demo. Reads the committed EODHD/ECB
  snapshot in ``demo-data/`` and never calls a data API; no sign-in; edits live
  in the browser session only (DM-D4); fixed 10-ticker universe.
- ``commercial``: licensed data for paying users. Defined so the setting is
  reserved, but not built yet, so selecting it fails at start-up.

On Streamlit Community Cloud a top-level secret is also exposed as an
environment variable, so ``UVALU_DATA_MODE = "demo"`` in the app's secrets is
enough. An unknown value fails loudly instead of falling back to personal:
a demo that silently ran on Yahoo would be the one outcome to avoid.

Pages and modules ask ``current()``; nothing else reads the variable.
No Streamlit import; unit-tested in tests/test_datamode.py.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from uvalu.demo import universe as _demo_universe

ENV_VAR = "UVALU_DATA_MODE"
DEMO_DATA_DIR = Path(__file__).resolve().parent.parent / "demo-data"


@dataclass(frozen=True)
class DataMode:
    key: str
    live_fetch: bool                 # the app itself calls market-data APIs
    sign_in: bool                    # the auth wall is on
    persistent_writes: bool          # user edits are saved to disk
    data_dir: "Path | None"          # snapshot read instead of fetching
    universe: "tuple[str, ...] | None"   # fixed tickers; None = the exchanges in Settings
    hidden_pages: frozenset[str]     # st.Page url_paths left out of the navigation
    banner: bool                     # the "Demo data" banner (spec F-01)
    built: bool = True


PERSONAL = DataMode(
    key="personal", live_fetch=True, sign_in=True, persistent_writes=True,
    data_dir=None, universe=None, hidden_pages=frozenset(), banner=False,
)

# DM-D6 (decided 18 Oct 2026): Admin out; Watchlist stays, kept per browser
# session like the sample portfolio; Settings stays for language and region.
DEMO = DataMode(
    key="demo", live_fetch=False, sign_in=False, persistent_writes=False,
    data_dir=DEMO_DATA_DIR, universe=_demo_universe.TICKERS,
    hidden_pages=frozenset({"admin"}), banner=True,
)

COMMERCIAL = DataMode(
    key="commercial", live_fetch=True, sign_in=True, persistent_writes=True,
    data_dir=None, universe=None, hidden_pages=frozenset(), banner=False,
    built=False,
)

MODES: dict[str, DataMode] = {m.key: m for m in (PERSONAL, DEMO, COMMERCIAL)}


def current() -> DataMode:
    """The active profile, read fresh from the environment on every call (cheap,
    and lets tests switch modes with monkeypatch). Raises ValueError for an
    unknown value and RuntimeError for a mode that isn't built yet."""
    raw = os.environ.get(ENV_VAR, "").strip().lower() or PERSONAL.key
    mode = MODES.get(raw)
    if mode is None:
        raise ValueError(f"{ENV_VAR}={raw!r} is not a data mode; "
                         f"expected one of: {', '.join(MODES)}")
    if not mode.built:
        raise RuntimeError(f"{ENV_VAR}={raw!r}: the {raw} mode isn't built yet")
    return mode


def is_demo() -> bool:
    return current().key == DEMO.key


def demo_log_dir() -> Path:
    """Where demo mode writes its log file: the system temp folder, never the
    repo's logs/ (open item L35). Gone when a Community Cloud container
    restarts; the host keeps its own console log under its policy."""
    import tempfile
    return Path(tempfile.gettempdir()) / "uvalu-demo"
