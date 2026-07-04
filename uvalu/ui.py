"""Reusable rendering helpers: static charts, donut, treemap color, and the
click-to-select dataframe / timed auto-refresh widgets.

Theme-dependent helpers resolve the active palette via ``theme_colors()`` so
callers don't pass colors around.
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from uvalu.runtime import theme_colors

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


def _auto_rerun(seconds: float, key: str) -> None:
    """Rerun the whole app every `seconds` while the caller keeps rendering this.

    Native replacement for streamlit-autorefresh: a fragment re-executes on the
    timer; the session flag distinguishes the initial render (part of a full
    script run — just arm the timer) from a timer tick (trigger the rerun).
    """
    _flag = f"_auto_rerun_{key}"

    @st.fragment(run_every=seconds)
    def _tick():
        if st.session_state.pop(_flag, False):
            return
        st.rerun(scope="app")

    st.session_state[_flag] = True
    _tick()


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
            "#ef5350" if v < 0 else "#1DD6A4" for v in _vals
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
    fig = go.Figure(go.Pie(
        labels=_labels,
        values=_vals,
        hole=0.52,
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
    fig.update_layout(
        margin=dict(l=10, r=10, t=36 if title else 10, b=10),
        title=dict(text=title or ""),
        height=max(340, 24 * _n + 60),
        showlegend=True,
        legend=dict(
            orientation="v",
            x=1.02, xanchor="left",
            y=1.0,  yanchor="top",
            font=dict(size=11, color=_c_text),
            itemwidth=30,
            tracegroupgap=2,
        ),
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
