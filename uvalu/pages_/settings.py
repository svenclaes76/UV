"""Settings page — Display, Screening & veto rules, Import & Export,
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
- Display currency and number format live in the Language & region card
  (uvalu/locale_ui.py, docs/i18n-spec.md §7) instead of the mockup's two
  demo segmented controls under Display.
- Screening sliders keep the app's real ranges/units (e.g. Max debt/equity
  is 50-1000%) instead of the mockup's demo 1-3× scale.
- No "Data & alerts" card (design reference v1.3): prices refresh on a fixed
  cadence (uvalu.ui.PRICE_REFRESH_S) and there are no alert badges. Old
  refresh/alert keys in stored settings are simply ignored.
- Import/Export (per-user portfolio ops) isn't in the mockup at all but is
  a real, useful feature, so it stays; the mockup's Table density-adjacent
  settings were removed per a separate request.
- Account footer shows the real derived display name/email/role, not the
  mockup's fabricated "Marek Kowalski · Pro plan"."""
import html
import io
from datetime import datetime

import qrcode
import streamlit as st

from auth import (backup_codes_remaining, begin_totp_enrollment, change_password, consent_record,
                  confirm_totp_enrollment, disable_totp, has_password, is_totp_enabled,
                  link_identity, list_linked_identities, list_sessions, password_last_changed,
                  trusted_devices_until, BACKUP_CODE_COUNT,
                  regenerate_backup_codes, revoke_other_sessions, revoke_session,
                  revoke_trusted_devices, set_password, trusted_device_count, unlink_identity)
from backup import backup_filename
from portfolio import load_portfolio, load_targets, save_targets
from settings import (load_shared_settings, save_shared_settings, load_settings, save_settings,
                      get_score_weights, _SCORE_STYLES)
from uvalu import datamode, locale_ui, nav as nav_registry, oauth
from uvalu.compliance import disclosures
from uvalu.components import support_page
from uvalu.dialogs import _dialog, _dialog_width_css
from uvalu.i18n import N_, _, fmt_date, fmt_int, frozen, fmt_num, fmt_pct, h_, ngettext, pgettext, sort_key, tr
from uvalu.locale_ui import number_field
from uvalu.data import _load_all_screener_data
from uvalu.runtime import current_user, theme_colors
from workbook import (ImportError_, apply_import, export_all, export_workbook, parse_workbook, plan_import,
                      sheet_names)
from uvalu.shell import _display_name, _initials, _password_strength, set_theme_script


def _targets_to_text(m) -> str:
    """{'Technology': 0.25} -> 'Technology 25'."""
    if not isinstance(m, dict) or not m:
        return ""
    return "\n".join(f"{k} {round(v * 100, 4):g}" for k, v in m.items())


def _parse_targets_text(txt: str) -> dict:
    """'Technology 25' / 'AAA.BR 7.5%' per line -> {name: fraction}. Silently
    drops blank/malformed lines and out-of-range weights; save_targets()
    validates again."""
    out: dict = {}
    for line in (txt or "").splitlines():
        parts = line.replace("%", "").split()
        if len(parts) < 2:
            continue
        name = " ".join(parts[:-1]).strip()
        try:
            pct = float(parts[-1])
        except ValueError:
            continue
        if name and 0 < pct <= 100:
            out[name] = round(pct / 100, 4)
    return out


def _row_header(label: str, *, anchor: str | None = None, chip: str | None = None) -> None:
    """A card's header row, sentence case (styles.py .uv-card-head). ``anchor``
    is the id the section rail links to; ``chip`` an amber note on the right
    (the shared model settings' "affects all users")."""
    _a = f'<span id="{anchor}" class="uv-anchor"></span>' if anchor else ""
    _c = (f'<span style="font-size:10.5px;font-weight:500;'
          f'color:var(--amber-txt);background:var(--amber-bg);border-radius:6px;padding:2px 8px;'
          f'white-space:nowrap;">{chip}</span>') if chip else ""
    # One outer <div> so Markdown keeps it a raw HTML block (a leading <span>
    # would make it a paragraph, with Markdown applied inside).
    st.markdown(f'<div>{_a}<div class="uv-card-head uv-set-head"><span role="heading" aria-level="2">{label}</span>{_c}</div></div>',
                unsafe_allow_html=True)


# Section nav: (anchor, label msgid, admin-visible-only?) in page order.
_SECTIONS = (
    ("set-language", N_("Language & region")),
    ("set-account", N_("Account security")),
    ("set-display", N_("Display")),
    ("set-portfolio", N_("Target allocation")),
    ("set-withholding", N_("Dividend withholding")),
    ("set-import", N_("Import & export")),
    ("set-model", N_("Model settings")),
    ("set-privacy", N_("Privacy")),
    ("set-plan", N_("Plan")),
    ("set-legal", N_("Legal")),
)


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


_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_IMPORT_ISSUES_SHOWN = 15


def _import_done(n: int) -> None:
    st.session_state["imp_portfolio_n"] = n + 1
    st.rerun()


def _import_review(data: bytes, n: int, email: str) -> None:
    """What an uploaded workbook holds, the Add / Replace choice and the
    confirmation. Nothing is written until the user confirms."""
    from uvalu import logkit

    parsed = parse_workbook(data)
    labels = sheet_names()
    with st.container(key="set_import_review"):
        if parsed.issues:
            lines = []
            for i in parsed.issues[:_IMPORT_ISSUES_SHOWN]:
                where = labels.get(i.sheet, "")
                if i.row:
                    where = _("{sheet}, row {row}", sheet=where, row=i.row)
                lines.append(f"- {where + ': ' if where else ''}{i.message}")
            if len(parsed.issues) > _IMPORT_ISSUES_SHOWN:
                lines.append("- " + _("and {count} more", count=len(parsed.issues) - _IMPORT_ISSUES_SHOWN))
            st.error(_("This file can't be imported. Fix these rows and upload it again:") + "\n\n"
                     + "\n".join(lines))
            if st.button(_("Cancel"), key="imp_cancel", type="tertiary"):
                _import_done(n)
            return
        if parsed.empty:
            st.warning(_("This file has no rows to import."))
            if st.button(_("Cancel"), key="imp_cancel", type="tertiary"):
                _import_done(n)
            return

        mode = st.radio(_("How to import"), options=["add", "replace"], key=f"imp_mode_{n}",
                        format_func=lambda m: (_("Add to my data — new rows are added; to change existing rows, use Replace")
                                               if m == "add" else
                                               _("Replace all my data — restore this file")))
        plan = plan_import(parsed, mode)
        counts = parsed.counts()
        rows = []
        for key, total in counts.items():
            if not total:
                continue
            if mode == "add" and plan.skipped.get(key):
                rows.append(f"- {labels[key]}: " + _("{new} new, {skipped} already there",
                                                      new=fmt_int(plan.new[key]), skipped=fmt_int(plan.skipped[key])))
            else:
                rows.append(f"- {labels[key]}: {fmt_int(total)}")
        st.markdown(_("This file holds:") + "\n\n" + "\n".join(rows))

        box_key = "set_import_confirm" if mode == "replace" else "set_import_add"
        with st.container(key=box_key):
            if mode == "replace":
                st.markdown(
                    '<div style="font-size:12.5px;line-height:1.5;color:var(--text);">'
                    + h_("Your portfolio data is deleted first: positions, sales, dividends, cash and "
                         "watchlist. Your settings stay. A backup is saved before anything changes.")
                    + "</div>", unsafe_allow_html=True)
            st.markdown(
                '<div style="font-size:12px;line-height:1.5;color:var(--muted);">'
                + h_("Every imported buy and sale posts its cash, like a trade you enter by hand: "
                     "if the balance would go below zero, an automatic top-up is added.")
                + "</div>", unsafe_allow_html=True)
            with st.container(horizontal=True, gap="small"):
                _go = st.button(_("Replace my portfolio data") if mode == "replace" else _("Import"),
                                key="imp_confirm" if mode == "replace" else "imp_add")
                _no = st.button(_("Cancel"), key="imp_cancel", type="tertiary")
        if _go:
            try:
                with st.spinner(_("Importing…")):
                    done = apply_import(parsed, mode, email)
            except ImportError_ as exc:
                st.error(str(exc))
                return
            except Exception as exc:
                logkit.get_logger("uvalu.workbook").error(
                    "workbook import failed", exc_info=True, extra={"event": "workbook.import_failed"})
                st.error(_("The import failed: {error}", error=exc))
                return
            st.toast(_("Imported {positions} positions, {sold} sold positions and {dividends} dividends.",
                       positions=fmt_int(done.new["positions"]), sold=fmt_int(done.new["sold"]),
                       dividends=fmt_int(done.new["dividends"])))
            _import_done(n)
        if _no:
            _import_done(n)


@_dialog(N_("Delete your account?"), width="large")
def _dlg_delete_account(email: str):
    """Settings › Privacy › Delete account: the design's confirmation, beta
    text (no invoices in the beta), confirmed by typing the account email."""
    from account import can_delete, delete_account

    _dialog_width_css(_SETTINGS_DIALOG_WIDTH)
    st.markdown(
        '<div style="padding:10px 12px;border-radius:8px;background:var(--down-bg);color:var(--down-txt);'
        'font-size:12.5px;line-height:1.5;">'
        + h_("Your portfolio, transactions, watchlist and settings are removed from live systems now and "
             "from backups within 30 days. This can't be undone. Export your data first if you want a copy.")
        + "</div>", unsafe_allow_html=True)
    _allowed, _reason = can_delete(email)
    if not _allowed:
        st.error(_("You're the only active Admin. Make another user Admin before you delete your account."))
        return
    _typed = st.text_input(_("Type your email address to confirm"), key="set_delete_email",
                           placeholder=email)
    _b1, _b2 = st.columns(2)
    with _b1:
        if st.button(_("Cancel"), key="set_delete_cancel", width="stretch"):
            st.rerun()
    with _b2, st.container(key="uv_danger_btn_set_delete"):
        _go = st.button(_("Delete account"), key="set_delete_confirm", type="primary", width="stretch")
    if _go:
        if (_typed or "").strip().lower() != email.strip().lower():
            st.error(_("The email address doesn't match this account."))
            return
        ok, msg = delete_account(email)
        if not ok:
            st.error(msg)
            return
        # Signed out like "Sign out": app.py's handle_logout clears the
        # session and the stored token.
        st.query_params["logout"] = "1"
        st.rerun()


def _legal_doc_version(doc: str) -> tuple[str, str]:
    """(version, effective date) from a legal document's own header line."""
    from uvalu.pages_ import legal as _legal
    return _legal.doc_version(doc)


def _seg_row(row_key, widget_key, title, desc, options, current, disabled=False, ratio=(3, 1),
             format_func=str, stacked=False):
    """Title+desc on the left, a segmented control flush right — Theme/
    Display currency/Number format all share this shape. `ratio` defaults to
    the [3, 1] every 1-2-option row uses; Screening style and Price refresh
    interval (4 options each) pass a wider control column — the default
    ratio's control column is too narrow for 4 segments inside this page's
    920px-capped width (see styles.py's `nowrap` note on the segmented-
    control track, which stops them silently wrapping but doesn't by itself
    make the column wide enough).

    ``stacked`` puts the control under the title instead of beside it — for
    4-option controls next to a long description, which otherwise wrapped to
    three lines and ran into the next row's divider."""
    if stacked:
        with st.container(key=f"set_row_{row_key}"):
            _row_title(title, desc)
            return st.segmented_control(title, options=options, default=current, disabled=disabled,
                                        format_func=format_func, label_visibility="collapsed", key=widget_key)
    with st.container(key=f"set_row_{row_key}"):
        _c1, _c2 = st.columns(list(ratio), vertical_alignment="center")
        with _c1:
            _row_title(title, desc)
        with _c2:
            return st.segmented_control(title, options=options, default=current, disabled=disabled,
                                        format_func=format_func, label_visibility="collapsed", key=widget_key)


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
               f'<span style="font-family:var(--uv-mono);font-size:13px;color:var(--up-txt);">{value_str}</span>'
               f'</div>', unsafe_allow_html=True)


def _threshold_slider(widget_key, label, minv, maxv, step, current, fmt, caption, disabled=False):
    """One cell of the Screening & veto rules 2x2 grid — mono/mint value
    inline with the label (read from session_state *before* the widget so it
    reflects this rerun's value instead of lagging a step behind the slider,
    same trick uvalu/pages_/screener.py's sliders use), the help text right
    under the label, then the slider (its own thumb value is hidden by CSS —
    the label row already shows the value)."""
    _slider_label(label, fmt(st.session_state.get(widget_key, current)))
    st.markdown(f'<div style="font-size:12px;color:var(--muted);line-height:1.45;margin:-4px 0 2px;">'
                f'{html.escape(caption)}</div>', unsafe_allow_html=True)
    return st.slider(label, minv, maxv, current, step=step, key=widget_key,
                     label_visibility="collapsed", disabled=disabled)


def _style_label(style: str) -> str:
    """Screening-style option label ("Balanced" / "Value" / "Growth" /
    "Income" — values stay the English style ids)."""
    return {"Balanced": pgettext("style", "Balanced"), "Value": pgettext("style", "Value"),
            "Growth": pgettext("style", "Growth"), "Income": pgettext("style", "Income")}.get(style, style)


def _fmt_date(iso: str) -> str:
    if not iso:
        return _("unknown date")
    try:
        return fmt_date(datetime.fromisoformat(iso))
    except ValueError:
        return _("unknown date")


def _device_label(user_agent: str) -> str:
    """"Chrome on macOS" from a raw User-Agent string — a light substring
    match, not a real parser (no dependency exists in requirements.txt for
    one, and this only has to be good enough to tell two of your own
    sessions apart in a list, not to fingerprint a device)."""
    ua = user_agent or ""
    if "iPhone" in ua:
        os_label = "iOS"
    elif "iPad" in ua:
        os_label = "iPadOS"
    elif "Android" in ua:
        os_label = "Android"
    elif "Macintosh" in ua or "Mac OS X" in ua:
        os_label = "macOS"
    elif "Windows" in ua:
        os_label = "Windows"
    elif "Linux" in ua:
        os_label = "Linux"
    else:
        return _("Unknown device")

    if "Edg/" in ua:
        browser = "Edge"
    elif "OPR/" in ua or "Opera" in ua:
        browser = "Opera"
    elif "Firefox" in ua:
        browser = "Firefox"
    elif "CriOS" in ua or "Chrome" in ua:
        browser = "Chrome"
    elif "Safari" in ua:
        browser = "Safari"
    else:
        browser = _("a browser")
    return _("{browser} on {os}", browser=browser, os=os_label)


def _strength_caption(password: str) -> None:
    """Advisory-only label under a new-password field — auth.validate_new_
    password()'s min-length/HIBP check is the actual hard block on submit;
    this is just live feedback while typing (see uvalu.shell._password_strength)."""
    label, tone = _password_strength(password)
    if not label:
        return
    st.markdown(f'<div style="font-size:12px;margin-top:-8px;margin-bottom:8px;color:var(--{tone}-txt);">'
               f'{h_("Password strength: {strength}", strength=label)}</div>', unsafe_allow_html=True)


# The security dialogs' form content is ~550px wide; the visible box is the
# PARENT of [role="dialog"] (Streamlit >= 1.60) and would otherwise stretch
# to nearly the window width — same clamp the Portfolio dialogs use.
_SETTINGS_DIALOG_WIDTH = 550


@_dialog(N_("Change password"), width="large")
def _dlg_change_password(email: str):
    _dialog_width_css(_SETTINGS_DIALOG_WIDTH)
    _min_len = int(load_shared_settings().get("min_password_length", 12))
    _current = st.text_input(_("Current password"), type="password", key="set_pw_current")
    _new = st.text_input(_("New password"), type="password", key="set_pw_new",
                         help=_("At least {min_len} characters.", min_len=_min_len))
    _strength_caption(_new)
    _confirm = st.text_input(_("Confirm new password"), type="password", key="set_pw_confirm")

    _b1, _b2 = st.columns(2)
    with _b1:
        if st.button(_("Cancel"), key="set_pw_cancel", width="stretch"):
            st.rerun()
    with _b2:
        _do_change = st.button(_("Change password"), key="set_pw_submit", type="primary", width="stretch")

    if _do_change:
        if _new != _confirm:
            st.error(_("New password and confirmation don't match."))
        else:
            ok, msg = change_password(email, _current, _new)
            if ok:
                st.success(msg)
                st.caption(_("Other devices stay signed in — use “Sign out everywhere else” below if you want to end those sessions too."))
            else:
                st.error(msg)


@_dialog(N_("Set a password"), width="large")
def _dlg_set_password(email: str):
    """For a provider-only account (no current password to prove) — add one
    so you can still sign in when your provider is unavailable, mockup
    frame 11's "Password / NOT SET / Set a password" row."""
    _dialog_width_css(_SETTINGS_DIALOG_WIDTH)
    st.caption(_("Add a password so you can sign in when your provider is unavailable."))
    _min_len = int(load_shared_settings().get("min_password_length", 12))
    _new = st.text_input(_("New password"), type="password", key="set_pw2_new",
                         help=_("At least {min_len} characters.", min_len=_min_len))
    _strength_caption(_new)
    _confirm = st.text_input(_("Confirm new password"), type="password", key="set_pw2_confirm")

    _b1, _b2 = st.columns(2)
    with _b1:
        if st.button(_("Cancel"), key="set_pw2_cancel", width="stretch"):
            st.rerun()
    with _b2:
        _do_set = st.button(_("Set password"), key="set_pw2_submit", type="primary", width="stretch")

    if _do_set:
        if _new != _confirm:
            st.error(_("New password and confirmation don't match."))
        else:
            ok, msg = set_password(email, _new)
            if ok:
                st.success(msg)
            else:
                st.error(msg)


def _qr_png_bytes(uri: str) -> bytes:
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@_dialog(N_("Set up two-factor authentication"), width="large")
def _dlg_totp_enroll(email: str):
    _dialog_width_css(_SETTINGS_DIALOG_WIDTH)
    # Cache the secret/URI in session_state so re-running this dialog on
    # every widget interaction (the code text_input, the confirm button)
    # doesn't regenerate a NEW secret each time — begin_totp_enrollment()
    # would otherwise invalidate the one already shown in the QR code.
    if "totp_enroll_secret" not in st.session_state:
        _result = begin_totp_enrollment(email)
        if _result is None:
            st.error(_("Could not start enrollment. Try again."))
            return
        st.session_state["totp_enroll_secret"], st.session_state["totp_enroll_uri"] = _result

    st.caption(_("Step 1 of 2 — scan this QR code with your authenticator app (Google Authenticator, 1Password, Authy, etc.)."))
    st.image(_qr_png_bytes(st.session_state["totp_enroll_uri"]), width=200)
    st.caption(_("Can't scan it? Enter this key manually:"))
    st.code(st.session_state["totp_enroll_secret"], language=None)

    st.caption(_("Step 2 of 2 — enter the 6-digit code your app is showing."))
    code = st.text_input(_("Code"), key="totp_enroll_code", placeholder="000000")

    _b1, _b2 = st.columns(2)
    with _b1:
        if st.button(_("Cancel"), key="totp_enroll_cancel", width="stretch"):
            st.session_state.pop("totp_enroll_secret", None)
            st.session_state.pop("totp_enroll_uri", None)
            st.rerun()
    with _b2:
        _do_confirm = st.button(_("Confirm and enable"), key="totp_enroll_confirm",
                                type="primary", width="stretch")

    if _do_confirm:
        ok, msg, backup_codes = confirm_totp_enrollment(email, code)
        if ok:
            st.session_state.pop("totp_enroll_secret", None)
            st.session_state.pop("totp_enroll_uri", None)
            st.session_state["totp_new_backup_codes"] = backup_codes
            st.rerun()
        else:
            st.error(msg)


@_dialog(N_("Save your backup codes"), width="large")
def _dlg_backup_codes_shown():
    """Shown once right after enrolling (or regenerating) — the plaintext
    codes are never retrievable again after this dialog closes."""
    _dialog_width_css(_SETTINGS_DIALOG_WIDTH)
    codes = st.session_state.get("totp_new_backup_codes") or []
    st.warning(_("Save these somewhere safe. Each code can be used once if you lose access to your authenticator app. They won't be shown again."),
               icon=":material/warning:")
    st.code("\n".join(codes), language=None)
    _confirmed = st.checkbox(_("I have saved these codes."), key="totp_backup_saved")
    if st.button(_("Done"), key="totp_backup_done", type="primary", width="stretch",
                disabled=not _confirmed):
        st.session_state.pop("totp_new_backup_codes", None)
        st.session_state.pop("totp_backup_saved", None)
        st.rerun()


@_dialog(N_("Regenerate backup codes"), width="large")
def _dlg_regenerate_backup_codes(email: str):
    _dialog_width_css(_SETTINGS_DIALOG_WIDTH)
    st.warning(_("This invalidates every existing backup code — only the new ones will work."),
               icon=":material/warning:")
    _b1, _b2 = st.columns(2)
    with _b1:
        if st.button(_("Cancel"), key="totp_regen_cancel", width="stretch"):
            st.rerun()
    with _b2:
        _do_regen = st.button(_("Regenerate"), key="totp_regen_confirm", type="primary", width="stretch")
    if _do_regen:
        codes = regenerate_backup_codes(email)
        st.session_state["totp_new_backup_codes"] = codes
        st.rerun()


def render() -> None:
    # Called unconditionally at the top of every render (not gated behind a
    # button click) so a fresh rerun after enrolling/regenerating re-enters
    # this dialog instead of it disappearing the moment the triggering
    # button's own script run ends — same pattern as _dlg_restore's "done"
    # state in uvalu/pages_/admin.py.
    if st.session_state.get("totp_new_backup_codes"):
        _dlg_backup_codes_shown()

    _u = current_user()
    _email = _u.email
    _s = load_settings(_email)
    _shared = load_shared_settings()

    # Completing a "Connect" click below (oauth.start_login()) lands back on
    # the app's home page already signed in as _email via the uv_jwt cookie
    # (recover_session_from_cookie() restores it before auth_wall() ever
    # gets a chance to treat this as a fresh sign-in) — so linking the
    # identity that just came back happens here, not in authgate.py's
    # unauthenticated-visitor flow. Guarded the same way that flow guards
    # itself: st.user stays populated for the life of the OIDC session, so
    # this only fires once per identity rather than re-linking every rerun.
    _identity = oauth.current_identity()
    if _identity and not st.session_state.get("set_oauth_link_handled"):
        st.session_state["set_oauth_link_handled"] = True
        _ok, _msg = link_identity(_email, _identity["issuer"], _identity["subject"], _identity["email"])
        st.toast(_msg, icon=None if _ok else ":material/warning:")

    # The shared supporting-page frame (components.support_page): back link,
    # title, and the section list as the sticky rail beside the cards.
    # Demo mode (DM-D6): language and region only. There is no account to
    # secure, export or delete, and the other settings would change a
    # throwaway session.
    _demo = not datamode.current().sign_in
    _sections = [(a, l) for a, l in _SECTIONS if a == "set-language"] if _demo else _SECTIONS
    _content = support_page(_("Settings"), back_key="settings",
                            subtitle=(h_("Language and region.") if _demo else
                                      h_("Language, account security, display, portfolio targets, dividend withholding, "
                                         "import and export, model settings.")),
                            rail=[(tr(label), f"#{anchor}") for anchor, label in _sections])
    with _content:
        with st.container(key="set_main"):
            # ── Language & region (docs/i18n-spec.md §7) ────────────────────────────────
            # First card, so the language picker is two clicks away from any page
            # (avatar → Settings) for someone who picked a language they can't read
            # (S-06).
            locale_ui.render_card(_email, anchor="set-language")
            if _demo:
                return

            # ── Security ─────────────────────────────────────────────────────────────────
            _has_pw = has_password(_email)
            with st.container(key="set_card_security", border=True):
                _row_header(h_("Account security"), anchor="set-account")
                with st.container(key="set_row_password"):
                    _pc1, _pc2 = st.columns([3, 1], vertical_alignment="center")
                    with _pc1:
                        if _has_pw:
                            _changed = password_last_changed(_email)
                            _row_title(h_("Password"), h_("Last changed {date}.", date=_fmt_date(_changed)) if _changed
                                      else h_("No password change on record."))
                        else:
                            _row_title(
                                f'{h_("Password")}<span style="font-size:9.5px;letter-spacing:0.04em;padding:2px 7px;'
                                'border-radius:4px;background:var(--line-2);color:var(--muted);margin-left:8px;">'
                                f'{h_("NOT SET")}</span>',
                                h_("Add one so you can sign in when your provider is unavailable."))
                    with _pc2:
                        if _has_pw:
                            if st.button(pgettext("button", "Change"), key="set_pw_change_btn"):
                                _dlg_change_password(_email)
                        else:
                            if st.button(_("Set a password"), key="set_pw_set_btn", type="primary"):
                                _dlg_set_password(_email)

                # Linked accounts: one row per provider this workspace offers or the
                # account already uses, "Linked account · {provider}". Google is
                # always listed: in the beta it reads "Not in the beta".
                _linked = {oauth.label_for_issuer(i["issuer"]): i for i in list_linked_identities(_email)}
                _providers = [p for p in oauth.configured_providers()
                              if p["configured"] or p["label"] in _linked or p["id"] == "google"]
                for _prov in _providers:
                    _ident = _linked.get(_prov["label"])
                    _live = _prov["configured"] or _ident is not None
                    with st.container(key=f"set_row_linked_{_prov['id']}"):
                        _pc1b, _pc2b = st.columns([3, 1], vertical_alignment="center")
                        with _pc1b:
                            _title = h_("Linked account · {provider}", provider=_prov["label"])
                            if _ident:
                                _row_title(
                                    f'{_title}<span style="font-size:9.5px;letter-spacing:0.04em;'
                                    f'padding:2px 6px;border-radius:4px;background:var(--up-bg);'
                                    f'color:var(--up-txt);margin-left:8px;">{h_("CONNECTED")}</span>',
                                    h_("{email} · linked {date}", email=_ident.get('email_at_link', ''),
                                       date=_fmt_date(_ident.get('linked_at', ''))))
                            elif _live:
                                _row_title(_title, h_("Sign in with {provider} as well as your password.",
                                                      provider=_prov["label"]))
                            else:
                                _row_title(_title, h_("Sign-in with Google is not available in the beta."))
                        with _pc2b:
                            if _ident:
                                if st.button(_("Disconnect"), key=f"set_unlink_{_prov['id']}"):
                                    ok, msg = unlink_identity(_email, _ident["issuer"])
                                    if not ok:
                                        st.toast(msg, icon=":material/warning:")
                                    st.rerun()
                            elif _live:
                                if st.button(_("Connect"), key=f"set_link_{_prov['id']}"):
                                    oauth.start_login(_prov["id"])
                            else:
                                st.markdown('<div style="text-align:right;font-size:12px;color:var(--muted);">'
                                            f'{h_("Not in the beta")}</div>', unsafe_allow_html=True)

                # Two-factor authentication — password-path only. A provider-only
                # account's 2FA is whatever its provider itself enforces (Google's own
                # 2-step verification, say) — Uvalu has no password step to challenge
                # for that account, so this shows static "managed by provider" text
                # instead of a toggle, matching the impact doc's own scoping of 2FA
                # to the password path.
                _totp_on = is_totp_enabled(_email)
                with st.container(key="set_row_totp"):
                    _tc1, _tc2 = st.columns([3, 1], vertical_alignment="center")
                    with _tc1:
                        _row_title(h_("Two-factor authentication"),
                                  h_("Require a code from an authenticator app in addition to your password.")
                                  if _has_pw else h_("Managed by your identity provider."))
                    with _tc2:
                        if not _has_pw:
                            st.markdown('<div style="text-align:right;font-size:12px;color:var(--muted);">'
                                       f'{h_("Not applicable")}</div>', unsafe_allow_html=True)
                        else:
                            _new_totp = st.toggle(_("Two-factor authentication"), value=_totp_on,
                                                  key="set_totp_toggle", label_visibility="collapsed")
                            if _new_totp and not _totp_on:
                                _dlg_totp_enroll(_email)
                            elif not _new_totp and _totp_on:
                                disable_totp(_email)
                                st.rerun()

                if _has_pw and _totp_on:
                    with st.container(key="set_row_backup_codes"):
                        _bc1, _bc2 = st.columns([3, 1], vertical_alignment="center")
                        with _bc1:
                            _remaining = backup_codes_remaining(_email)
                            _row_title(h_("Backup codes"),
                                       h_("{count} of {total} unused. Regenerating replaces the old set.",
                                          count=fmt_int(_remaining), total=fmt_int(BACKUP_CODE_COUNT)))
                        with _bc2:
                            if st.button(_("Regenerate"), key="set_totp_regen_btn"):
                                _dlg_regenerate_backup_codes(_email)

                    with st.container(key="set_row_trusted_devices"):
                        _dc1, _dc2 = st.columns([3, 1], vertical_alignment="center")
                        with _dc1:
                            _dev_count = trusted_device_count(_email)
                            _until = trusted_devices_until(_email)
                            _row_title(h_("Trusted devices"),
                                       ngettext("{count} device skips the code until {date}.",
                                                "{count} devices skip the code until {date}.",
                                                _dev_count, date=_fmt_date(_until)) if _until
                                       else h_("No device skips the code."))
                        with _dc2:
                            if st.button(_("Revoke all"), key="set_totp_revoke_devices_btn",
                                        disabled=_dev_count == 0):
                                revoke_trusted_devices(_email)
                                st.rerun()

                # Passkeys — UI stub only (mockup frame 14): no WebAuthn/py_webauthn
                # registration or login exists yet. Shown regardless of password/TOTP
                # state (unlike the rows above) since a passkey is its own
                # independent credential. Users see "not available in the beta",
                # not the internal roadmap phase.
                with st.container(key="set_row_passkeys"):
                    _pkc1, _pkc2 = st.columns([3, 1], vertical_alignment="center")
                    with _pkc1:
                        _row_title(h_("Passkeys"), h_("Sign in with Face ID, Touch ID or a security key.")
                                   + " " + h_("Not available in the beta."))
                    with _pkc2:
                        st.button(_("Manage"), key="set_passkeys_manage_btn", disabled=True,
                                 help=_("Not available in the beta."))

                # Active sessions, inside the card: device, when it signed in (the
                # sign-in method and location aren't stored), "This session".
                _sessions = list_sessions(_email)
                _current_sid = st.session_state.get("jwt_sid")
                with st.container(key="set_row_sessions_head", horizontal=True, vertical_alignment="center",
                                  horizontal_alignment="distribute"):
                    st.markdown(f'<div style="font-size:13.5px;font-weight:500;">{h_("Active sessions")}</div>',
                                unsafe_allow_html=True, width="content")
                    if len(_sessions) > 1:
                        with st.container(key="set_sessions_revoke_wrap", width="content"):
                            if st.button(_("Sign out everywhere else"), key="set_sessions_revoke_others",
                                         type="tertiary"):
                                ok, msg = revoke_other_sessions(_email, _current_sid)
                                st.toast(msg)
                                st.rerun()
                for _sess in _sessions:
                    with st.container(key=f"set_row_session_{_sess['sid']}"):
                        _sc1, _sc2 = st.columns([3, 1], vertical_alignment="center")
                        with _sc1:
                            _is_current = _sess["sid"] == _current_sid
                            _row_title(_device_label(_sess.get("user_agent", "")),
                                       h_("Signed in {time}", time=_fmt_date(_sess['created_at'])))
                        with _sc2:
                            if _is_current:
                                st.markdown(f'<div style="text-align:right;font-size:12px;color:var(--up-txt);">'
                                            f'{h_("This session")}</div>', unsafe_allow_html=True)
                            elif st.button(_("Sign out"), key=f"set_session_signout_{_sess['sid']}"):
                                ok, msg = revoke_session(_email, _sess["sid"])
                                if not ok:
                                    st.toast(msg, icon=":material/warning:")
                                st.rerun()

            # ── Display ────────────────────────────────────────────────────────────────
            with st.container(key="set_card_display", border=True):
                _row_header(h_("Display"), anchor="set-display")

                _light = theme_colors().effective_light
                _cur_theme = "Light" if _light else "Dark"
                _theme_sel = _seg_row("theme", "set_theme_seg", h_("Theme"),
                                      h_("Deep-navy dark or surface-white light."), [N_("Dark"), N_("Light")], _cur_theme,
                                      format_func=frozen(_))
                if _theme_sel and _theme_sel != _cur_theme:
                    set_theme_script(_theme_sel)

                _cur_density = str(_s.get("density") or "comfortable")
                _density_sel = _seg_row("density", "set_density_seg", h_("Table density"),
                                        h_("Row height for holdings and screener."), ["compact", "comfortable"],
                                        _cur_density if _cur_density in ("compact", "comfortable") else "comfortable",
                                        format_func=frozen(lambda d: _("Compact") if d == "compact" else _("Comfortable")))
                if _density_sel and _density_sel != _cur_density:
                    _s["density"] = _density_sel
                    save_settings(_s, _email)
                    st.rerun()

            # ── Target allocation (per-user, personal reference weights) ────────────────
            _targets = load_targets()
            with st.container(key="set_card_targets", border=True):
                _row_header(h_("Target allocation"), anchor="set-portfolio")
                with st.container(key="set_targets_body"):
                    with st.container(key="set_targets_row_sectors"):
                        _tc1, _tc2 = st.columns([3, 2], vertical_alignment="top")
                        with _tc1:
                            _row_title(h_("Sector targets"),
                                      h_("Blank = no sector targets; the 30% guideline applies instead."))
                        with _tc2:
                            _tgt_sectors_txt = st.text_area(
                                _("Sector targets"), key="tgt_sectors",
                                value=_targets_to_text(_targets.get("sectors")), height=110,
                                placeholder=_("One per line — sector and target %:\nTechnology 25\nHealthcare 15"),
                                label_visibility="collapsed")
                    with st.container(key="set_targets_row_tickers"):
                        _tc1, _tc2 = st.columns([3, 2], vertical_alignment="top")
                        with _tc1:
                            _row_title(h_("Per-name targets"),
                                      h_("Blank = no per-name targets; only the 20% hard cap applies."))
                        with _tc2:
                            _tgt_tickers_txt = st.text_area(
                                _("Per-name targets"), key="tgt_tickers",
                                value=_targets_to_text(_targets.get("tickers")), height=110,
                                placeholder=_("One per line — ticker and target %:\nAAA.BR 10\nBBB.PA 7.5"),
                                label_visibility="collapsed")

                with st.container(key="set_targets_hhi"):
                    # Empty = the default bands (it used to be a magic 0).
                    _hc1, _hc2 = st.columns([3, 2], vertical_alignment="center")
                    with _hc1:
                        _row_title(h_("Concentration ceiling (HHI)"),
                                  h_("Flag when the portfolio's HHI exceeds this. Leave empty for the default bands."))
                    with _hc2:
                        _hhi_max = number_field(
                            _("Concentration ceiling (HHI)"), min_value=0.0, max_value=0.50,
                            value=float(_targets["hhi_max"]) if _targets.get("hhi_max") else None, step=0.01,
                            key="tgt_hhi", label_visibility="collapsed", placeholder=fmt_num(0.15, 2))

                with st.container(key="set_targets_save"):
                    _save_clicked = st.button(_("Save target allocation"), key="tgt_save", type="secondary")
                if _save_clicked:
                    _new: dict = {}
                    _secs = _parse_targets_text(_tgt_sectors_txt)
                    _tks  = _parse_targets_text(_tgt_tickers_txt)
                    if _secs:
                        _new["sectors"] = _secs
                    if _tks:
                        _new["tickers"] = _tks
                    if _hhi_max and _hhi_max > 0:
                        _new["hhi_max"] = float(_hhi_max)
                    save_targets(_new)
                    st.toast(_("Target allocation saved."))
                    st.rerun()

            # ── Dividend withholding: per country of the company (D13, D23) ─────────────
            with st.container(key="set_card_dividend_tax", border=True):
                from uvalu import withholding as _whm
                _row_header(h_("Dividend withholding"), anchor="set-withholding")
                # Translators: Settings › Dividend withholding › explanation under the card title.
                _row_desc(h_("Foreign withholding % used by default when you record a dividend, by the country where "
                             "the company is registered, not where it trades: Airbus is Dutch, so its dividends follow "
                             "the Netherlands rate. Each country starts at its statutory rate withheld at source, before "
                             "any treaty refund; set it to what your broker withholds. You can always change it per dividend."))
                with st.container(key="set_dividend_wh_grid"):     # padded card body (styles.py)
                    _overrides = dict(_s.get(_whm.SETTING_KEY) or {})
                    _moved = _s.get("withholding_moved") or []
                    if _moved:
                        # One-time notice after migration m0003 (D23).
                        st.info(_("Your withholding rates moved from exchanges to countries: {rates}. Check them below.",
                                  rates=", ".join(f"{_whm.country_name(c)} {fmt_num(float(r), 3, min_decimals=0)}%"
                                                  for c, r in _moved)))
                        if st.button(_("Got it"), key="wh_moved_ok", type="tertiary"):
                            _s.pop("withholding_moved", None)
                            save_settings(_s, _email)
                            st.rerun()
                    # Translators: Settings › Dividend withholding › Belgium has no field; this line says why.
                    st.markdown(f'<div style="font-size:12.5px;color:var(--muted);margin:2px 0 10px;">'
                                f'{h_("{country}: the Belgian withholding tax (30%) is applied automatically for Belgian residents.", country=_whm.country_name(_whm.HOME_COUNTRY))}'
                                f'</div>', unsafe_allow_html=True)
                    _held = set()
                    try:
                        _pf_wh = load_portfolio()
                        for _t in (_pf_wh["ticker"] if _pf_wh is not None and "ticker" in _pf_wh.columns else []):
                            _c = _whm.company_country(str(_t))
                            if _c in _whm.STATUTORY:
                                _held.add(_c)
                    except Exception:
                        pass
                    _by_name = lambda cs: sorted(cs, key=lambda c: sort_key(_whm.country_name(c)))
                    _wh_new: dict[str, float] = {}

                    def _wh_row(country: str) -> None:
                        _iso = _whm.STATUTORY[country][0]
                        _default = _whm.default_rate(country)
                        # Only a rate that differs from the default is "yours" (a migrated
                        # rate equal to the default reads as the default).
                        _own = country in _overrides and abs(float(_overrides[country]) - _default) > 1e-9
                        _c1, _c2 = st.columns([1.1, 1.4], vertical_alignment="bottom")
                        with _c1:
                            _v = number_field(f"{_whm.country_name(country)} (%)", min_value=0.0, max_value=100.0, step=0.5,
                                              value=float(_whm.rate_for(country, _overrides)), format="%.3g",
                                              key=f"wh_c_{_iso}")
                        _wh_new[country] = float(_whm.rate_for(country, _overrides)) if _v is None else float(_v)
                        with _c2:
                            if _own:
                                _r1, _r2 = st.columns([1, 1], vertical_alignment="center")
                                with _r1:
                                    # Translators: Settings › Dividend withholding › marks a rate the user set, with the statutory default after it.
                                    st.caption(_("Your rate · default {rate}%", rate=fmt_num(_default, 3, min_decimals=0)))
                                with _r2:
                                    if st.button(_("Reset to default"), key=f"wh_reset_{_iso}", type="tertiary"):
                                        _overrides.pop(country, None)
                                        _s[_whm.SETTING_KEY] = _overrides
                                        save_settings(_s, _email)
                                        st.session_state.pop(f"wh_c_{_iso}", None)
                                        st.rerun()
                            else:
                                # Translators: Settings › Dividend withholding › marks a statutory default rate.
                                st.caption(_("Default"))

                    for _country in _by_name(_held):
                        _wh_row(_country)
                    _others = [c for c in _whm.countries() if c not in _held]
                    with st.expander(_("Other countries") if _held else _("All countries"), expanded=not _held):
                        for _country in _by_name(_others):
                            _wh_row(_country)
                # Typed values: saved with the button, not on every keystroke/blur
                # (a half-typed rate shouldn't apply). Only rates that differ
                # from the default are stored, so a corrected default reaches
                # everyone who never changed it.
                with st.container(key="set_wh_save"):
                    if st.button(_("Save withholding rates"), key="wh_save"):
                        _s[_whm.SETTING_KEY] = {c: v for c, v in _wh_new.items()
                                                if abs(v - _whm.default_rate(c)) > 1e-9}
                        _s.pop("dividend_withholding", None)
                        save_settings(_s, _email)
                        st.toast(_("Withholding rates saved."))
                        st.rerun()

            # ── Import / Export (per-user, not admin-scoped) ─────────────────────────────
            # One workbook format both ways (docs/import-export-plan.md): export
            # holds what the user entered; import restores it (replace) or adds
            # rows added to an export (add) — the export is also the template.
            with st.container(key="set_card_import", border=True):
                _row_header(h_("Import & export"), anchor="set-import")

                # Uvalu.dc.html's two rows, on the page's own set_row_ grammar
                # (padding, right-aligned control, sibling-gap cancel).
                with st.container(key="set_row_import"):
                    _imp_l, _imp_col = st.columns([3, 2], vertical_alignment="center")
                    with _imp_l:
                        _row_title(h_("Import portfolio"),
                                   h_("Restore or add to your positions, trades, dividends and cash from an "
                                      "Uvalu .xlsx file. You confirm before anything changes."))
                    with _imp_col:
                        # A new key after an import or cancel empties the uploader —
                        # the old one kept its file, so the page re-imported it on
                        # every rerun after a successful import.
                        _imp_n = st.session_state.get("imp_portfolio_n", 0)
                        _imp_key = "imp_portfolio" if not _imp_n else f"imp_portfolio_{_imp_n}"
                        _imp_file = st.file_uploader(_("Choose a Uvalu workbook (.xlsx)"), type=["xlsx"],
                                                     key=_imp_key, label_visibility="collapsed",
                                                     disabled=_u.is_viewer)
                if _imp_file:
                    _import_review(_imp_file.getvalue(), _imp_n, _email)

                with st.container(key="set_row_export"):
                    _exp_l, _exp_col = st.columns([3, 2], vertical_alignment="center")
                    with _exp_l:
                        _row_title(h_("Excel export"), h_("Your portfolio in the same format, ready to re-import."))
                    with _exp_col:
                        with st.container(horizontal=True, gap="small", horizontal_alignment="right",
                                          key="set_export_buttons"):
                            try:
                                st.download_button(
                                    _("Download backup.xlsx"),
                                    data=export_workbook(_email),
                                    file_name=backup_filename("xlsx"),
                                    mime=_XLSX_MIME,
                                )
                            except Exception as e:
                                st.error(_("Could not create the workbook: {error}", error=e))
                # The uploader's own button text ("Upload") is framework chrome;
                # the design's label goes in through CSS. Its own hidden
                # container, so it takes no flex gap in either row.
                with st.container(key="set_upload_label"):
                    st.markdown('<style>.st-key-set_row_import [data-testid="stFileUploaderDropzone"] button[data-testid="stBaseButton-secondary"]'
                                '{--uv-upload-label:"' + h_("Choose .xlsx file").replace('"', "") + '";}</style>',
                                unsafe_allow_html=True)

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
                from screener import (DDM_STABLE_GROWTH, EQUITY_RISK_PREMIUM, model_version,
                                      portfolio_risk_free, refresh_model_switches)
                _m5_on = refresh_model_switches(_shared)
                st.markdown(
                    '<div><span id="set-model" class="uv-anchor"></span>'
                    '<div class="uv-card-head uv-set-head" style="align-items:baseline;">'
                    f'<span>{h_("Model settings in force")}</span>'
                    f'<span style="font-size:11px;font-weight:400;color:var(--muted);">'
                    f'{h_("Same for every user · model {version}", version=model_version())}</span></div></div>',
                    unsafe_allow_html=True)
                _w = get_score_weights()
                _model_rows = [
                    (h_("Undervalued: composite score"), h_("And fair value from at least two independent models."),
                     f"≥ {fmt_num(_shared.get('buy_threshold', 70), 0)}"),
                    (h_("Undervalued: margin of safety"), h_("Discount of price to model fair value."),
                     f"≥ {fmt_pct(max(10, float(_shared.get('min_mos', 10))), 0)}"),
                    (h_("Cost of equity"),
                     (h_("10-year government bond yield of the share's currency (shown: euro, Germany) "
                         "plus beta times equity risk premium.")
                      if _m5_on.get("m5_rate_per_currency", True)
                      else h_("Risk-free rate plus beta times equity risk premium.")),
                     f"{fmt_pct(portfolio_risk_free() * 100, 1)} + β × {fmt_pct(EQUITY_RISK_PREMIUM * 100, 0)}"),
                    (h_("Terminal dividend growth"), h_("Multi-stage dividend model, after year 5."),
                     fmt_pct(DDM_STABLE_GROWTH * 100, 0)),
                    (h_("Quality screen: debt / equity"), h_("Not applied to financials, real estate and utilities."),
                     f"&gt; {fmt_pct(float(_shared.get('max_debt_equity', 500)), 0)}"),
                    (h_("Score weighting"),
                     h_("Margin of safety {a} · Risk {b} · Quality {c} · Momentum {d} · Dividend {e}.",
                        a=fmt_num(_w[0] * 100, 0), b=fmt_num(_w[1] * 100, 0), c=fmt_num(_w[2] * 100, 0),
                        d=fmt_num(_w[3] * 100, 0), e=fmt_num(_w[4] * 100, 0)),
                     html.escape(_style_label(str(_shared.get("screen_style", "balanced")).capitalize()))),
                ]
                st.markdown(
                    '<div class="uv-model-rows" style="display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);'
                    'gap:0 40px;padding:4px 20px 8px;">'
                    + "".join(
                        '<div style="display:flex;justify-content:space-between;gap:16px;padding:12px 0;'
                        'border-bottom:0.5px solid var(--line-2);"><div style="min-width:0;">'
                        f'<div style="font-size:13px;font-weight:500;">{label}</div>'
                        f'<div style="font-size:11px;color:var(--muted);margin-top:3px;">{hint}</div></div>'
                        f'<span style="font-family:var(--uv-mono);font-size:13px;color:var(--text);flex:none;">{value}</span></div>'
                        for label, hint, value in _model_rows)
                    + '</div>'
                    '<div style="padding:12px 20px;font-size:12px;color:var(--muted);line-height:1.55;">'
                    f'{h_("Thresholds and weights are set centrally by Uvalu, so every user sees the same signals. Changes are logged.")} '
                    f'<a href="/help" target="_self" style="color:var(--link);text-decoration:none;">{h_("Methodology →")}</a></div>',
                    unsafe_allow_html=True)

                # Admins change them here (D2: logged); everyone else sees the list above.
                _cur_style = str(_shared.get("screen_style", "balanced"))
                _style_sel = None
                if _is_admin:
                    with st.container(key="set_slider_grid"):
                        _v1, _v2 = st.columns(2, gap="large")
                        with _v1:
                            _max_de = _threshold_slider(
                                "scr_max_de", h_("Max debt / equity"), 50, 1000, 50,
                                int(_shared.get("max_debt_equity", 500)), lambda v: fmt_pct(v, 0),
                                _("Fails the quality screen above this leverage (Financials, Real Estate, Utilities exempt)."),
                                disabled=not _is_admin)
                        with _v2:
                            _max_payout = _threshold_slider(
                                "scr_max_payout", h_("Max dividend payout"), 50, 100, 5,
                                int(_shared.get("max_payout", 90)), lambda v: fmt_pct(v, 0),
                                _("Flag dividends above this payout."), disabled=not _is_admin)

                        _v3, _v4 = st.columns(2, gap="large")
                        with _v3:
                            _min_mos = _threshold_slider(
                                "scr_min_mos", h_("Minimum margin of safety"), 10, 50, 5,
                                max(10, int(_shared.get("min_mos", 10))), lambda v: fmt_pct(v, 0, signed=True),
                                _("Margin of safety needed for the Undervalued signal; never below 10%."), disabled=not _is_admin)
                        with _v4:
                            _buy_thr = _threshold_slider(
                                "scr_buy_thr", h_("Undervalued score threshold"), 50, 90, 5,
                                int(_shared.get("buy_threshold", 70)), str,
                                _("Minimum composite score for the Undervalued signal."), disabled=not _is_admin)

                    _style_opts = [s.capitalize() for s in _SCORE_STYLES]
                    _cur_style  = str(_shared.get("screen_style", "balanced"))
                    _style_sel  = _seg_row(
                        "screen_style", "scr_style", h_("Screening style"),
                        h_("Which signals lead the composite score — Value tilts to margin of safety & quality, Growth to momentum, Income to dividends."),
                        _style_opts, _cur_style.capitalize(), disabled=not _is_admin, stacked=True,
                        format_func=frozen(_style_label))

                _stoxx = _toggle_row("stoxx", "scr_stoxx", h_("Benchmark — Euro Stoxx 50"),
                                     h_("Overlay on the portfolio value chart."),
                                     bool(_shared.get("benchmark_stoxx", False)), disabled=not _is_admin)
                _toggle_row("us", "scr_us", h_("Include US-listed names"),
                           h_("Not available: the beta covers European exchanges only."), False, disabled=True)

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
                    elif _style_sel and _style_sel.lower() != _cur_style:
                        _shared["screen_style"] = _style_sel.lower()
                        save_shared_settings(_shared)
                        _load_all_screener_data.clear()
                        st.rerun()
                    elif _stoxx != bool(_shared.get("benchmark_stoxx", False)):
                        _shared["benchmark_stoxx"] = bool(_stoxx)
                        save_shared_settings(_shared)
                        st.rerun()


            # ── Privacy (Uvalu.dc.html "Privacy" card) ─────────────────────────────────
            with st.container(key="set_card_privacy", border=True):
                _row_header(h_("Privacy"), anchor="set-privacy")
                with st.container(key="set_row_privacy_export"):
                    _c1, _c2 = st.columns([3, 1], vertical_alignment="center")
                    with _c1:
                        _row_title(h_("Export my data"),
                                   h_("Everything Uvalu holds about you: account details, settings, watchlist "
                                      "and all portfolio data, as an Excel workbook (.xlsx)."))
                    with _c2:
                        try:
                            st.download_button(_("Export"), data=export_all(_email),
                                               file_name=f"uvalu_my_data_{datetime.now():%Y%m%d_%H%M}.xlsx",
                                               mime=_XLSX_MIME, key="privacy_export")
                        except Exception as e:
                            st.error(_("Could not create the workbook: {error}", error=e))
                with st.container(key="set_row_privacy_delete"):
                    _c1, _c2 = st.columns([3, 1], vertical_alignment="center")
                    with _c1:
                        _row_title(h_("Delete account"),
                                   h_("Removes your account and data from live systems at once and from backups "
                                      "within 30 days."))
                    with _c2:
                        if st.button(_("Delete account"), key="privacy_delete"):
                            _dlg_delete_account(_email)
                with st.container(key="set_row_privacy_contact"):
                    _c1, _c2 = st.columns([3, 1], vertical_alignment="center")
                    with _c1:
                        _row_title(h_("Privacy contact"),
                                   h_("Questions about your data, or a complaint to the Belgian Data Protection "
                                      "Authority (GBA / APD)."))
                    with _c2:
                        _pc = html.escape(disclosures.producer_privacy_contact())
                        st.markdown(f'<div class="uv-set-privacy-mail"><a href="mailto:{_pc}">'
                                    f'{_pc.replace("@", "&#64;")}</a></div>', unsafe_allow_html=True)

            # ── Plan (free beta) ─────────────────────────────────────────────────────
            if disclosures.BETA:
                with st.container(key="set_card_plan", border=True):
                    _row_header(h_("Plan"), anchor="set-plan")
                    with st.container(key="set_row_plan_beta"):
                        _c1, _c2 = st.columns([5, 1], vertical_alignment="center")
                        with _c1:
                            # Same promises as the beta terms, section 2.
                            _row_title(h_("Free beta · by invitation"),
                                       h_("No paid plans during the beta and you pay nothing. We tell you at least "
                                          "14 days before the beta ends where we can, so you can export your data. "
                                          "Your account never turns into a paid plan without your express agreement."))
                        with _c2:
                            st.markdown(f'<span class="uv-set-chip-active">{h_("Active")}</span>',
                                        unsafe_allow_html=True)

            # ── Legal documents (L13, L1) ────────────────────────────────────────────
            # Version and effective date from the documents themselves, and
            # what this account accepted when it joined (auth.consent_record,
            # stored since L1). Accounts created before L1 have no record.
            with st.container(key="set_card_legal", border=True):
                _row_header(h_("Legal documents"), anchor="set-legal")
                _legal_page = nav_registry.pages.get("legal")
                _docs = {key: title for key, title, _f in disclosures.LEGAL_DOCS}
                _consent = consent_record(_email)
                _advice = _consent.get("no_advice")
                for _lkey, _ltitle, _ldesc, _ldoc in (
                        ("terms", tr(_docs["terms"]), None, "terms"),
                        ("privacy", tr(_docs["privacy"]), None, "privacy"),
                        ("advice", _("No-personal-advice acknowledgement"),
                         (h_("Terms of use, section 4. You confirmed it on {date}.",
                             date=_fmt_date(_advice["at"])) if _advice
                          else h_("Terms of use, section 4. Your acceptance isn't recorded yet.")),
                         "terms" if _advice else None)):
                    _ver, _eff = _legal_doc_version(_ldoc) if _ldoc else ("", "")
                    _title = h_("{document} · {version}", document=_ltitle, version=_ver) if _ver and _lkey != "advice" else html.escape(_ltitle)
                    _desc = _ldesc or (h_("Effective from {date}.", date=_eff) if _eff else "")
                    _acc = _consent.get(_lkey) if _lkey != "advice" else None
                    if _acc:
                        _desc = (_desc + " " if _desc else "") + h_(
                            "You accepted version {version} on {date}.",
                            version=_acc["version"] or "—", date=_fmt_date(_acc["at"]))
                    with st.container(key=f"set_row_legal_{_lkey}"):
                        _c1, _c2 = st.columns([3, 1], vertical_alignment="center")
                        with _c1:
                            _row_title(_title, _desc)
                        with _c2:
                            if _ldoc is None:
                                st.markdown(f'<span class="uv-set-chip-na">{h_("Not available")}</span>',
                                            unsafe_allow_html=True)
                            elif _legal_page is not None:
                                st.page_link(_legal_page, label=_("View"), query_params={"doc": _ldoc})
                st.markdown(f'<div class="uv-set-legal-note">'
                            f'{h_("During the beta these documents are available in English only.")}</div>',
                            unsafe_allow_html=True)

            # ── Account footer: who is signed in (G27: "Free beta", not the role) ──
            st.markdown(
                # Anchor-free: a leading <span> made Markdown read the block as a
                # paragraph and auto-link the email address.
                f'<div class="uv-set-account-footer" style="display:flex;align-items:center;gap:12px;'
                f'padding:14px 4px;border-top:0.5px solid var(--line);margin-top:4px;">'
                f'<div style="width:38px;height:38px;border-radius:8px;background:var(--navy);'
                f'border:0.5px solid var(--line);display:flex;align-items:center;justify-content:center;'
                f'font-size:13px;font-weight:600;color:var(--mint);flex:none;">{_initials(_email)}</div>'
                f'<div style="flex:1;min-width:0;"><div style="font-size:13.5px;font-weight:500;">{_display_name(_email)}</div>'
                f'<div style="font-size:12px;color:var(--muted);font-family:var(--uv-mono);overflow:hidden;'
                f'text-overflow:ellipsis;white-space:nowrap;">{_email.replace("@", "&#64;")} · {h_("Free beta")}</div></div>'
                f'<a href="/?logout=1" target="_self" class="uv-set-signout">{h_("Sign out")}</a>'
                f'</div>', unsafe_allow_html=True)
