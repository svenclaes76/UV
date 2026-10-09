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
                      _SCORE_STYLES, ALL_EXCHANGES, EXCHANGE_LABELS)
from uvalu import locale_ui, nav as nav_registry, oauth
from uvalu.compliance import disclosures
from uvalu.components import support_page
from uvalu.dialogs import _dialog, _dialog_width_css
from uvalu.i18n import N_, _, fmt_date, frozen, fmt_num, fmt_pct, h_, ngettext, pgettext, tr
from uvalu.locale_ui import number_field
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
    st.markdown(f'<div>{_a}<div class="uv-card-head uv-set-head"><span>{label}</span>{_c}</div></div>',
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
    _content = support_page(_("Settings"), back_key="settings",
                            subtitle=h_("Choices apply as you make them; sections with typed values have their own Save button."),
                            rail=[(tr(label), f"#{anchor}") for anchor, label in _SECTIONS])
    with _content:
        with st.container(key="set_main"):
            # ── Language & region (docs/i18n-spec.md §7) ────────────────────────────────
            # First card, so the language picker is two clicks away from any page
            # (avatar → Settings) for someone who picked a language they can't read
            # (S-06).
            locale_ui.render_card(_email, anchor="set-language")

            # ── Account: who is signed in, at the top of the account section ────────────
            # (it used to sit at the bottom of the page, with a second Sign out).
            with st.container(key="set_card_profile", border=True):
                st.markdown(
                    # Anchor inside the <div>: a leading <span> made Markdown read
                    # the block as a paragraph and auto-link the email address.
                    f'<div style="display:flex;align-items:center;gap:12px;padding:14px 20px;">'
                    f'<span id="set-account" class="uv-anchor"></span>'
                    f'<div style="width:38px;height:38px;border-radius:8px;background:var(--navy);'
                    f'border:0.5px solid var(--line);display:flex;align-items:center;justify-content:center;'
                    f'font-size:13px;font-weight:600;color:var(--mint);flex:none;">{_initials(_email)}</div>'
                    f'<div style="flex:1;min-width:0;"><div style="font-size:13.5px;font-weight:500;">{_display_name(_email)}</div>'
                    f'<div style="font-size:12px;color:var(--muted);font-family:var(--uv-mono);overflow:hidden;'
                    f'text-overflow:ellipsis;white-space:nowrap;">{_email} · {tr(_u.role.capitalize())}</div></div>'
                    f'<a href="/?logout=1" target="_self" class="uv-set-signout">{h_("Sign out")}</a>'
                    f'</div>', unsafe_allow_html=True)

            # ── Security ─────────────────────────────────────────────────────────────────
            _has_pw = has_password(_email)
            with st.container(key="set_card_security", border=True):
                _row_header(h_("Account security"))
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

                # Linked accounts — one row per known provider (oauth.PROVIDERS), not
                # just the ones this account has linked, so an unconfigured/
                # unlinked provider still shows up dimmed instead of only appearing
                # once someone connects it (mockup: "adding one later changes a
                # state rather than a layout").
                with st.container(key="set_row_linked"):
                    _linked = {oauth.label_for_issuer(i["issuer"]): i for i in list_linked_identities(_email)}
                    # Only providers this workspace offers, or one already linked:
                    # a list of "Not configured · Unavailable" rows was noise.
                    _providers = [p for p in oauth.configured_providers()
                                  if p["configured"] or p["label"] in _linked]
                    _lc1, _lc2 = st.columns([3, 1], vertical_alignment="center")
                    with _lc1:
                        _row_title(h_("Linked accounts"),
                                   h_("Other ways to sign in to this account.") if _providers
                                   else h_("Sign-in with Google or Microsoft is not available in the beta."))
                    for _prov in _providers:
                        _ident = _linked.get(_prov["label"])
                        with st.container(key=f"set_row_linked_{_prov['id']}"):
                            _pc1b, _pc2b = st.columns([3, 1], vertical_alignment="center")
                            with _pc1b:
                                if _ident:
                                    _meta = h_("{email} · linked {date}", email=_ident.get('email_at_link', ''),
                                               date=_fmt_date(_ident.get('linked_at', '')))
                                    _row_title(
                                        f'{_prov["label"]}<span style="font-size:9.5px;letter-spacing:0.04em;'
                                        f'padding:2px 6px;border-radius:4px;background:var(--up-bg);'
                                        f'color:var(--up-txt);margin-left:8px;">{h_("CONNECTED")}</span>', _meta)
                                else:
                                    _row_title(_prov["label"], h_("Available for this workspace."))
                            with _pc2b:
                                if _ident:
                                    if st.button(_("Disconnect"), key=f"set_unlink_{_prov['id']}"):
                                        ok, msg = unlink_identity(_email, _ident["issuer"])
                                        if not ok:
                                            st.toast(msg, icon=":material/warning:")
                                        st.rerun()
                                elif st.button(_("Connect"), key=f"set_link_{_prov['id']}"):
                                    oauth.start_login(_prov["id"])

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
                            _row_title(h_("Backup codes"), ngettext("{count} unused code remaining.",
                                                                   "{count} unused codes remaining.", _remaining))
                        with _bc2:
                            if st.button(_("Regenerate"), key="set_totp_regen_btn"):
                                _dlg_regenerate_backup_codes(_email)

                    with st.container(key="set_row_trusted_devices"):
                        _dc1, _dc2 = st.columns([3, 1], vertical_alignment="center")
                        with _dc1:
                            _dev_count = trusted_device_count(_email)
                            _row_title(h_("Trusted devices"), ngettext("{count} device skips the two-factor challenge.",
                                                                      "{count} devices skip the two-factor challenge.",
                                                                      _dev_count))
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

            # ── Active sessions ────────────────────────────────────────────────────────
            with st.container(key="set_card_sessions", border=True):
                _row_header(h_("Active sessions"))
                _sessions = list_sessions(_email)
                _current_sid = st.session_state.get("jwt_sid")
                for _sess in _sessions:
                    with st.container(key=f"set_row_session_{_sess['sid']}"):
                        _sc1, _sc2 = st.columns([3, 1], vertical_alignment="center")
                        with _sc1:
                            _is_current = _sess["sid"] == _current_sid
                            _meta = h_("{device} · signed in {date}", device=_device_label(_sess.get('user_agent', '')),
                                       date=_fmt_date(_sess['created_at']))
                            _row_title(h_("This browser") if _is_current else _device_label(_sess.get("user_agent", "")), _meta)
                        with _sc2:
                            if _is_current:
                                st.markdown(f'<div style="text-align:right;font-size:12px;color:var(--muted);">{h_("Current")}</div>',
                                           unsafe_allow_html=True)
                            elif st.button(_("Sign out"), key=f"set_session_signout_{_sess['sid']}"):
                                ok, msg = revoke_session(_email, _sess["sid"])
                                if not ok:
                                    st.toast(msg, icon=":material/warning:")
                                st.rerun()
                if len(_sessions) > 1:
                    if st.button(_("Sign out everywhere else"), key="set_sessions_revoke_others"):
                        ok, msg = revoke_other_sessions(_email, _current_sid)
                        st.toast(msg)
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

            # ── Target allocation (per-user, personal reference weights) ────────────────
            _targets = load_targets()
            with st.container(key="set_card_targets", border=True):
                _row_header(h_("Target allocation"), anchor="set-portfolio")
                _row_desc(h_("Reference weights you set yourself. When any are set, the Risk page's observations compare the portfolio with them instead of the model reference levels."))

                with st.container(key="set_targets_body"):
                    _tc1, _tc2 = st.columns(2, gap="large")
                    with _tc1:
                        _row_title(h_("Sector targets"),
                                  h_("Blank = no sector targets; the 30% guideline applies instead."))
                        _tgt_sectors_txt = st.text_area(
                            _("Sector targets"), key="tgt_sectors",
                            value=_targets_to_text(_targets.get("sectors")), height=140,
                            placeholder=_("One per line — sector and target %:\nTechnology 25\nHealthcare 15"),
                            label_visibility="collapsed")
                    with _tc2:
                        _row_title(h_("Per-name targets"),
                                  h_("Blank = no per-name targets; only the 20% hard cap applies."))
                        _tgt_tickers_txt = st.text_area(
                            _("Per-name targets"), key="tgt_tickers",
                            value=_targets_to_text(_targets.get("tickers")), height=140,
                            placeholder=_("One per line — ticker and target %:\nAAA.BR 10\nBBB.PA 7.5"),
                            label_visibility="collapsed")

                with st.container(key="set_targets_hhi"):
                    # Empty = the default bands (it used to be a magic 0).
                    _row_title(h_("Concentration ceiling (HHI)"),
                              h_("Flag when the portfolio's HHI exceeds this. Leave empty for the default bands."))
                    _hhi_max = number_field(
                        _("Concentration ceiling (HHI)"), min_value=0.0, max_value=0.50,
                        value=float(_targets["hhi_max"]) if _targets.get("hhi_max") else None, step=0.01,
                        key="tgt_hhi", label_visibility="collapsed",
                        placeholder=_("Default ({low} / {high})", low=fmt_num(0.10, 2), high=fmt_num(0.18, 2)))

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

            # ── Dividend withholding (per-user — depends on tax residency/treaty) ────────
            with st.container(key="set_card_dividend_tax", border=True):
                _row_header(h_("Dividend withholding"), anchor="set-withholding")
                _row_desc(h_("Default withholding tax % applied when you record a dividend on each exchange — always editable per record. Depends on your own tax residency and treaty, which this app has no way to know, so every rate starts at 0% until you set it."))
                _wh = dict(_s.get("dividend_withholding") or {})
                _wh_new: dict[str, float] = {}
                with st.container(key="set_dividend_wh_grid"):
                    for _i in range(0, len(ALL_EXCHANGES), 3):
                        _wh_cols = st.columns(3, gap="large")
                        for _col, _ex in zip(_wh_cols, ALL_EXCHANGES[_i:_i + 3]):
                            with _col:
                                _wh_val = number_field(
                                    f"{EXCHANGE_LABELS.get(_ex, _ex.title())} (%)", min_value=0.0, max_value=100.0,
                                    step=0.5, value=float(_wh.get(_ex, 0.0)), format="%.1f",
                                    key=f"disp_wh_{_ex}")
                                _wh_new[_ex] = float(_wh.get(_ex, 0.0)) if _wh_val is None else _wh_val
                # Typed values: saved with the button, not on every keystroke/blur
                # (a half-typed rate shouldn't apply).
                with st.container(key="set_wh_save"):
                    if st.button(_("Save withholding rates"), key="wh_save"):
                        _s["dividend_withholding"] = _wh_new
                        save_settings(_s, _email)
                        st.toast(_("Withholding rates saved."))
                        st.rerun()

            # ── Import / Export (per-user, not admin-scoped) ─────────────────────────────
            with st.container(key="set_card_import", border=True):
                _row_header(h_("Import & export"), anchor="set-import")

                with st.container(key="set_import_row"):
                    _imp_col, _exp_col = st.columns(2, gap="large")
                    with _imp_col:
                        with st.container(key="set_import_body"):
                            _row_title(h_("Import portfolio"),
                                      h_("Upload an Excel file to import positions, sold history and dividends. This replaces all existing portfolio data for this account."))
                        # A new key after an import or cancel empties the uploader —
                        # the old one kept its file, so the page re-imported it on
                        # every rerun after a successful import.
                        _imp_n = st.session_state.get("imp_portfolio_n", 0)
                        _imp_key = "imp_portfolio" if not _imp_n else f"imp_portfolio_{_imp_n}"
                        _imp_file = st.file_uploader(_("Choose your portfolio .xlsx file"), type=["xlsx"], key=_imp_key,
                                                     label_visibility="collapsed")
                        if _imp_file:
                            try:
                                with st.spinner(_("Parsing Excel…")):
                                    _imp_pf, _imp_sold, _imp_div = parse_excel(_imp_file)
                            except Exception as e:
                                st.error(_("Could not parse file: {error}", error=e))
                                st.code(traceback.format_exc())
                            else:
                                if _imp_pf.empty:
                                    st.error(_("No open EBR:/AMS:/EPA:/BIT:/ETR:/SWX: positions found. Check that your file matches the expected format."))
                                else:
                                    # Destructive: say what the file holds and that the
                                    # current data goes, and wait for an explicit yes.
                                    with st.container(key="set_import_confirm"):
                                        st.markdown(
                                            f'<div style="font-size:12.5px;line-height:1.5;color:var(--text);">'
                                            + h_("Replace all portfolio data with this file? It holds {open} open positions, "
                                                 "{sold} sold positions and {dividends} dividend records. Your current "
                                                 "positions, sales and dividends are deleted.",
                                                 open=len(_imp_pf), sold=len(_imp_sold), dividends=len(_imp_div))
                                            + "</div>", unsafe_allow_html=True)
                                        with st.container(horizontal=True, gap="small"):
                                            _imp_yes = st.button(_("Replace my portfolio data"), key="imp_confirm")
                                            _imp_no = st.button(_("Cancel"), key="imp_cancel", type="tertiary")
                                    if _imp_yes:
                                        _udir = user_data_dir(_email)
                                        (_udir / "portfolio.json").unlink(missing_ok=True)
                                        (_udir / "sold.json").unlink(missing_ok=True)
                                        (_udir / "dividends_history.json").unlink(missing_ok=True)
                                        save_portfolio(_imp_pf)
                                        save_sold(_imp_sold)
                                        save_div_hist(_imp_div)
                                        st.toast(_("Imported {open} open, {sold} sold, {dividends} dividend records.",
                                                   open=len(_imp_pf), sold=len(_imp_sold), dividends=len(_imp_div)))
                                    if _imp_yes or _imp_no:
                                        st.session_state["imp_portfolio_n"] = _imp_n + 1
                                        st.rerun()

                    with _exp_col:
                        with st.container(key="set_export_body"):
                            _row_title(h_("Excel export"),
                                      h_("Human-readable workbook with positions, dividends, sold history and watchlist. Useful for inspection or migration."))
                        try:
                            xls_bytes = export_excel()
                            st.download_button(
                                _("Download backup.xlsx"),
                                data=xls_bytes,
                                file_name=backup_filename("xlsx"),
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            )
                        except ValueError:
                            st.info(_("Your portfolio is empty. Add positions in the Portfolio section first, then come back to export."))
                        except Exception as e:
                            st.error(_("Could not create Excel: {error}", error=e))

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
                _row_header(h_("Model settings & quality screens"), anchor="set-model",
                            chip=h_("Affects all users · logged"))
                _row_desc(h_("Shared model settings: they set every model signal across the app, the same for every user, and are published on the Methodology page. Each change is recorded.")
                         + ("" if _is_admin else " " + h_("Admin-only — sign in as an Admin to change these.")))

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


            # ── Legal (L13) ─────────────────────────────────────────────────────────────
            with st.container(key="set_card_legal", border=True):
                _row_header(h_("Legal"), anchor="set-legal")
                _legal_page = nav_registry.pages.get("legal")
                with st.container(key="set_legal_links"):
                    if _legal_page is not None:
                        for _lkey, _ltitle, _lfile in disclosures.LEGAL_DOCS:
                            st.page_link(_legal_page, label=tr(_ltitle), query_params={"doc": _lkey})
                _row_desc(h_("To get a copy of your data or have it deleted, write to {email}.",
                             email=disclosures.PRODUCER_PRIVACY_CONTACT))
