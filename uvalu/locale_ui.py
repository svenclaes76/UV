"""Language & region UI — the Settings card, the sign-in language switcher,
CSV export menus and a region-aware number field (docs/i18n-spec.md §7,
F-10, F-11, T-04).

Every control applies instantly (S-02): it saves the profile key, which
settings.save_settings() audit-logs with old and new values (S-07), and the
next run's i18n.activate() picks the new value up for the whole app.
"""
from __future__ import annotations

import datetime as _dt
import html

import streamlit as st

from settings import load_settings, save_settings
from uvalu import i18n
from uvalu.i18n import _, fmt_date, fmt_money, fmt_num, fmt_pct, pgettext

_KEYS = {  # profile key → widget key
    "language": "set_i18n_language",
    "region": "set_i18n_region",
    "display_currency": "set_i18n_currency",
    "date_format": "set_i18n_date_format",
    "time_zone": "set_i18n_time_zone",
    "week_start": "set_i18n_week_start",
}
_SAMPLE_DATE = _dt.date(2026, 9, 27)
# Globe next to "Language" in every language (S-06), so someone who picked a
# language they can't read still finds the way back.
GLOBE_SVG = ('<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
             'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" '
             'style="vertical-align:-2px;margin-right:6px;"><circle cx="12" cy="12" r="9"/>'
             '<path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/></svg>')


def _save(email: str, key: str, value) -> None:
    s = load_settings(email)
    if s.get(key) == value:
        return
    s[key] = value
    save_settings(s, email)


def _on_change(email: str, key: str) -> None:
    _save(email, key, st.session_state.get(_KEYS[key]))


def _sync_widgets(ctx: i18n.Ctx, profile: dict) -> None:
    """Seed each widget from the resolved context. A setting the user hasn't
    chosen (profile value None) is re-seeded every run, so a derived default
    — the display currency or week start following the region — updates
    when what it follows changes; a chosen one is seeded once."""
    seeds = {
        "language": ctx.lang,
        "region": profile.get("region") or ctx.region,
        "display_currency": ctx.currency,
        "date_format": ctx.date_format,
        "time_zone": ctx.time_zone,
        "week_start": ctx.week_start,
    }
    for key, wkey in _KEYS.items():
        if wkey not in st.session_state or profile.get(key) is None:
            st.session_state[wkey] = seeds[key]


def _row(title: str, desc: str | None = None):
    from uvalu.pages_.settings import _row_title   # shared row styling
    with st.container():
        c1, c2 = st.columns([5, 4], vertical_alignment="center")
        with c1:
            _row_title(title, desc or "")
        return c2


def _preview(ctx: i18n.Ctx) -> None:
    """S-01: sample price, portfolio total, % change, date and a BUY badge in
    the current selection."""
    from uvalu.components import signal_badge_html
    cells = [
        (_("Price"), fmt_money(42.17, "EUR")),
        (_("Total value"), fmt_money(125430.5, ctx.currency)),
        (_("Change"), fmt_pct(3.2, signed=True)),
        (_("Date"), fmt_date(_SAMPLE_DATE)),
        (_("Signal"), signal_badge_html("buy", "BUY")),
    ]
    inner = "".join(
        f'<div><div style="font-size:10.5px;letter-spacing:0.06em;text-transform:uppercase;'
        f'color:var(--faint);line-height:1.3;">{label}</div>'
        f'<div style="font-family:var(--uv-mono);font-size:13.5px;margin-top:4px;line-height:1.3;">{value}</div></div>'
        for label, value in cells)
    st.markdown(
        f'<div style="margin:6px 20px 14px;padding:12px 16px;border:0.5px solid var(--line);border-radius:8px;">'
        f'<div style="font-size:12px;color:var(--muted);margin-bottom:10px;line-height:1.3;">{_("Preview")}</div>'
        f'<div style="display:flex;flex-wrap:wrap;gap:22px 32px;">{inner}</div></div>',
        unsafe_allow_html=True)


def _reset(email: str) -> None:
    s = load_settings(email)
    for key in i18n.PROFILE_KEYS:
        s[key] = None
    save_settings(s, email)
    for wkey in _KEYS.values():
        st.session_state.pop(wkey, None)
    st.session_state.pop("_uv_lang_choice", None)
    st.session_state["_uv_i18n_reset_done"] = True


def render_card(email: str) -> None:
    """The Settings › Language & region card (spec §7.1)."""
    from uvalu.pages_.settings import _row_header
    cfg = i18n.config()
    ctx = i18n.current()
    profile = load_settings(email)
    _sync_widgets(ctx, profile)

    with st.container(key="set_card_i18n", border=True):
        _row_header(_("Language & region"))

        with st.container(key="set_row_i18n_language"):
            with _row(f"{GLOBE_SVG}{html.escape(_('Language'))}"):
                st.selectbox(
                    _("Language"), options=list(cfg.enabled_languages),
                    format_func=lambda code: i18n.language_name(code),   # each in its own language
                    key=_KEYS["language"], label_visibility="collapsed",
                    on_change=_on_change, args=(email, "language"))

        with st.container(key="set_row_i18n_region"):
            with _row(_("Region format")):
                langs = list(cfg.enabled_languages)
                regions = sorted(cfg.enabled_regions,
                                 key=lambda r: (langs.index(r.split("-")[0]) if r.split("-")[0] in langs else 99,
                                                i18n.sort_key(i18n.region_name(r))))
                same = i18n.REGION_SAME_AS_LANGUAGE
                st.selectbox(
                    _("Region format"), options=[same, *regions],
                    format_func=i18n.frozen(lambda r: (f"{_('Same as language')} — "
                                                       f"{i18n.region_name(cfg.default_region_for(ctx.lang))}"
                                                       if r == same else i18n.region_name(r))),
                    key=_KEYS["region"], label_visibility="collapsed",
                    on_change=_on_change, args=(email, "region"))

        with st.container(key="set_row_i18n_currency"):
            with _row(_("Display currency"),
                      _("Applies to portfolio totals. Individual prices stay in the currency they trade in.")):
                st.selectbox(_("Display currency"), options=list(cfg.enabled_display_currencies),
                             key=_KEYS["display_currency"], label_visibility="collapsed",
                             on_change=_on_change, args=(email, "display_currency"))

        with st.container(key="set_row_i18n_date_format"):
            with _row(_("Date format")):
                names = {"short": pgettext("date_format", "Short"),
                         "medium": pgettext("date_format", "Medium"), "iso": "ISO"}
                st.radio(_("Date format"), options=list(i18n.DATE_FORMATS),
                         format_func=i18n.frozen(lambda f: f"{names[f]} ({fmt_date(_SAMPLE_DATE, f)})"),
                         key=_KEYS["date_format"], label_visibility="collapsed",
                         on_change=_on_change, args=(email, "date_format"))

        with st.container(key="set_row_i18n_time_zone"):
            with _row(_("Time zone")):
                zones = i18n.time_zones()
                if st.session_state.get(_KEYS["time_zone"]) not in zones:
                    zones = [st.session_state[_KEYS["time_zone"]], *zones]
                st.selectbox(_("Time zone"), options=zones, key=_KEYS["time_zone"],
                             label_visibility="collapsed", on_change=_on_change, args=(email, "time_zone"))

        with st.container(key="set_row_i18n_week_start"):
            with _row(_("First day of week")):
                days = ctx.locale.days["format"]["wide"]
                day_names = {"monday": days[0], "sunday": days[6]}
                st.radio(_("First day of week"), options=list(i18n.WEEK_STARTS),
                         format_func=i18n.frozen(lambda d: day_names[d][:1].upper() + day_names[d][1:]),
                         key=_KEYS["week_start"], label_visibility="collapsed", horizontal=True,
                         on_change=_on_change, args=(email, "week_start"))

        _preview(ctx)

        with st.container(key="set_row_i18n_reset"):
            if st.session_state.pop("_uv_i18n_reset_done", False):
                st.toast(_("Settings saved"))
            if st.session_state.get("set_i18n_confirm_reset"):
                st.markdown(f'<div style="padding:4px 20px;font-size:12.5px;">'
                            f'{_("Reset all language and region settings to their defaults?")}</div>',
                            unsafe_allow_html=True)
                # Content-width buttons: fixed st.columns slots wrapped the
                # German "Auf Standard zurücksetzen" onto two lines.
                with st.container(horizontal=True, gap="small"):
                    yes = st.button(_("Reset to defaults"), key="set_i18n_reset_yes", type="primary")
                    no = st.button(_("Cancel"), key="set_i18n_reset_no")
                if yes:
                    st.session_state["set_i18n_confirm_reset"] = False
                    _reset(email)
                    st.rerun()
                if no:
                    st.session_state["set_i18n_confirm_reset"] = False
                    st.rerun()
            elif st.button(_("Reset to defaults"), key="set_i18n_reset", type="tertiary"):
                st.session_state["set_i18n_confirm_reset"] = True
                st.rerun()


def render_login_switcher() -> None:
    """Compact pre-sign-in language picker (S-04, S-06): kept in the session
    and saved to the profile at sign-in if the profile has no language yet."""
    cfg = i18n.config()
    if len(cfg.enabled_languages) < 2:
        return
    current = i18n.current().lang

    def _changed():
        i18n.set_session_language(st.session_state["auth_lang_switch"])

    if "auth_lang_switch" not in st.session_state or st.session_state["auth_lang_switch"] != current:
        st.session_state["auth_lang_switch"] = current
    with st.container(key="auth_lang_switcher"):
        st.selectbox(f":material/language: {_('Language')}", options=list(cfg.enabled_languages),
                     format_func=lambda code: i18n.language_name(code), key="auth_lang_switch",
                     label_visibility="collapsed", on_change=_changed)


# ── CSV exports (spec F-11) ──────────────────────────────────────────────────

def csv_machine(frame) -> bytes:
    """Dot decimal, ISO dates, ',' delimiter — stable for scripts."""
    import pandas as pd
    out = frame.copy()
    for c in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[c]):
            out[c] = out[c].dt.strftime("%Y-%m-%d")
    return out.to_csv(index=False).encode("utf-8")


def csv_spreadsheet(frame) -> bytes:
    """Region format for Excel: the region's decimal mark, ';' as delimiter
    when the decimal mark is a comma, dates in the user's date format. No
    thousands separators, so Excel reads every figure as a number. Starts
    with a UTF-8 BOM so Excel detects the encoding."""
    import pandas as pd
    sym = i18n.current().locale.number_symbols["latn"]
    decimal = sym["decimal"]
    sep = ";" if decimal == "," else ","
    out = frame.copy()
    for c in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[c]):
            out[c] = out[c].map(lambda v: "" if pd.isna(v) else fmt_date(v))
    return out.to_csv(index=False, sep=sep, decimal=decimal).encode("utf-8-sig")


def export_menu(label: str, *, frame, file_name: str, key: str, disabled: bool = False,
                machine_csv: bytes | None = None) -> None:
    """An Export button offering both CSV flavours (F-11). ``machine_csv``
    overrides the machine export when the caller already builds one."""
    with st.popover(label, icon=":material/download:", disabled=disabled):
        stem = file_name.rsplit(".", 1)[0]
        st.download_button(_("Spreadsheet format (for Excel)"), data=csv_spreadsheet(frame),
                           file_name=f"{stem}_excel.csv", mime="text/csv", key=f"{key}_xl",
                           width="stretch")
        st.download_button(_("Machine format (for scripts)"),
                           data=machine_csv if machine_csv is not None else csv_machine(frame),
                           file_name=file_name, mime="text/csv", key=key, width="stretch")


# ── Number fields (spec T-04, F-10) ──────────────────────────────────────────

def comma_decimal_region() -> bool:
    return i18n.current().locale.number_symbols["latn"]["decimal"] != "."


def number_field(label: str, *, key: str, value=None, min_value=None, max_value=None, step=None,
                 format: str | None = None, help: str | None = None, placeholder: str | None = None,
                 disabled: bool = False, label_visibility: str = "visible"):
    """st.number_input where the region writes a dot decimal (the native
    widget only accepts '.'); a text input read with parse_num() where it
    writes a comma (T-04). The text variant shows the parsed value back and
    rejects what it can't read or what falls outside min/max (F-10),
    returning None until the input is valid. Integer fields (int step/value)
    return an int."""
    if not comma_decimal_region():
        return st.number_input(label, value=value, min_value=min_value, max_value=max_value, step=step,
                               format=format, help=help, placeholder=placeholder, disabled=disabled,
                               label_visibility=label_visibility, key=key)
    is_int = isinstance(step, int) or (step is None and isinstance(value, int))
    decimals = 0 if is_int else _decimals_from(format, step)
    tkey = f"{key}__txt"
    if tkey not in st.session_state:
        st.session_state[tkey] = "" if value is None else fmt_num(value, decimals, min_decimals=0, grouping=False)
    raw = st.text_input(label, key=tkey, help=help, disabled=disabled, label_visibility=label_visibility,
                        placeholder=placeholder or i18n.number_example())
    try:
        parsed = i18n.parse_num(raw)
    except i18n.NumberParseError as e:
        st.caption(f":red[{e.message}]")
        return None
    if parsed is None:
        return None
    if is_int:
        if parsed != int(parsed):
            st.caption(f":red[{i18n.NumberParseError(raw, fmt_num(1234, 0)).message}]")
            return None
        parsed = int(parsed)
    if min_value is not None and parsed < min_value:
        st.caption(f":red[{_('Must be at least {min}.', min=fmt_num(min_value, decimals, min_decimals=0))}]")
        return None
    if max_value is not None and parsed > max_value:
        st.caption(f":red[{_('Must be at most {max}.', max=fmt_num(max_value, decimals, min_decimals=0))}]")
        return None
    if raw.strip() != fmt_num(parsed, decimals, min_decimals=0):
        st.caption(f"= {fmt_num(parsed, decimals, min_decimals=0)}")   # F-10: parsed value shown back
    return parsed


def _decimals_from(format: str | None, step) -> int:
    import re
    m = re.search(r"%\.(\d+)f", format or "")
    if m:
        return int(m.group(1))
    if isinstance(step, float) and step > 0:
        s = f"{step:.10f}".rstrip("0")
        return len(s.split(".")[1]) if "." in s else 0
    return 2
