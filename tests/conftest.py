"""
Shared fixtures for testing uvalu/pages_/*.py render() functions via
Streamlit's AppTest harness.

Every page module reads/writes through portfolio.py/settings.py/auth.py/
backup.py's module-level path constants and calls out to yfinance for live
data — ``isolated_data`` redirects all persistence into tmp_path (see
tests/test_auth.py etc. for why both the defining module's AND any
by-value-importing module's copy of a path constant need patching) and
nothing here ever touches the developer's real .cache/data directories or
makes a real network call.
"""
import pandas as pd
import pytest

import auth
import backup
import portfolio
import risk
import settings

TEST_EMAIL = "test@example.com"

# portfolio.py's "current user" is stored in threading.local() (see
# portfolio.py's _local), scoped to the thread executing a script run — not
# a shared global, so it isn't visible across threads. AppTest.run() (and
# real Streamlit reruns) execute the script on a fresh thread each time, so
# a page test that needs portfolio.py's implicit "current user" (no email
# passed explicitly) must call set_user() from WITHIN the script text itself,
# exactly like app.py does for the real app — the isolated_data fixture's own
# set_user() call runs on the pytest thread and is not visible to the
# AppTest-executed script. Prepend this to any script_src that calls page
# code touching portfolio.py without an explicit email.
#
# The user_email session-state line matches what app.py's auth gate leaves
# behind: uvalu.ui.enter_dialog() (top of every @st.dialog body) re-derives
# the active user from st.session_state via current_user(), because a fragment
# rerun — a dialog's Save button — never re-runs app.py's set_user().
USER_SETUP_SRC = (
    f'import portfolio\nportfolio.set_user({TEST_EMAIL!r})\n'
    f'import streamlit as st\nst.session_state["user_email"] = {TEST_EMAIL!r}\n'
)


@pytest.fixture
def isolated_data(tmp_path, monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEY", "unit-test-key-123")
    monkeypatch.setattr(portfolio, "_BASE_DIR", tmp_path / "portfolio")
    monkeypatch.setattr(settings, "_DATA_DIR", tmp_path / "settings_data")
    monkeypatch.setattr(settings, "_SHARED_FILE", tmp_path / "settings_data" / "shared.json")
    monkeypatch.setattr(backup, "_SHARED_FILE", tmp_path / "settings_data" / "shared.json")
    monkeypatch.setattr(backup, "_ENV_FILE", tmp_path / "fake.env")
    monkeypatch.setattr(backup, "_BACKUPS_DIR", tmp_path / "backups")
    monkeypatch.setattr(backup, "_BACKUPS_MANIFEST", tmp_path / "backups" / "manifest.json")
    monkeypatch.setattr(auth, "USERS_FILE", tmp_path / ".cache" / "users.json")
    # Keep the Fama-French disk cache off the developer's real .cache/factors.
    monkeypatch.setattr(risk, "_FACTORS_DIR", tmp_path / "factors")
    monkeypatch.setattr(risk, "_ff_cache", {})
    # Drop the process-global scored-universe store (uvalu.store, WP-5) so no
    # stale entry — or a background worker another test kicked — leaks in. Page
    # tests monkeypatch _load_all_screener_data wholesale and never reach it,
    # but this keeps that guarantee cheap and explicit.
    from uvalu import store as _uv_store
    _uv_store._STORE.clear()
    # Sets the pytest thread's own portfolio "current user" -- covers direct,
    # non-AppTest calls into portfolio.py made straight from a test body. An
    # AppTest-executed script runs on its own separate thread and needs its
    # own USER_SETUP_SRC prepended instead; see the comment on that constant.
    portfolio.set_user(TEST_EMAIL)
    yield
    portfolio.set_user("")


# ── Fake scored-screener-row builder ──────────────────────────────────────
# Mirrors the real column set screener.run_screener_from_df() produces
# (see screener.py / tests/test_algorithms.py) — enough fields for every
# pages_/*.py module's row.get(...) calls to find real values instead of
# silently rendering "—" placeholders everywhere.

_SCREENER_COLUMNS = dict(
    Ticker="AAA.BR", Name="Alpha Corp", sector="Technology", country="Belgium",
    Exchange="Brussels", Price=100.0, Decision="Strong Buy", veto=False,
    **{"Value Score": 78.0, "MoS %": 18.5, "margin_of_safety": 0.185},
    fair_value=122.0, graham_number=118.0, pe_fair_value=125.0, epv=120.0,
    ddm=115.0, ddm_multistage=124.0, targetMeanPrice=130.0,
    trailingPE=14.2, dividendYield=0.032, dividendRate=3.2,
    exDividendDate="15-01-2025", trailingEps=6.5, bookValue=45.0,
    returnOnEquity=0.18, debtToEquity=80.0, fcfYield=0.05,
    operatingMargins=0.20, profitMargins=0.15, payoutRatio=0.40,
    freeCashflow=5_000_000.0,
    **{"Div Flag": "OK"}, dividendCoverage=2.5,
    **{"Sub MoS": 70.0, "Sub Risk": 65.0, "Sub Quality": 80.0,
       "Sub Momentum": 60.0, "Sub Dividend": 75.0},
    beta=1.05,
    # Multi-year statement histories (screener._statement_history). None here =
    # "column present, no history" — the same shape an older cache or a failed
    # statement fetch produces; consumers already guard with isinstance(x, list).
    revenueHistory=None, ebitHistory=None, netIncomeHistory=None,
    cfoHistory=None, retainedEarningsHistory=None, totalAssetsHistory=None,
)


def make_scored_row(**overrides) -> dict:
    row = dict(_SCREENER_COLUMNS)
    row.update(overrides)
    return row


def make_scored_df(rows: list[dict] | None = None) -> pd.DataFrame:
    rows = rows if rows is not None else [make_scored_row()]
    return pd.DataFrame(rows)


@pytest.fixture
def scored_df():
    return make_scored_df()


def make_portfolio_scored_df(tickers=("AAA.BR",), names=("Alpha Corp",)) -> pd.DataFrame:
    """Stand-in for uvalu.data._load_portfolio_screener_data() — a scored row
    per held/sold ticker, same column set as make_scored_df().
    """
    rows = [make_scored_row(Ticker=t, Name=n) for t, n in zip(tickers, names)]
    return pd.DataFrame(rows if rows else [make_scored_row()])


def fake_portfolio_scored(override=None):
    """Build a stand-in for uvalu.data._load_portfolio_scored(held, sold=None) —
    the WP-3 portfolio-fast-path loader that Dashboard/Portfolio/Risk call
    instead of _load_all_screener_data(). Returns one scored row per held (+
    sold) ticker, deduped held-first, mirroring the real helper. Pass
    `override` (a DataFrame) to return a fixed frame regardless of input.

    Page test `_run` helpers patch with
    `monkeypatch.setattr(<page>, "_load_portfolio_scored", fake_portfolio_scored())`.
    """
    def _fn(held, sold=None):
        if override is not None:
            return override
        seen: dict[str, str] = {}
        for df in (held, sold):
            if df is None or getattr(df, "empty", True) or "ticker" not in df.columns:
                continue
            names = df["name"] if "name" in df.columns else df["ticker"]
            for t, n in zip(df["ticker"], names):
                t = str(t).strip()
                if t and t not in seen:
                    seen[t] = str(n)
        return make_portfolio_scored_df(tuple(seen), tuple(seen.values()))
    return _fn


def make_screener_data_tuple(exchange_df: pd.DataFrame | None = None,
                             extra_df: pd.DataFrame | None = None) -> tuple:
    """Build the 7-tuple _load_all_screener_data() normally returns:
    one DataFrame per settings.ALL_EXCHANGES entry, then the "extra"
    (portfolio-only) tickers DataFrame. Puts all fake data in the
    "brussels" slot (index 0) since every fake ticker uses a ".BR" suffix."""
    empty = pd.DataFrame(columns=["Ticker"])
    exchange_df = exchange_df if exchange_df is not None else make_scored_df()
    extra_df = extra_df if extra_df is not None else empty
    return (exchange_df, empty, empty, empty, empty, empty, extra_df)


def fake_cached_fn(return_value):
    """Build a stand-in for an @st.cache_data-wrapped function: several
    pages call `.clear()` on _load_all_screener_data (a real cache-clear),
    so a bare lambda would raise AttributeError when that fires."""
    def _fn(*_a, **_k):
        return return_value
    _fn.clear = lambda: None
    return _fn


def make_portfolio_df(rows: list[dict] | None = None) -> pd.DataFrame:
    default_row = dict(
        ticker="AAA.BR", name="Alpha Corp", google_ticker="EBR:AAA",
        shares=10, purchase_value=1000.0, purchase_price=100.0,
        target_price=130.0, dividends=20.0, date_in="2023-01-01", date_out="",
    )
    rows = rows if rows is not None else [default_row]
    return pd.DataFrame(rows)
