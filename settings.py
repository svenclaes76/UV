"""User-scoped app settings — one encrypted file per user in data/settings/."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from crypto import read_encrypted, write_encrypted  # noqa: E402

_DATA_DIR = Path(__file__).parent / "data" / "settings"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

ALL_EXCHANGES: list[str] = ["brussels", "amsterdam", "paris", "milan", "frankfurt", "swiss"]

EXCHANGE_LABELS: dict[str, str] = {
    "brussels":  "Euronext Brussels",
    "amsterdam": "Euronext Amsterdam",
    "paris":     "Euronext Paris",
    "milan":     "Borsa Italiana",
    "frankfurt": "Deutsche Börse",
    "swiss":     "SIX Swiss Exchange",
}

_SHARED_FILE   = _DATA_DIR / "shared.json"
_SHARED_DEFAULTS: dict = {
    "enabled_exchanges": ALL_EXCHANGES,
    # Veto/screening thresholds — read by screener.py's _score_and_clean via
    # get_veto_thresholds() below. Defaults match the constants that were
    # hardcoded before Phase 3.6 (screener.py SCORE_STRONG_BUY=70, the
    # debtToEquity>500 hard veto, and _dividend_sustainability_flag's
    # payout>0.90 check).
    "max_debt_equity": 500.0,   # % — hard veto above this D/E
    "max_payout":      90.0,    # % — dividend flagged "At Risk" above this payout ratio
    "min_mos":         0.0,     # % — minimum margin of safety required for a BUY signal
    "buy_threshold":   70.0,    # composite score required for a BUY signal
    "screen_style":    "balanced",  # composite sub-score weighting — see _SCORE_STYLES
    "benchmark_stoxx": False,   # default state of the Dashboard's Euro Stoxx 50 overlay checkbox
    "us_listed_enabled": False,  # not yet wired — no US ticker universe exists
}

# Composite-score sub-weight vectors per screening style, each
# (W_MOS, W_RISK, W_QUALITY, W_MOMENTUM, W_DIVIDEND) summing to 1.0. "balanced"
# reproduces screener.py's own W_* constants exactly; the others just re-lens the
# same five signals so the user can pick which one leads. Read by screener.py's
# compute_scores via get_score_weights() below.
_SCORE_STYLES: dict[str, tuple] = {
    "balanced": (0.30, 0.18, 0.22, 0.15, 0.15),
    "value":    (0.38, 0.18, 0.26, 0.06, 0.12),   # MoS + quality lead
    "growth":   (0.16, 0.14, 0.28, 0.34, 0.08),   # momentum + quality lead, thin MoS
    "income":   (0.20, 0.20, 0.16, 0.06, 0.38),   # dividend-led
}

_USER_DEFAULTS: dict = {
    "density":  "comfortable",  # "comfortable" | "compact" — table row density
    "refresh_interval_s": 60,   # portfolio price auto-refresh cadence
    "alert_buy_signal":      False,
    "alert_avoid_signal":    False,
    "alert_dividend_ex_date": False,
    "alert_price_target":    False,
}


def _settings_file(email: str) -> Path:
    slug = hashlib.sha256(email.strip().lower().encode()).hexdigest()[:16]
    return _DATA_DIR / f"{slug}.json"


# ── Shared settings (admin-controlled, apply to all users) ───────────────────

def load_shared_settings() -> dict:
    if not _SHARED_FILE.exists():
        return dict(_SHARED_DEFAULTS)
    try:
        data = json.loads(read_encrypted(_SHARED_FILE))
        for k, v in _SHARED_DEFAULTS.items():
            data.setdefault(k, v)
        return data
    except Exception:
        return dict(_SHARED_DEFAULTS)


def save_shared_settings(s: dict) -> None:
    write_encrypted(_SHARED_FILE, json.dumps(s, indent=2))


def get_veto_thresholds() -> tuple[float, float, float, float]:
    """(max_debt_equity, max_payout, min_mos, buy_threshold) for screener.py's
    scoring engine — a tuple so it's hashable as an @st.cache_data key."""
    s = load_shared_settings()
    return (
        float(s.get("max_debt_equity", 500.0)),
        float(s.get("max_payout", 90.0)) / 100,
        float(s.get("min_mos", 0.0)) / 100,
        float(s.get("buy_threshold", 70.0)),
    )


def get_score_weights() -> tuple:
    """(W_MOS, W_RISK, W_QUALITY, W_MOMENTUM, W_DIVIDEND) for the active
    screening style — a hashable tuple so it joins the @st.cache_data keys next
    to get_veto_thresholds(). Falls back to "balanced" for an unknown style."""
    style = load_shared_settings().get("screen_style", "balanced")
    return _SCORE_STYLES.get(style, _SCORE_STYLES["balanced"])


# ── Per-user settings ────────────────────────────────────────────────────────

def load_settings(email: str = "") -> dict:
    path = _settings_file(email) if email else _DATA_DIR / "default.json"
    if not path.exists():
        return dict(_USER_DEFAULTS)
    try:
        data = json.loads(read_encrypted(path))
        for k, v in _USER_DEFAULTS.items():
            data.setdefault(k, v)
        return data
    except Exception:
        return dict(_USER_DEFAULTS)


def save_settings(s: dict, email: str = "") -> None:
    path = _settings_file(email) if email else _DATA_DIR / "default.json"
    write_encrypted(path, json.dumps(s, indent=2))
