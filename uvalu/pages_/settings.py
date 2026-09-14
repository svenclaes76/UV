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
import io
import traceback
from datetime import datetime

import qrcode
import streamlit as st

from auth import (backup_codes_remaining, begin_totp_enrollment, change_password,
                  confirm_totp_enrollment, disable_totp, has_password, is_totp_enabled,
                  link_identity, list_linked_identities, list_sessions, password_last_changed,
                  regenerate_backup_codes, revoke_other_sessions, revoke_session,
                  revoke_trusted_devices, set_password, trusted_device_count, unlink_identity)
from backup import export_excel, backup_filename
from portfolio import (parse_excel, user_data_dir, save_portfolio, save_sold,
                       save_div_hist, load_targets, save_targets)
from settings import (load_shared_settings, save_shared_settings, load_settings, save_settings,
                      _SCORE_STYLES)
from uvalu import nav as nav_registry, oauth
from uvalu.data import _load_all_screener_data
from uvalu.runtime import current_user, theme_colors
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


def _seg_row(row_key, widget_key, title, desc, options, current, disabled=False, ratio=(3, 1)):
    """Title+desc on the left, a segmented control flush right — Theme/
    Display currency/Number format all share this shape. `ratio` defaults to
    the [3, 1] every 1-2-option row uses; Screening style and Price refresh
    interval (4 options each) pass a wider control column — the default
    ratio's control column is too narrow for 4 segments inside this page's
    920px-capped width (see styles.py's `nowrap` note on the segmented-
    control track, which stops them silently wrapping but doesn't by itself
    make the column wide enough)."""
    with st.container(key=f"set_row_{row_key}"):
        _c1, _c2 = st.columns(list(ratio), vertical_alignment="center")
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


def _fmt_date(iso: str) -> str:
    if not iso:
        return "unknown date"
    try:
        return datetime.fromisoformat(iso).strftime("%d %b %Y")
    except ValueError:
        return "unknown date"


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
        return "Unknown device"

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
        browser = "a browser"
    return f"{browser} on {os_label}"


def _strength_caption(password: str) -> None:
    """Advisory-only label under a new-password field — auth.validate_new_
    password()'s min-length/HIBP check is the actual hard block on submit;
    this is just live feedback while typing (see uvalu.shell._password_strength)."""
    label, tone = _password_strength(password)
    if not label:
        return
    st.markdown(f'<div style="font-size:12px;margin-top:-8px;margin-bottom:8px;color:var(--{tone}-txt);">'
               f'Password strength: {label}</div>', unsafe_allow_html=True)


@st.dialog("Change password", width="large")
def _dlg_change_password(email: str):
    _min_len = int(load_shared_settings().get("min_password_length", 12))
    _current = st.text_input("Current password", type="password", key="set_pw_current")
    _new = st.text_input("New password", type="password", key="set_pw_new",
                         help=f"At least {_min_len} characters.")
    _strength_caption(_new)
    _confirm = st.text_input("Confirm new password", type="password", key="set_pw_confirm")

    _b1, _b2 = st.columns(2)
    with _b1:
        if st.button("Cancel", key="set_pw_cancel", width="stretch"):
            st.rerun()
    with _b2:
        _do_change = st.button("Change password", key="set_pw_submit", type="primary", width="stretch")

    if _do_change:
        if _new != _confirm:
            st.error("New password and confirmation don't match.")
        else:
            ok, msg = change_password(email, _current, _new)
            if ok:
                st.success(msg)
                st.caption("Other devices stay signed in — use “Sign out everywhere else” "
                          "below if you want to end those sessions too.")
            else:
                st.error(msg)


@st.dialog("Set a password", width="large")
def _dlg_set_password(email: str):
    """For a provider-only account (no current password to prove) — add one
    so you can still sign in when your provider is unavailable, mockup
    frame 11's "Password / NOT SET / Set a password" row."""
    st.caption("Add a password so you can sign in when your provider is unavailable.")
    _min_len = int(load_shared_settings().get("min_password_length", 12))
    _new = st.text_input("New password", type="password", key="set_pw2_new",
                         help=f"At least {_min_len} characters.")
    _strength_caption(_new)
    _confirm = st.text_input("Confirm new password", type="password", key="set_pw2_confirm")

    _b1, _b2 = st.columns(2)
    with _b1:
        if st.button("Cancel", key="set_pw2_cancel", width="stretch"):
            st.rerun()
    with _b2:
        _do_set = st.button("Set password", key="set_pw2_submit", type="primary", width="stretch")

    if _do_set:
        if _new != _confirm:
            st.error("New password and confirmation don't match.")
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


@st.dialog("Set up two-factor authentication", width="large")
def _dlg_totp_enroll(email: str):
    # Cache the secret/URI in session_state so re-running this dialog on
    # every widget interaction (the code text_input, the confirm button)
    # doesn't regenerate a NEW secret each time — begin_totp_enrollment()
    # would otherwise invalidate the one already shown in the QR code.
    if "totp_enroll_secret" not in st.session_state:
        _result = begin_totp_enrollment(email)
        if _result is None:
            st.error("Could not start enrollment. Try again.")
            return
        st.session_state["totp_enroll_secret"], st.session_state["totp_enroll_uri"] = _result

    st.caption("Step 1 of 2 — scan this QR code with your authenticator app "
              "(Google Authenticator, 1Password, Authy, etc.).")
    st.image(_qr_png_bytes(st.session_state["totp_enroll_uri"]), width=200)
    st.caption("Can't scan it? Enter this key manually:")
    st.code(st.session_state["totp_enroll_secret"], language=None)

    st.caption("Step 2 of 2 — enter the 6-digit code your app is showing.")
    code = st.text_input("Code", key="totp_enroll_code", placeholder="000000")

    _b1, _b2 = st.columns(2)
    with _b1:
        if st.button("Cancel", key="totp_enroll_cancel", width="stretch"):
            st.session_state.pop("totp_enroll_secret", None)
            st.session_state.pop("totp_enroll_uri", None)
            st.rerun()
    with _b2:
        _do_confirm = st.button("Confirm and enable", key="totp_enroll_confirm",
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


@st.dialog("Save your backup codes", width="large")
def _dlg_backup_codes_shown():
    """Shown once right after enrolling (or regenerating) — the plaintext
    codes are never retrievable again after this dialog closes."""
    codes = st.session_state.get("totp_new_backup_codes") or []
    st.warning("Save these somewhere safe. Each code can be used once if you lose access "
              "to your authenticator app. They won't be shown again.", icon=":material/warning:")
    st.code("\n".join(codes), language=None)
    _confirmed = st.checkbox("I have saved these codes.", key="totp_backup_saved")
    if st.button("Done", key="totp_backup_done", type="primary", width="stretch",
                disabled=not _confirmed):
        st.session_state.pop("totp_new_backup_codes", None)
        st.session_state.pop("totp_backup_saved", None)
        st.rerun()


@st.dialog("Regenerate backup codes", width="large")
def _dlg_regenerate_backup_codes(email: str):
    st.warning("This invalidates every existing backup code — only the new ones will work.",
              icon=":material/warning:")
    _b1, _b2 = st.columns(2)
    with _b1:
        if st.button("Cancel", key="totp_regen_cancel", width="stretch"):
            st.rerun()
    with _b2:
        _do_regen = st.button("Regenerate", key="totp_regen_confirm", type="primary", width="stretch")
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

    # Centered, width-capped content column matching Uvalu.dc.html's own
    # Settings frame (`max-width:920px;margin:0 auto`) -- without this the
    # page inherited the app's global full-width block-container rule
    # (uvalu/styles.py), which stretched every row edge-to-edge on a wide
    # window instead of the design's tightly grouped card rows.
    with st.container(key="set_root"):
        _dash_page = nav_registry.pages.get("dashboard")
        if _dash_page is not None and st.button("← Back", key="set_back", type="tertiary"):
            st.switch_page(_dash_page)

        st.markdown('<div style="font-size:22px;font-weight:500;letter-spacing:-0.02em;">Settings</div>',
                   unsafe_allow_html=True)
        st.caption("Display preferences and screening thresholds. Changes apply immediately.")

        # ── Security ─────────────────────────────────────────────────────────────────
        _has_pw = has_password(_email)
        with st.container(key="set_card_security", border=True):
            _row_header("Security")
            with st.container(key="set_row_password"):
                _pc1, _pc2 = st.columns([3, 1], vertical_alignment="center")
                with _pc1:
                    if _has_pw:
                        _changed = password_last_changed(_email)
                        _row_title("Password", f"Last changed {_fmt_date(_changed)}." if _changed
                                  else "No password change on record.")
                    else:
                        _row_title(
                            'Password<span style="font-size:9.5px;letter-spacing:0.04em;padding:2px 7px;'
                            'border-radius:4px;background:var(--line-2);color:var(--faint);margin-left:8px;">'
                            'NOT SET</span>',
                            "Add one so you can sign in when your provider is unavailable.")
                with _pc2:
                    if _has_pw:
                        if st.button("Change", key="set_pw_change_btn"):
                            _dlg_change_password(_email)
                    else:
                        if st.button("Set a password", key="set_pw_set_btn", type="primary"):
                            _dlg_set_password(_email)

            # Linked accounts — one row per known provider (oauth.PROVIDERS), not
            # just the ones this account has linked, so an unconfigured/
            # unlinked provider still shows up dimmed instead of only appearing
            # once someone connects it (mockup: "adding one later changes a
            # state rather than a layout").
            with st.container(key="set_row_linked"):
                _lc1, _lc2 = st.columns([3, 1], vertical_alignment="center")
                with _lc1:
                    _row_title("Linked accounts", "One row per configured provider.")
                _linked = {oauth.label_for_issuer(i["issuer"]): i for i in list_linked_identities(_email)}
                for _prov in oauth.configured_providers():
                    _ident = _linked.get(_prov["label"])
                    with st.container(key=f"set_row_linked_{_prov['id']}"):
                        _pc1b, _pc2b = st.columns([3, 1], vertical_alignment="center")
                        with _pc1b:
                            if _ident:
                                _meta = f"{_ident.get('email_at_link', '')} · linked {_fmt_date(_ident.get('linked_at', ''))}"
                                _row_title(
                                    f'{_prov["label"]}<span style="font-size:9.5px;letter-spacing:0.04em;'
                                    f'padding:2px 6px;border-radius:4px;background:var(--up-bg);'
                                    f'color:var(--up-txt);margin-left:8px;">CONNECTED</span>', _meta)
                            elif _prov["configured"]:
                                _row_title(_prov["label"], "Available for this workspace.")
                            else:
                                _row_title(_prov["label"], "Not configured for this workspace.")
                        with _pc2b:
                            if _ident:
                                if st.button("Disconnect", key=f"set_unlink_{_prov['id']}"):
                                    ok, msg = unlink_identity(_email, _ident["issuer"])
                                    if not ok:
                                        st.toast(msg, icon=":material/warning:")
                                    st.rerun()
                            elif _prov["configured"]:
                                if st.button("Connect", key=f"set_link_{_prov['id']}"):
                                    oauth.start_login(_prov["id"])
                            else:
                                st.markdown('<div style="text-align:right;font-size:12px;color:var(--faint);">'
                                           'Unavailable</div>', unsafe_allow_html=True)

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
                    _row_title("Two-factor authentication",
                              "Require a code from an authenticator app in addition to your password."
                              if _has_pw else "Managed by your identity provider.")
                with _tc2:
                    if not _has_pw:
                        st.markdown('<div style="text-align:right;font-size:12px;color:var(--faint);">'
                                   'Not applicable</div>', unsafe_allow_html=True)
                    else:
                        _new_totp = st.toggle("Two-factor authentication", value=_totp_on,
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
                        _row_title("Backup codes", f"{_remaining} unused code{'s' if _remaining != 1 else ''} "
                                  "remaining.")
                    with _bc2:
                        if st.button("Regenerate", key="set_totp_regen_btn"):
                            _dlg_regenerate_backup_codes(_email)

                with st.container(key="set_row_trusted_devices"):
                    _dc1, _dc2 = st.columns([3, 1], vertical_alignment="center")
                    with _dc1:
                        _dev_count = trusted_device_count(_email)
                        _row_title("Trusted devices", f"{_dev_count} device{'s' if _dev_count != 1 else ''} "
                                  "skip the two-factor challenge.")
                    with _dc2:
                        if st.button("Revoke all", key="set_totp_revoke_devices_btn",
                                    disabled=_dev_count == 0):
                            revoke_trusted_devices(_email)
                            st.rerun()

            # Passkeys — Phase 3, UI stub only (mockup frame 14): no WebAuthn/
            # py_webauthn registration or login exists yet. Shown regardless of
            # password/TOTP state (unlike the rows above) since a passkey is its
            # own independent credential, not gated behind having a password.
            with st.container(key="set_row_passkeys"):
                _pkc1, _pkc2 = st.columns([3, 1], vertical_alignment="center")
                with _pkc1:
                    _row_title(
                        'Passkeys<span style="font-size:9.5px;letter-spacing:0.04em;padding:2px 6px;'
                        'border-radius:4px;background:var(--amber-bg);color:var(--amber-txt);margin-left:8px;">'
                        'PHASE 3</span>',
                        "Sign in with Face ID, Touch ID or a security key.")
                with _pkc2:
                    st.button("Manage", key="set_passkeys_manage_btn", disabled=True,
                             help="Not built yet — feature-flagged off until Phase 3.")

        # ── Active sessions ────────────────────────────────────────────────────────
        with st.container(key="set_card_sessions", border=True):
            _row_header("Active sessions")
            _sessions = list_sessions(_email)
            _current_sid = st.session_state.get("jwt_sid")
            for _sess in _sessions:
                with st.container(key=f"set_row_session_{_sess['sid']}"):
                    _sc1, _sc2 = st.columns([3, 1], vertical_alignment="center")
                    with _sc1:
                        _is_current = _sess["sid"] == _current_sid
                        _meta = f"{_device_label(_sess.get('user_agent', ''))} · signed in {_fmt_date(_sess['created_at'])}"
                        _row_title("This browser" if _is_current else _device_label(_sess.get("user_agent", "")), _meta)
                    with _sc2:
                        if _is_current:
                            st.markdown('<div style="text-align:right;font-size:12px;color:var(--faint);">Current</div>',
                                       unsafe_allow_html=True)
                        elif st.button("Sign out", key=f"set_session_signout_{_sess['sid']}"):
                            ok, msg = revoke_session(_email, _sess["sid"])
                            if not ok:
                                st.toast(msg, icon=":material/warning:")
                            st.rerun()
            if len(_sessions) > 1:
                if st.button("Sign out everywhere else", key="set_sessions_revoke_others"):
                    ok, msg = revoke_other_sessions(_email, _current_sid)
                    st.toast(msg)
                    st.rerun()

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

            _style_opts = [s.capitalize() for s in _SCORE_STYLES]
            _cur_style  = str(_shared.get("screen_style", "balanced"))
            _style_sel  = _seg_row(
                "screen_style", "scr_style", "Screening style",
                "Which signals lead the composite score — Value tilts to margin of safety "
                "&amp; quality, Growth to momentum, Income to dividends.",
                _style_opts, _cur_style.capitalize(), disabled=not _is_admin, ratio=(2, 2))

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
                elif _style_sel and _style_sel.lower() != _cur_style:
                    _shared["screen_style"] = _style_sel.lower()
                    save_shared_settings(_shared)
                    _load_all_screener_data.clear()
                    st.rerun()
                elif _stoxx != bool(_shared.get("benchmark_stoxx", False)):
                    _shared["benchmark_stoxx"] = bool(_stoxx)
                    save_shared_settings(_shared)
                    st.rerun()

        # ── Target allocation (per-user, personal reference weights) ────────────────
        _targets = load_targets()
        with st.container(key="set_card_targets", border=True):
            _row_header("Target allocation")
            _row_desc("Your personal reference weights. When any are set, the Risk page's "
                     "rebalancing signals switch from absolute thresholds to drift-vs-target.")

            with st.container(key="set_targets_body"):
                _tc1, _tc2 = st.columns(2, gap="large")
                with _tc1:
                    _row_title("Sector targets",
                              "Blank = no sector targets; the 30% guideline applies instead.")
                    _tgt_sectors_txt = st.text_area(
                        "Sector targets", key="tgt_sectors",
                        value=_targets_to_text(_targets.get("sectors")), height=140,
                        placeholder="One per line — sector and target %:\nTechnology 25\nHealthcare 15",
                        label_visibility="collapsed")
                with _tc2:
                    _row_title("Per-name targets",
                              "Blank = no per-name targets; only the 20% hard cap applies.")
                    _tgt_tickers_txt = st.text_area(
                        "Per-name targets", key="tgt_tickers",
                        value=_targets_to_text(_targets.get("tickers")), height=140,
                        placeholder="One per line — ticker and target %:\nAAA.BR 10\nBBB.PA 7.5",
                        label_visibility="collapsed")

            with st.container(key="set_targets_hhi"):
                _row_title("Concentration ceiling (HHI)",
                          "Flag when portfolio HHI exceeds this. 0 = use the default 0.10 / 0.18 bands.")
                _hhi_max = st.number_input(
                    "Concentration ceiling (HHI)", min_value=0.0, max_value=0.50,
                    value=float(_targets.get("hhi_max") or 0.0), step=0.01, key="tgt_hhi",
                    label_visibility="collapsed")

            with st.container(key="set_targets_save"):
                _save_clicked = st.button("Save target allocation", key="tgt_save", type="secondary")
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
                st.toast("Target allocation saved.")
                st.rerun()

        # ── Data ─────────────────────────────────────────────────────────────────────
        with st.container(key="set_card_data", border=True):
            _row_header("Data")

            # A segmented control, not a select_slider — every other discrete-
            # choice row on this page (Theme, Screening style) already uses
            # one, and unlike a BaseWeb slider it has a genuinely fixed width
            # regardless of which option is selected (was visibly resizing
            # per value before).
            _refresh_opts = [30, 60, 300, 900]
            _refresh_fmt = lambda s: f"{s}s" if s < 60 else f"{s // 60} min"
            _refresh_labels = [_refresh_fmt(s) for s in _refresh_opts]
            _label_to_refresh = dict(zip(_refresh_labels, _refresh_opts))
            _cur_refresh = _s.get("refresh_interval_s", 60)
            _cur_refresh_label = _refresh_fmt(_cur_refresh if _cur_refresh in _refresh_opts else 60)
            _new_refresh_label = _seg_row(
                "refresh", "disp_refresh_interval", "Price refresh interval",
                "How often quotes update during market hours.",
                _refresh_labels, _cur_refresh_label, ratio=(2, 2))
            _new_refresh = _label_to_refresh.get(_new_refresh_label, _cur_refresh)

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
