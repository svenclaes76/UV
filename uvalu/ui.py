"""Reusable rendering helpers: static charts, donut, treemap color, and the
click-to-select dataframe / timed auto-refresh widgets.

Theme-dependent helpers resolve the active palette via ``theme_colors()`` so
callers don't pass colors around.
"""
import time

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from portfolio import set_user
from settings import load_settings
from uvalu.market_hours import is_market_hours
from uvalu.runtime import current_user, theme_colors

_CHART_CONFIG = {"staticPlot": True, "displayModeBar": False}

# Brand-aligned categorical palette for donut / pie charts.
# Stays in the teal-blue-sage family; red/orange reserved for danger signals only.
_DONUT_PALETTE = [
    "#1DD6A4",  # Mint Pulse      — primary slot
    "#1A8C6E",  # Signal Teal
    "#5B8FA8",  # Steel blue
    "#2BA5A5",  # Mid teal
    "#3D7AB5",  # Slate blue
    "#8BA888",  # Sage green
    "#4A6B8A",  # Navy blue
    "#6B9E8A",  # Muted teal-green
    "#2D6B7A",  # Deep teal
    "#A0B8B0",  # Silver teal
    "#7A9EBF",  # Powder blue
    "#5E8C7A",  # Forest teal
]


def _row_select_table(df, key: str, **dataframe_kwargs) -> "int | None":
    """st.dataframe with single-row click selection.

    Returns the selected positional row index (into `df`) once per selection,
    or None. The widget key embeds a nonce that is bumped when a selection is
    consumed, so closing the details dialog does not immediately re-open it.
    """
    _nonce_key = f"_nonce_{key}"
    _nonce = st.session_state.get(_nonce_key, 0)
    _event = st.dataframe(
        df,
        on_select="rerun",
        selection_mode="single-row",
        key=f"{key}_{_nonce}",
        **dataframe_kwargs,
    )
    _rows = _event.selection.rows
    if _rows:
        st.session_state[_nonce_key] = _nonce + 1
        return _rows[0]
    return None


# A modal dialog stays open only while its dialog-decorated function keeps
# being called on every script run; a full-app rerun that doesn't re-invoke it
# closes it (see st.dialog docs). _auto_rerun's timer fires exactly such a
# rerun, so without this guard it silently tears down whatever @st.dialog the
# user has open — losing half-entered form data (the "Add position isn't
# working" bug). mark_dialog_open() timestamps an open modal; the timer skips
# its rerun while that stamp is fresh. The stamp is refreshed on every
# dialog-fragment rerun (i.e. every interaction inside the modal), so an
# actively-used dialog never goes stale; it only lapses after this many
# seconds of no interaction, and any genuine full run clears it outright.
_DIALOG_GRACE_S = 300


def mark_dialog_open() -> None:
    """Call at the top of every ``@st.dialog`` body so a timed price refresh
    can't yank the modal out from under the user mid-edit."""
    st.session_state["_uv_dialog_open_ts"] = time.time()


def enter_dialog() -> None:
    """Call as the very first line of every ``@st.dialog`` body.

    Does two things a dialog can't do without:

    1. ``mark_dialog_open()`` — keep ``price_autorefresh``'s timer from firing a
       full-app rerun that would close the modal mid-edit.
    2. Re-point the data layer at the signed-in user. A dialog body runs as a
       fragment; a fragment rerun (the Save/Delete buttons) does **not**
       re-execute ``app.py``, so the ``set_user()`` there is skipped — and on a
       fresh ScriptRunner thread that only ever ran this fragment,
       ``portfolio.py``'s thread-local active user is unset, so CRUD writes land
       in the anonymous ``default/`` bucket instead of the user's directory
       (their new position then never shows up). ``current_user()`` reads
       ``st.session_state``, which is correct across fragment reruns.
    """
    mark_dialog_open()
    set_user(current_user().email)


def _dialog_is_open() -> bool:
    _ts = st.session_state.get("_uv_dialog_open_ts", 0.0)
    return bool(_ts) and (time.time() - _ts) < _DIALOG_GRACE_S


def _auto_rerun(seconds: float, key: str) -> None:
    """Rerun the whole app every `seconds` while the caller keeps rendering this.

    Native replacement for streamlit-autorefresh: a fragment re-executes on the
    timer; the session flag distinguishes the initial render (part of a full
    script run — just arm the timer) from a timer tick (trigger the rerun).

    On a real timer tick it also sets ``_tick_<key>`` in session state just
    before the rerun, so the page body can tell a timed refresh from a user
    navigation via ``consumed_tick(key)`` and skip work that only needs to run
    on a genuine (re)visit.

    A timer tick is skipped entirely while a modal dialog is open (see
    ``mark_dialog_open``) — the full-app rerun would otherwise close it.
    """
    _flag = f"_auto_rerun_{key}"
    # Any genuine full script run means no dialog is mid-flow (a full rerun
    # that isn't from within the dialog has already closed it) — clear the
    # stamp so a silently-dismissed dialog can't pause refreshes indefinitely.
    st.session_state.pop("_uv_dialog_open_ts", None)

    @st.fragment(run_every=seconds)
    def _tick():
        if st.session_state.pop(_flag, False):
            return
        if _dialog_is_open():
            return
        st.session_state[f"_tick_{key}"] = True
        st.rerun(scope="app")

    st.session_state[_flag] = True
    _tick()


def consumed_tick(key: str) -> bool:
    """True (once) when the current script run was triggered by ``_auto_rerun``'s
    timer for `key` rather than by a user navigation/interaction.

    Pops the marker, so a widget interaction later in the same run doesn't still
    see it.
    """
    return bool(st.session_state.pop(f"_tick_{key}", False))


def poll_while_fetching(key: str, lane: str = "screener", *, seconds: float = 5.0) -> dict:
    """While the named background fundamentals-fetch lane is running, arm a
    short ``_auto_rerun`` so a page showing a cold-cache loading skeleton
    (components.loading_skeleton_html) fills in on its own — no user
    interaction, no waiting for the 60s price cadence.

    ``lane`` is ``"screener"`` (the exchange universe — Screener/Watchlist) or
    ``"portfolio"`` (held/sold tickers — Dashboard/Portfolio). Returns the
    fetch-progress snapshot (``{"running", "done", "total"}``) so the caller
    can render an "N/M tickers" line.
    """
    from screener import get_fetch_progress, SCREENER_FETCH, PORTFOLIO_FETCH
    prog = get_fetch_progress(PORTFOLIO_FETCH if lane == "portfolio" else SCREENER_FETCH)
    if prog.get("running"):
        _auto_rerun(seconds, key)
    return prog


def price_autorefresh(key: str) -> None:
    """Timed refresh for the live-price pages (dashboard / portfolio / risk).

    Cadence is the user's ``refresh_interval_s`` during market hours, stretched
    to at least 15 minutes outside them so idle overnight tabs don't keep
    hammering the quote feed. One implementation shared by all three pages.
    """
    interval = load_settings(current_user().email).get("refresh_interval_s", 60)
    if not is_market_hours():
        interval = max(interval, 900)
    _auto_rerun(interval, key)


def _static_bar(series: "pd.Series", title: str = "", color: str | None = None) -> None:
    """Render a static (non-zoomable) horizontal bar chart via Plotly."""
    _ui_effective_light = theme_colors().effective_light
    _bad = {"", "nan", "none", "undefined", "<na>"}
    _pairs = [
        (str(k), v) for k, v in zip(series.index, series.values)
        if pd.notna(k) and pd.notna(v)
        and str(k).strip().lower() not in _bad
    ]
    if not _pairs:
        return
    # Reverse so highest value is at top in natural Plotly order (avoids autorange="reversed" artifact)
    _labels, _vals = zip(*reversed(_pairs))
    fig = go.Figure(go.Bar(
        x=list(_vals),
        y=list(_labels),
        orientation="h",
        marker_color=color or [
            "#A32D2D" if v < 0 else "#1DD6A4" for v in _vals
        ],
    ))
    _ax_color = "#3B4D63" if _ui_effective_light else "#F5F7FA"
    fig.update_layout(
        margin=dict(l=0, r=0, t=28 if title else 24, b=0),
        title=dict(text=title or ""),
        height=max(200, len(_labels) * 32 + 60),
        xaxis=dict(fixedrange=True, tickfont=dict(color=_ax_color)),
        yaxis=dict(fixedrange=True, categoryorder="array", categoryarray=list(_labels), tickfont=dict(color=_ax_color)),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(size=12, color=_ax_color),
    )
    st.plotly_chart(fig, width="stretch", config=_CHART_CONFIG)


def _donut_chart(series: "pd.Series", title: str = "") -> None:
    """Render a static donut chart showing proportional breakdown of a value series."""
    _C = theme_colors()
    _c_surface, _c_text = _C.surface, _C.text
    _bad = {"", "nan", "none", "undefined", "<na>", "n/a"}
    _clean = series[series.index.map(lambda k: pd.notna(k) and str(k).strip().lower() not in _bad)]
    _clean = _clean[_clean > 0]
    if _clean.empty:
        st.info("No data available for this breakdown.")
        return
    _labels = [str(k) for k in _clean.index]
    _vals   = _clean.values.tolist()
    _total  = sum(_vals)
    _pcts   = [v / _total * 100 for v in _vals]
    _text   = [f"{p:.1f}%" if p >= 4 else "" for p in _pcts]
    _n      = len(_labels)
    _colors = [_DONUT_PALETTE[i % len(_DONUT_PALETTE)] for i in range(_n)]
    # Confine the pie to the left half of the plotting area so it sits close
    # to its legend instead of centering across the full card width (a wide
    # card left the pie centered around x=0.5 with a large empty gap before
    # the legend, which floats just outside the pie's own domain at x=0.58).
    _pie_cx = 0.27
    fig = go.Figure(go.Pie(
        labels=_labels,
        values=_vals,
        hole=0.52,
        domain=dict(x=[0, 0.54], y=[0, 1]),
        text=_text,
        textinfo="text",
        textposition="inside",
        insidetextorientation="horizontal",
        hovertemplate="%{label}: €%{value:,.0f} (%{percent})<extra></extra>",
        marker=dict(
            colors=_colors,
            line=dict(color=_c_surface, width=2),
        ),
        textfont=dict(color=_c_text, size=12),
    ))
    _total_short = f"€{_total/1000:,.1f}k" if _total >= 10_000 else f"€{_total:,.0f}"
    fig.update_layout(
        margin=dict(l=10, r=10, t=36 if title else 10, b=10),
        title=dict(text=title or ""),
        height=max(240, 24 * _n + 60),
        showlegend=True,
        legend=dict(
            orientation="v",
            x=0.58, xanchor="left",
            y=0.5,  yanchor="middle",
            font=dict(size=11, color=_c_text),
            itemwidth=30,
            tracegroupgap=2,
        ),
        # Center overlay — "TOTAL / <value>" inside the donut hole, matching
        # Uvalu.dc.html's compact donut. Paper coords track the pie's own
        # domain center (x=0.27, the midpoint of the [0, 0.54] domain above)
        # rather than the full plot's center, since the pie no longer spans
        # the whole width.
        annotations=[
            dict(text=f"TOTAL<br><b>{_total_short}</b>", x=_pie_cx, y=0.5, showarrow=False,
                xanchor="center", yanchor="middle",
                font=dict(size=12, color=_c_text), align="center"),
        ],
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(size=12, color=_c_text),
    )
    st.plotly_chart(fig, width="stretch", config=_CHART_CONFIG)


def _hm_color(v: float) -> str:
    """Brand-aligned treemap cell color. v in [-1, 1]: negative=danger, zero=surface, positive=teal."""
    _ui_effective_light = theme_colors().effective_light
    zero    = (245, 247, 250) if _ui_effective_light else (13, 31, 60)
    pos_end = (29, 214, 164)
    neg_end = (163, 45, 45)
    t, end  = (v, pos_end) if v >= 0 else (-v, neg_end)
    r, g, b = (int(s + t * (e - s)) for s, e in zip(zero, end))
    return f"rgb({r},{g},{b})"
