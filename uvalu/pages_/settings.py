"""Settings page — Display, Screening & veto rules, Data, Import & Export,
matching the Uvalu.dc.html mockup's Settings screen: one bordered/shadowed
card per section (uppercase header row, then flat hairline-divided setting
rows), imported from the claude.ai/design project (projectId
edc1baa4-ffbe-46e8-828c-a545703d9112) via the DesignSync MCP tool.

Real-vs-mockup differences below are all intentional — the mockup is a
static single-state demo; this keeps the app's real behavior and only
borrows its visual chrome:
- Every control saves immediately on change (no Save button, per request) —
  each one compares its new widget value against the persisted one and only
  writes + reruns when it actually changed, so dragging a slider without
  releasing on a new value doesn't spam disk writes.
- Display currency/Number format stay disabled single-option controls (app
  is EUR-only, one decimal format) instead of the mockup's 4/2 demo options.
- Screening sliders keep the app's real ranges/units (e.g. Max debt/equity
  is 50-1000%) instead of the mockup's demo 1-3× scale.
- The mockup's "Alerts & data" card (4 notification toggles + Price refresh
  interval) is now just "Data" with Price refresh interval only — the
  notification toggles were removed per request (they were never wired to
  any real delivery mechanism — no email/push exists in this app — so the
  toggles didn't do anything besides store an unused preference).
- Import/Export (per-user portfolio ops) isn't in the mockup at all but is
  a real, useful feature, so it stays; the mockup's Table density-adjacent
  settings were removed per a separate request.
- Account footer shows the real derived display name/email/role, not the
  mockup's fabricated "Marek Kowalski · Pro plan"."""
import traceback

import streamlit as st

from backup import export_excel, backup_filename
from portfolio import parse_excel, user_data_dir, save_portfolio, save_sold, save_div_hist
from settings import load_shared_settings, save_shared_settings, load_settings, save_settings
from uvalu import nav as nav_registry
from uvalu.data import _load_all_screener_data
from uvalu.runtime import current_user, theme_colors
from uvalu.shell import _display_name, _initials, set_theme_script


def _row_header(label: str) -> None:
    st.markdown(f'<div style="padding:15px 20px;border-bottom:0.5px solid var(--line-2);font-size:13px;'
               f'font-weight:600;letter-spacing:0.03em;text-transform:uppercase;color:var(--faint);'
               f'line-height:1.3;">{label}</div>', unsafe_allow_html=True)


def _row_desc(text: str) -> None:
    st.markdown(f'<div style="padding:10px 20px 2px;font-size:12px;color:var(--muted);line-height:1.5;">'
               f'{text}</div>', unsafe_allow_html=True)


def _row_title(title: str, desc: str) -> None:
    # Explicit line-height on both lines — without it these inherit
    # Streamlit's own markdown default (1.6), noticeably taller than the
    # 1.3/1.5 convention every other raw-HTML caption in this app uses
    # (uvalu/pages_/dashboard.py, risk.py, analysis.py, drawer.py), which
    # was inflating every row's height well past its real needed size.
    st.markdown(f'<div><div style="font-size:13.5px;font-weight:500;line-height:1.3;">{title}</div>'
               f'<div style="font-size:12px;color:var(--muted);margin-top:2px;line-height:1.5;">{desc}</div></div>',
               unsafe_allow_html=True)


def _seg_row(row_key, widget_key, title, desc, options, current, disabled=False):
    """Title+desc on the left, a segmented control flush right — Theme/
    Display currency/Number format all share this shape."""
    with st.container(key=f"set_row_{row_key}"):
        _c1, _c2 = st.columns([3, 1], vertical_alignment="center")
        with _c1:
            _row_title(title, desc)
        with _c2:
            return st.segmented_control(title, options=options, default=current, disabled=disabled,
                                        label_visibility="collapsed", key=widget_key)


def _toggle_row(row_key, widget_key, title, desc, value, disabled=False):
    """Title+desc on the left, a toggle switch flush right — Benchmark and
    Include US-listed share this shape."""
    with st.container(key=f"set_row_{row_key}"):
        _c1, _c2 = st.columns([3, 1], vertical_alignment="center")
        with _c1:
            _row_title(title, desc)
        with _c2:
            return st.toggle(title, value=value, disabled=disabled,
                             label_visibility="collapsed", key=widget_key)


def _slider_label(label: str, value_str: str) -> None:
    st.markdown(f'<div style="display:flex;align-items:baseline;justify-content:space-between;'
               f'margin-bottom:9px;line-height:1.3;"><span style="font-size:13px;font-weight:500;">{label}</span>'
               f'<span style="font-family:var(--uv-mono);font-size:13px;color:var(--mint);">{value_str}</span>'
               f'</div>', unsafe_allow_html=True)


def _threshold_slider(widget_key, label, minv, maxv, step, current, fmt, caption, disabled=False):
    """One cell of the Screening & veto rules 2x2 grid — mono/mint value
    inline with the label (read from session_state *before* the widget so it
    reflects this rerun's value instead of lagging a step behind the slider,
    same trick uvalu/pages_/screener.py's sliders use), then the slider, then
    a caption below."""
    _slider_label(label, fmt(st.session_state.get(widget_key, current)))
    _val = st.slider(label, minv, maxv, current, step=step, key=widget_key,
                     label_visibility="collapsed", disabled=disabled)
    st.caption(caption)
    return _val


def render() -> None:
    _u = current_user()
    _email = _u.email
    _s = load_settings(_email)
    _shared = load_shared_settings()

    _dash_page = nav_registry.pages.get("dashboard")
    if _dash_page is not None and st.button("← Back", key="set_back", type="tertiary"):
        st.switch_page(_dash_page)

    st.markdown('<div style="font-size:22px;font-weight:500;letter-spacing:-0.02em;">Settings</div>',
               unsafe_allow_html=True)
    st.caption("Display preferences and screening thresholds. Changes apply immediately.")

    # ── Display ────────────────────────────────────────────────────────────────
    with st.container(key="set_card_display", border=True):
        _row_header("Display")

        _light = theme_colors().effective_light
        _cur_theme = "Light" if _light else "Dark"
        _theme_sel = _seg_row("theme", "set_theme_seg", "Theme",
                              "Deep-navy dark or surface-white light.", ["Dark", "Light"], _cur_theme)
        if _theme_sel and _theme_sel != _cur_theme:
            set_theme_script(_theme_sel)

        _seg_row("currency", "set_currency_seg", "Display currency",
                 "Reporting currency for values and P&amp;L.", ["EUR"], "EUR", disabled=True)

        _seg_row("numfmt", "set_numfmt_seg", "Number format",
                 "Decimal and thousands separators.", ["1,234.56"], "1,234.56", disabled=True)

    # ── Screening & veto rules ───────────────────────────────────────────────────
    # Admin-only: these are shared, all-user settings (settings.py's own
    # docstring calls them "admin-controlled, apply to all users") that drive
    # every BUY/MONITOR/AVOID decision app-wide — not a personal preference
    # like Display/Data below. Gated the same way admin.py gates its whole
    # page and portfolio.py/drawer.py disable mutating controls for Viewers
    # (`disabled=_is_viewer`); this card was the one place in the app that
    # let any signed-in user, including a read-only Viewer, change every
    # other user's screening results.
    _is_admin = _u.is_admin
    with st.container(key="set_card_screening", border=True):
        _row_header("Screening &amp; veto rules")
        _row_desc("These drive every BUY/MONITOR/AVOID decision across the app — Screener, "
                 "Watchlist, Dashboard, Portfolio and Analysis all read the same values."
                 + ("" if _is_admin else " Admin-only — sign in as an Admin to change these."))

        with st.container(key="set_slider_grid"):
            _v1, _v2 = st.columns(2, gap="large")
            with _v1:
                _max_de = _threshold_slider(
                    "scr_max_de", "Max debt / equity", 50, 1000, 50,
                    int(_shared.get("max_debt_equity", 500)), lambda v: f"{v}%",
                    "Hard veto above this leverage (Financials, Real Estate, Utilities exempt).",
                    disabled=not _is_admin)
            with _v2:
                _max_payout = _threshold_slider(
                    "scr_max_payout", "Max dividend payout", 50, 100, 5,
                    int(_shared.get("max_payout", 90)), lambda v: f"{v}%",
                    "Flag dividends above this payout.", disabled=not _is_admin)

            _v3, _v4 = st.columns(2, gap="large")
            with _v3:
                _min_mos = _threshold_slider(
                    "scr_min_mos", "Target margin of safety", -20, 50, 5,
                    int(_shared.get("min_mos", 0)), lambda v: f'{"+" if v >= 0 else ""}{v}%',
                    "Discount to fair value required for a BUY.", disabled=not _is_admin)
            with _v4:
                _buy_thr = _threshold_slider(
                    "scr_buy_thr", "BUY score threshold", 50, 90, 5,
                    int(_shared.get("buy_threshold", 70)), str,
                    "Composite score required for a BUY signal.", disabled=not _is_admin)

        _stoxx = _toggle_row("stoxx", "scr_stoxx", "Benchmark — Euro Stoxx 50",
                             "Overlay on the portfolio value chart.",
                             bool(_shared.get("benchmark_stoxx", False)), disabled=not _is_admin)
        _toggle_row("us", "scr_us", "Include US-listed names",
                   "Extend the screener beyond European exchanges.", False, disabled=True)

        # Save immediately, one field at a time — only the field the user
        # actually just touched differs from the persisted value, so at most
        # one of these branches fires on a given rerun. Guarded by _is_admin
        # server-side too, not just via the widgets' disabled= above — a
        # disabled Streamlit widget can't be driven by the user, but this
        # keeps the write path itself from ever depending on that alone.
        if _is_admin:
            _veto_changed = (
                _max_de     != _shared.get("max_debt_equity", 500) or
                _max_payout != _shared.get("max_payout", 90) or
                _min_mos    != _shared.get("min_mos", 0) or
                _buy_thr    != _shared.get("buy_threshold", 70)
            )
            if _veto_changed:
                _shared["max_debt_equity"] = float(_max_de)
                _shared["max_payout"]      = float(_max_payout)
                _shared["min_mos"]         = float(_min_mos)
                _shared["buy_threshold"]   = float(_buy_thr)
                save_shared_settings(_shared)
                _load_all_screener_data.clear()
                st.rerun()
            elif _stoxx != bool(_shared.get("benchmark_stoxx", False)):
                _shared["benchmark_stoxx"] = bool(_stoxx)
                save_shared_settings(_shared)
                st.rerun()

    # ── Data ─────────────────────────────────────────────────────────────────────
    with st.container(key="set_card_data", border=True):
        _row_header("Data")

        with st.container(key="set_row_refresh"):
            _c1, _c2 = st.columns([3, 1], vertical_alignment="center")
            with _c1:
                _row_title("Price refresh interval", "How often quotes update during market hours.")
            with _c2:
                _refresh_opts = [30, 60, 300, 900]
                _refresh_fmt = lambda s: f"{s}s" if s < 60 else f"{s // 60} min"
                _cur_refresh = _s.get("refresh_interval_s", 60)
                _refresh_idx = _refresh_opts.index(_cur_refresh) if _cur_refresh in _refresh_opts else 1
                _slider_label("", _refresh_fmt(st.session_state.get("disp_refresh_interval",
                                                                    _refresh_opts[_refresh_idx])))
                _new_refresh = st.select_slider(
                    "Price refresh interval", options=_refresh_opts,
                    value=_refresh_opts[_refresh_idx], format_func=_refresh_fmt,
                    key="disp_refresh_interval", label_visibility="collapsed")

        if int(_new_refresh) != _cur_refresh:
            _s["refresh_interval_s"] = int(_new_refresh)
            save_settings(_s, _email)
            st.rerun()

    # ── Import / Export (per-user, not admin-scoped) ─────────────────────────────
    with st.container(key="set_card_import", border=True):
        _row_header("Import &amp; export")

        with st.container(key="set_import_row"):
            _imp_col, _exp_col = st.columns(2, gap="large")
            with _imp_col:
                with st.container(key="set_import_body"):
                    _row_title("Import portfolio",
                              "Upload an Excel file to import positions, sold history and dividends. "
                              "This replaces all existing portfolio data for this account.")
                _imp_file = st.file_uploader("Choose your portfolio .xlsx file", type=["xlsx"], key="imp_portfolio",
                                             label_visibility="collapsed")
                if _imp_file:
                    with st.spinner("Parsing Excel…"):
                        try:
                            _imp_pf, _imp_sold, _imp_div = parse_excel(_imp_file)
                            if _imp_pf.empty:
                                st.error("No open EBR:/AMS:/EPA:/BIT:/ETR:/SWX: positions found. Check that your file matches the expected format.")
                            else:
                                _udir = user_data_dir(_email)
                                (_udir / "portfolio.json").unlink(missing_ok=True)
                                (_udir / "sold.json").unlink(missing_ok=True)
                                (_udir / "dividends_history.json").unlink(missing_ok=True)
                                save_portfolio(_imp_pf)
                                save_sold(_imp_sold)
                                save_div_hist(_imp_div)
                                st.success(f"Imported {len(_imp_pf)} open, {len(_imp_sold)} sold, {len(_imp_div)} dividend records.")
                                st.rerun()
                        except Exception as e:
                            st.error(f"Could not parse file: {e}")
                            st.code(traceback.format_exc())

            with _exp_col:
                with st.container(key="set_export_body"):
                    _row_title("Excel export",
                              "Human-readable workbook with positions, dividends, sold history and "
                              "watchlist. Useful for inspection or migration.")
                try:
                    xls_bytes = export_excel()
                    st.download_button(
                        "Download backup.xlsx",
                        data=xls_bytes,
                        file_name=backup_filename("xlsx"),
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                except ValueError:
                    st.info("Your portfolio is empty. Add positions in the Portfolio section first, then come back to export.")
                except Exception as e:
                    st.error(f"Could not create Excel: {e}")

    # ── Account footer ─────────────────────────────────────────────────────────
    # One raw-HTML flex row (not st.columns) — nothing here is an interactive
    # widget, and Streamlit's per-column vertical_alignment centering proved
    # unreliable for mismatched-height siblings (confirmed live: an 8px
    # offset between the avatar square and the Sign out pill persisted even
    # after forcing align-items:center + matching explicit heights on a
    # column-based version). A single native CSS flex row centers all three
    # exactly.
    with st.container(key="set_account_footer"):
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:12px;">'
            f'<div style="width:38px;height:38px;border-radius:9px;background:var(--navy);'
            f'border:0.5px solid var(--line);display:flex;align-items:center;justify-content:center;'
            f'font-size:13px;font-weight:600;color:var(--mint);flex:none;">{_initials(_email)}</div>'
            f'<div style="flex:1;"><div style="font-size:13.5px;font-weight:500;">{_display_name(_email)}</div>'
            f'<div style="font-size:12px;color:var(--faint);font-family:var(--uv-mono);">'
            f'{_email} · {_u.role.capitalize()}</div></div>'
            f'<a href="/?logout=1" target="_self" class="uv-set-signout">Sign out</a>'
            f'</div>', unsafe_allow_html=True)
