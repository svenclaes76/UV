"""Translations (gettext) and locale formatting (Babel/CLDR) — docs/i18n-spec.md.

Every page imports its UI text and number/date formatting from here; nothing
else calls gettext or Babel directly (spec §9).

Two independent settings drive this module (spec §3):

* **Interface language** (``en``, ``nl``, …) picks the ``.po``/``.mo`` catalog
  that ``_()``/``ngettext()``/``pgettext()`` read.
* **Region format** (``nl-BE``, ``de-CH``, …) drives every ``fmt_*`` helper and
  ``parse_num()``. The language never affects formatting.

``activate()`` resolves both once per script run (spec §6) and stores the
result in session state; every other function reads it from there, falling
back to the config defaults outside a Streamlit session (background threads,
unit tests).

Text built where no user language is known — the risk report, which is
assembled in a background thread and cached — uses ``lazy_()``: it returns a
``Msg`` (a ``str`` holding the English text) that re-translates itself when a
page passes it through ``tr()``.
"""
from __future__ import annotations

import copy
import datetime as _dt
import gettext as _gettext
import html as _html
import io
import json
import math
import os
import re
import threading
import unicodedata
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import streamlit as st
from babel import Locale, UnknownLocaleError
from babel import dates as _bdates
from babel import numbers as _bnum

from uvalu import logkit

_REPO_ROOT = Path(__file__).resolve().parent.parent
LOCALES_DIR = _REPO_ROOT / "locales"
CONFIG_PATH = _REPO_ROOT / "i18n.config.json"

MISSING = "—"   # shown for None/NaN everywhere, as before
DATE_FORMATS = ("short", "medium", "iso")
WEEK_STARTS = ("monday", "sunday")

_log = logkit.get_logger("uvalu.i18n")


# ── Config (spec §7.3) ────────────────────────────────────────────────────────

class I18nConfigError(ValueError):
    """Invalid ``i18n`` config — names the offending key (spec C-02)."""


@dataclass(frozen=True)
class I18nConfig:
    default_language: str = "en"
    enabled_languages: tuple[str, ...] = ("en", "nl", "fr", "de", "it", "es")
    default_region: str = "en-GB"
    enabled_regions: tuple[str, ...] = (
        "en-GB", "en-IE", "en-US", "nl-BE", "nl-NL", "fr-BE", "fr-FR", "fr-LU", "fr-CH",
        "de-DE", "de-BE", "de-AT", "de-LU", "de-CH", "it-IT", "it-CH", "es-ES")
    default_display_currency: str = "EUR"
    display_currency_by_region: dict = field(
        default_factory=lambda: {"de-CH": "CHF", "fr-CH": "CHF", "it-CH": "CHF"})
    enabled_display_currencies: tuple[str, ...] = ("EUR", "USD", "GBP", "CHF")
    default_time_zone: str = "Europe/Brussels"
    time_zone_by_region: dict = field(
        default_factory=lambda: {"de-CH": "Europe/Zurich", "fr-CH": "Europe/Zurich", "it-CH": "Europe/Zurich"})
    allow_url_lang_param: bool = True
    log_missing_translations: bool = True

    def default_region_for(self, lang: str) -> str:
        """A language's default region = its first entry in enabled_regions
        (en-GB, nl-BE, fr-BE, de-DE, it-IT, es-ES with the shipped config), so
        a seventh language needs only a config entry, no code (spec N-05)."""
        for r in self.enabled_regions:
            if r.split("-")[0] == lang:
                return r
        return self.default_region

    def currency_for(self, region: str) -> str:
        return self.display_currency_by_region.get(region, self.default_display_currency)

    def time_zone_for(self, region: str) -> str:
        return self.time_zone_by_region.get(region, self.default_time_zone)


def _require(cond: bool, key: str, problem: str) -> None:
    if not cond:
        raise I18nConfigError(f"i18n config ({CONFIG_PATH.name}): '{key}' {problem}")


def _is_region(tag: str) -> bool:
    try:
        loc = Locale.parse(tag, sep="-")
    except (UnknownLocaleError, ValueError, TypeError):
        return False
    return bool(loc.territory)


def validate_config(raw: dict) -> I18nConfig:
    """Build an I18nConfig from the ``i18n`` block, raising I18nConfigError
    that names the key for anything invalid (spec C-02)."""
    _require(isinstance(raw, dict), "i18n", "must be an object")
    defaults = I18nConfig()
    known = set(I18nConfig.__dataclass_fields__)
    for k in raw:
        _require(k in known, k, "is not a known setting")
    vals = {k: raw.get(k, getattr(defaults, k)) for k in known}

    langs = vals["enabled_languages"]
    _require(isinstance(langs, (list, tuple)) and langs, "enabled_languages", "must be a non-empty list")
    for lang in langs:
        _require(isinstance(lang, str) and (lang == "en" or (LOCALES_DIR / lang / "LC_MESSAGES" / "messages.po").exists()),
                 "enabled_languages", f"lists '{lang}', which has no locales/{lang}/LC_MESSAGES/messages.po")
    _require(vals["default_language"] in langs, "default_language",
             f"'{vals['default_language']}' is not in enabled_languages")

    regions = vals["enabled_regions"]
    _require(isinstance(regions, (list, tuple)) and regions, "enabled_regions", "must be a non-empty list")
    for r in regions:
        _require(isinstance(r, str) and _is_region(r), "enabled_regions",
                 f"lists '{r}', which is not a language-TERRITORY locale such as nl-BE")
    _require(vals["default_region"] in regions, "default_region",
             f"'{vals['default_region']}' is not in enabled_regions")

    currencies = vals["enabled_display_currencies"]
    _require(isinstance(currencies, (list, tuple)) and currencies, "enabled_display_currencies",
             "must be a non-empty list")
    known_ccy = _bnum.list_currencies()
    for c in currencies:
        _require(c in known_ccy, "enabled_display_currencies", f"lists unknown currency '{c}'")
    _require(vals["default_display_currency"] in currencies, "default_display_currency",
             f"'{vals['default_display_currency']}' is not in enabled_display_currencies")
    by_region = vals["display_currency_by_region"]
    _require(isinstance(by_region, dict), "display_currency_by_region", "must be an object")
    for r, c in by_region.items():
        _require(r in regions, "display_currency_by_region", f"has region '{r}' that is not in enabled_regions")
        _require(c in currencies, "display_currency_by_region", f"maps '{r}' to '{c}', not in enabled_display_currencies")

    try:
        ZoneInfo(str(vals["default_time_zone"]))
    except (ZoneInfoNotFoundError, ValueError):
        _require(False, "default_time_zone", f"'{vals['default_time_zone']}' is not an IANA time zone")
    tz_by_region = vals["time_zone_by_region"]
    _require(isinstance(tz_by_region, dict), "time_zone_by_region", "must be an object")
    for r, tz in tz_by_region.items():
        _require(r in regions, "time_zone_by_region", f"has region '{r}' that is not in enabled_regions")
        try:
            ZoneInfo(str(tz))
        except (ZoneInfoNotFoundError, ValueError):
            _require(False, "time_zone_by_region", f"maps '{r}' to '{tz}', which is not an IANA time zone")
    for k in ("allow_url_lang_param", "log_missing_translations"):
        _require(isinstance(vals[k], bool), k, "must be true or false")

    return I18nConfig(
        default_language=vals["default_language"], enabled_languages=tuple(langs),
        default_region=vals["default_region"], enabled_regions=tuple(regions),
        default_display_currency=vals["default_display_currency"],
        display_currency_by_region=dict(by_region),
        enabled_display_currencies=tuple(currencies),
        default_time_zone=str(vals["default_time_zone"]),
        time_zone_by_region={r: str(tz) for r, tz in tz_by_region.items()},
        allow_url_lang_param=vals["allow_url_lang_param"],
        log_missing_translations=vals["log_missing_translations"],
    )


@lru_cache(maxsize=1)
def config() -> I18nConfig:
    """The validated config, read once per process — changes apply on restart
    (spec C-03). A missing file means the shipped defaults."""
    if not CONFIG_PATH.exists():
        return I18nConfig()
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise I18nConfigError(f"i18n config ({CONFIG_PATH.name}): not valid JSON: {e}") from e
    _require(isinstance(raw, dict) and "i18n" in raw, "i18n", "block is missing")
    return validate_config(raw["i18n"])


# ── Active context (spec §6) ──────────────────────────────────────────────────

@dataclass(frozen=True)
class Ctx:
    lang: str
    region: str
    currency: str
    date_format: str
    time_zone: str
    week_start: str

    @property
    def locale(self) -> Locale:
        return _locale(self.region)


_SS_CTX = "_uv_i18n"
_SS_LANG_CHOICE = "_uv_lang_choice"   # sign-in switcher / ?lang= (session only)
_SS_NOTICE = "_uv_i18n_notice"
_SS_MISSING = "_uv_i18n_missing"

# Profile keys (settings.py _USER_DEFAULTS). None = not chosen yet → detect.
PROFILE_KEYS = ("language", "region", "display_currency", "date_format", "time_zone", "week_start")
REGION_SAME_AS_LANGUAGE = "same"


@lru_cache(maxsize=64)
def _locale(tag: str) -> Locale:
    return Locale.parse(tag, sep="-")


def _default_ctx() -> Ctx:
    cfg = config()
    return Ctx(cfg.default_language, cfg.default_region, cfg.currency_for(cfg.default_region),
               "short", cfg.time_zone_for(cfg.default_region), _week_start_for(cfg.default_region))


def current() -> Ctx:
    """The context activate() resolved for this run, or the config defaults
    (en / en-GB while a Msg renders its stored English text)."""
    pinned = _using.pinned()
    if pinned is not None:
        return pinned
    if not _in_script_run():
        return _default_ctx()
    try:
        ctx = st.session_state.get(_SS_CTX)
    except Exception:
        ctx = None
    return ctx if isinstance(ctx, Ctx) else _default_ctx()


def _in_script_run() -> bool:
    """True inside a Streamlit script run (not a background thread / bare test)."""
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        return get_script_run_ctx(suppress_warning=True) is not None
    except Exception:
        return False


def _week_start_for(region: str) -> str:
    return "sunday" if _locale(region).first_week_day == 6 else "monday"


def _parse_accept_language(header: str) -> list[str]:
    """Browser tags, best first: 'nl-BE,nl;q=0.9,en;q=0.8' → ['nl-BE','nl','en']."""
    out = []
    for i, part in enumerate((header or "").split(",")):
        tag, _sep, params = part.strip().partition(";")
        q = 1.0
        m = re.search(r"q=([0-9.]+)", params)
        if m:
            try:
                q = float(m.group(1))
            except ValueError:
                q = 0.0
        if tag and tag != "*" and q > 0:
            out.append((-q, i, tag.replace("_", "-")))
    return [t for _q, _i, t in sorted(out)]


def _browser_tags() -> list[str]:
    try:
        tags = _parse_accept_language(st.context.headers.get("Accept-Language", ""))
    except Exception:
        tags = []
    if not tags:
        try:
            loc = getattr(st.context, "locale", None)
            if loc:
                tags = [str(loc)]
        except Exception:
            pass
    return tags


def _canonical_region(tag: str) -> str | None:
    """'fr-be' → 'fr-BE' if enabled, else None."""
    lang, _sep, terr = tag.partition("-")
    cand = f"{lang.lower()}-{terr.upper()}"
    return cand if cand in config().enabled_regions else None


def _browser_region(tags: list[str], lang: str) -> str | None:
    """Spec §6 region step 2, over every Accept-Language tag (browsers often
    send the bare language first: "nl, nl-BE"). Best first: a supported tag
    in the chosen language; then that language in a country the browser
    lists (fr + de-CH → fr-CH); then any supported tag."""
    canon = [r for r in (_canonical_region(t) for t in tags if "-" in t) if r]
    same_lang = [r for r in canon if r.split("-")[0] == lang]
    if same_lang:
        return same_lang[0]
    for t in tags:
        _lang, _sep, terr = t.partition("-")
        cand = _canonical_region(f"{lang}-{terr}") if terr else None
        if cand:
            return cand
    return canon[0] if canon else None


def resolve(profile: dict | None, *, session_lang: str | None, browser_tags: list[str]) -> tuple[Ctx, str | None]:
    """Pure resolution (spec §6) → (ctx, disabled_language_or_None).

    The second value is the profile language that config no longer enables
    (spec C-01), so the caller can show the one-time notice and clear it."""
    cfg = config()
    profile = profile or {}
    dropped = None

    lang = None
    p_lang = profile.get("language")
    if p_lang:
        if p_lang in cfg.enabled_languages:
            lang = p_lang
        else:
            dropped = p_lang
    if lang is None and not dropped and session_lang in cfg.enabled_languages:
        lang = session_lang
    if lang is None and not dropped:
        for tag in browser_tags:
            base = tag.split("-")[0].lower()
            if base in cfg.enabled_languages:
                lang = base
                break
    lang = lang or cfg.default_language

    region = None
    p_region = profile.get("region")
    if p_region == REGION_SAME_AS_LANGUAGE:
        region = cfg.default_region_for(lang)
    elif p_region in cfg.enabled_regions:
        region = p_region
    if region is None and browser_tags:
        region = _browser_region(browser_tags, lang)
    region = region or cfg.default_region_for(lang)

    currency = profile.get("display_currency")
    if currency not in cfg.enabled_display_currencies:
        currency = cfg.currency_for(region)
    date_format = profile.get("date_format")
    if date_format not in DATE_FORMATS:
        date_format = "short"
    tz = profile.get("time_zone") or cfg.time_zone_for(region)
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        tz = cfg.time_zone_for(region)
    week = profile.get("week_start")
    if week not in WEEK_STARTS:
        week = _week_start_for(region)
    return Ctx(lang, region, currency, date_format, tz, week), dropped


def activate(email: str = "") -> Ctx:
    """Resolve language + region for this run and store them (call once per
    run from app.py, before anything renders text)."""
    import settings as _settings   # late: settings imports crypto/.env

    ss = st.session_state
    cfg = config()
    if cfg.allow_url_lang_param:
        q = st.query_params.get("lang")
        if q and q.lower() in cfg.enabled_languages:
            ss[_SS_LANG_CHOICE] = q.lower()   # session only, never saved (spec §6 step 2)

    profile = {}
    if email:
        try:
            profile = _settings.load_settings(email)
        except Exception:
            profile = {}
    ctx, dropped = resolve(profile, session_lang=ss.get(_SS_LANG_CHOICE), browser_tags=_browser_tags())

    if email:
        changed = dict(profile)
        if dropped:
            # C-01: fall back, tell the user once, forget the retired language.
            ss[_SS_NOTICE] = (dropped, ctx.lang)
            changed["language"] = None
        elif not profile.get("language") and ss.get("_uv_lang_from_switcher"):
            # S-04: a pre-sign-in switcher choice becomes the profile default.
            changed["language"] = ss.get(_SS_LANG_CHOICE)
        # D-03: a corrupt saved value silently resets to the default.
        for key, ok in (("region", lambda v: v in cfg.enabled_regions or v == REGION_SAME_AS_LANGUAGE),
                        ("display_currency", lambda v: v in cfg.enabled_display_currencies),
                        ("date_format", lambda v: v in DATE_FORMATS),
                        ("week_start", lambda v: v in WEEK_STARTS),
                        ("time_zone", _valid_tz)):
            if profile.get(key) is not None and not ok(profile.get(key)):
                changed[key] = None
        if changed != profile:
            try:
                _settings.save_settings(changed, email)
            except Exception:
                _log.warning("could not save locale profile fix-up", exc_info=True,
                             extra={"event": "i18n.profile_save_failed"})
    ss[_SS_CTX] = ctx
    return ctx


def _valid_tz(v) -> bool:
    try:
        ZoneInfo(str(v))
        return True
    except (ZoneInfoNotFoundError, ValueError):
        return False


def pop_notice() -> str | None:
    """The one-time 'language no longer available' message (C-01), if any."""
    if not _in_script_run():
        return None
    try:
        pair = st.session_state.pop(_SS_NOTICE, None)
    except Exception:
        return None
    if not pair:
        return None
    old, new = pair
    return _("{language} is no longer available. Current language: {fallback}.",
             language=language_name(old, in_lang=new), fallback=language_name(new))


def set_session_language(lang: str) -> None:
    """Pre-sign-in switcher (S-04): session only until sign-in saves it."""
    st.session_state[_SS_LANG_CHOICE] = lang
    st.session_state["_uv_lang_from_switcher"] = True


# ── Catalogs (spec T-01, D-01, D-02) ──────────────────────────────────────────

def _drafts_enabled() -> bool:
    """UVALU_I18N_DRAFTS=1 shows unreviewed (fuzzy) drafts — for screenshot
    passes before review. Never in production (spec W-04)."""
    return (os.environ.get("UVALU_I18N_DRAFTS") == "1"
            and os.environ.get("UVALU_ENV", "development") != "production")


def _pseudo_enabled() -> bool:
    """UVALU_I18N_PSEUDO=1 renders every translated text as ~35%-longer
    pseudo text (spec §12) to spot hard-coded English and clipping."""
    return (os.environ.get("UVALU_I18N_PSEUDO") == "1"
            and os.environ.get("UVALU_ENV", "development") != "production")


@dataclass(frozen=True)
class _Catalog:
    messages: dict          # msgid | (msgid, idx) | "ctx\x04msgid" → str
    plural: object          # n → index


def _english_plural(n) -> int:
    return 0 if n == 1 else 1


@st.cache_resource(show_spinner=False)
def _load_catalog(lang: str, drafts: bool) -> _Catalog:
    po = LOCALES_DIR / lang / "LC_MESSAGES" / "messages.po"
    mo = po.with_suffix(".mo")
    data = None
    if drafts and po.exists():
        from babel.messages.mofile import write_mo
        from babel.messages.pofile import read_po
        with po.open("rb") as fh:
            cat = read_po(fh, locale=lang)
        buf = io.BytesIO()
        write_mo(buf, cat, use_fuzzy=True)
        data = buf.getvalue()
    elif mo.exists():
        data = mo.read_bytes()
    if not data:
        return _Catalog({}, _english_plural)
    try:
        t = _gettext.GNUTranslations(io.BytesIO(data))
    except Exception:
        _log.warning("unreadable translation catalog", exc_info=True,
                     extra={"event": "i18n.catalog_unreadable", "language": lang})
        return _Catalog({}, _english_plural)
    msgs = {k: v for k, v in t._catalog.items() if k != ""}   # noqa: SLF001 — gettext has no public dict
    return _Catalog(msgs, getattr(t, "plural", _english_plural))


@st.cache_resource(show_spinner=False)
def _template_ids() -> frozenset:
    """Keys in messages.pot — tells 'not reviewed yet' from 'truly missing'."""
    pot = LOCALES_DIR / "messages.pot"
    if not pot.exists():
        return frozenset()
    from babel.messages.pofile import read_po
    with pot.open("rb") as fh:
        cat = read_po(fh)
    keys = set()
    for m in cat:
        if not m.id:
            continue
        mid = m.id[0] if isinstance(m.id, (list, tuple)) else m.id
        keys.add(f"{m.context}\x04{mid}" if m.context else mid)
    return frozenset(keys)


def _catalog(lang: str) -> _Catalog:
    return _load_catalog(lang, _drafts_enabled())


def _note_missing(lang: str, key: str) -> None:
    """D-02: log each missing translation once per session. Entries that
    exist but await review are summarised once per language instead of one
    warning per string."""
    if lang == "en" or not config().log_missing_translations or not _in_script_run():
        return
    try:
        seen = st.session_state.setdefault(_SS_MISSING, set())
    except Exception:
        return
    if key in _template_ids():
        tag = ("unreviewed", lang)
        if tag not in seen:
            seen.add(tag)
            _log.info("unreviewed translations shown in English",
                      extra={"event": "i18n.unreviewed", "language": lang})
        return
    if (lang, key) in seen:
        return
    seen.add((lang, key))
    _log.warning("missing translation", extra={"event": "i18n.missing", "language": lang,
                                                "msgid": key.split("\x04")[-1][:200]})


def _lookup(key, lang: str, *, quiet: bool = False) -> str | None:
    s = _catalog(lang).messages.get(key)
    if s is None and lang != "en":
        if not quiet:
            _note_missing(lang, key if isinstance(key, str) else key[0])
        s = _catalog("en").messages.get(key)   # D-01: corrected English, then the msgid
    return s


_PSEUDO = str.maketrans("aceinouyACEINOUY", "àçéîñöüýÅÇÉÎÑÖÜÝ")


def _pseudo(s: str) -> str:
    parts = re.split(r"(\{\w+\}|<[^>]+>|\*\*)", s)
    body = "".join(p if (p.startswith("{") or p.startswith("<") or p == "**") else p.translate(_PSEUDO)
                   for p in parts)
    return f"[{body} {'~' * max(1, len(s) // 3)}]"


_PCT_IN_TEXT = re.compile(r"(?<=[\d}])[   ]?%")


@lru_cache(maxsize=64)
def _percent_sep(region: str) -> str | None:
    """What the region's CLDR percent format puts between number and "%":
    '' (en, de-CH, it), NBSP (de-DE, es), narrow NBSP (fr); None when the
    sign isn't a suffix."""
    suffix = _locale(region).percent_formats[None].suffix[0]
    return suffix[:-1] if suffix.endswith("%") else None


def _percent_spacing(text: str) -> str:
    """Make "30 %" / "{pct}%" in a translated text follow the region's percent
    format, so literal percentages match fmt_pct() values on the same screen
    (German translations write "30 %", which de-CH formats as "30%")."""
    if "%" not in text:
        return text
    sep = _percent_sep(current().region)
    return text if sep is None else _PCT_IN_TEXT.sub(sep + "%", text)


def _format(text: str, fallback: str, kw: dict) -> str:
    text, fallback = _percent_spacing(text), _percent_spacing(fallback)
    if _pseudo_enabled():
        text = _pseudo(text)
    if not kw:
        return text
    try:
        return text.format(**kw)
    except (KeyError, IndexError, ValueError):
        # A broken placeholder in a translation must never crash a page.
        _log.warning("translation placeholder mismatch", extra={"event": "i18n.bad_placeholder",
                                                                 "msgid": fallback[:200]})
        return fallback.format(**kw)


def _render_kw(kw: dict) -> dict:
    return {k: (v.translate() if isinstance(v, Msg) else v.render() if isinstance(v, Fmt) else v)
            for k, v in kw.items()}


def _(msgid: str, **kw) -> str:
    """Translate ``msgid``; ``kw`` fills its ``{placeholders}`` (pass values
    already formatted with the fmt_* helpers)."""
    lang = current().lang
    s = _lookup(msgid, lang) if lang != "en" or _catalog("en").messages else None
    return _format(s or msgid, msgid, _render_kw(kw))


def h_(msgid: str, **kw) -> str:
    """_() for HTML strings: escapes the translated text (so '&' or '<' in a
    translation can't break markup) but not the placeholder values, which
    callers may pass as ready-made markup such as a <span>."""
    lang = current().lang
    s = _lookup(msgid, lang) if lang != "en" or _catalog("en").messages else None
    text = _percent_spacing(s or msgid)
    if _pseudo_enabled():
        text = _pseudo(text)
    text = _html.escape(text, quote=False)
    if not kw:
        return text
    try:
        return text.format(**_render_kw(kw))
    except (KeyError, IndexError, ValueError):
        return _html.escape(_percent_spacing(msgid), quote=False).format(**_render_kw(kw))


def pgettext(context: str, msgid: str, **kw) -> str:
    """Translate ``msgid`` in a message context ("button", "style",
    "date_format") — for one English word that needs two translations."""
    lang = current().lang
    s = _lookup(f"{context}\x04{msgid}", lang)
    return _format(s or msgid, msgid, _render_kw(kw))


def ngettext(singular: str, plural: str, n, **kw) -> str:
    """Plural-aware translation (spec L-04). ``{count}`` is filled with the
    locale-formatted ``n`` unless given explicitly."""
    lang = current().lang
    kw.setdefault("count", fmt_num(n, 0))
    cat = _catalog(lang)
    n_int = int(n) if n is not None and not (isinstance(n, float) and math.isnan(n)) else 0
    s = cat.messages.get((singular, cat.plural(n_int)))
    if s is None:
        if lang != "en":
            _note_missing(lang, singular)
        en = _catalog("en")
        s = en.messages.get((singular, _english_plural(n_int)))
    fallback = singular if n_int == 1 else plural
    return _format(s or fallback, fallback, _render_kw(kw))


def lowercase_noun(word: str) -> str:
    """A translated word used mid-sentence: lower-cased, except in German,
    which capitalises nouns."""
    return word if current().lang == "de" else word.lower()


def N_(msgid: str) -> str:
    """Mark a string for extraction without translating it now (constants
    defined at import time); translate it with tr() / _() at display."""
    return msgid


def tr(value) -> str:
    """Display-time translation of a value that may be a Msg (re-rendered in
    the active language), a marked data value such as a sector name or
    dividend frequency (looked up quietly — unknown values pass through), or
    anything else (str()'d)."""
    if value is None:
        return MISSING
    if isinstance(value, Msg):
        return value.translate()
    if isinstance(value, str):
        if not value:
            return value
        lang = current().lang
        s = _lookup(value, lang, quiet=True)
        s = _percent_spacing(s) if s else value   # unknown data values pass through untouched
        return _pseudo(s) if _pseudo_enabled() else s
    return str(value)


# ── Deferred messages (text built outside a request) ─────────────────────────

class Fmt:
    """A number/date placeholder rendered in the active region at display
    time: Fmt("pct", 12.5, decimals=1, signed=True)."""
    __slots__ = ("kind", "value", "opts")

    def __init__(self, kind: str, value, **opts):
        self.kind, self.value, self.opts = kind, value, opts

    def render(self) -> str:
        fn = {"num": fmt_num, "pct": fmt_pct, "money": fmt_money,
              "compact": fmt_compact, "date": fmt_date,
              "tr": lambda v, **_o: tr(v)}[self.kind]
        return fn(self.value, **self.opts)

    def __reduce__(self):
        return (_rebuild_fmt, (self.kind, self.value, self.opts))

    def __eq__(self, other):
        return isinstance(other, Fmt) and (self.kind, self.value, self.opts) == (other.kind, other.value, other.opts)

    def __hash__(self):
        return hash((self.kind, repr(self.value)))

    def __repr__(self):
        return f"Fmt({self.kind!r}, {self.value!r}, **{self.opts!r})"


def _rebuild_fmt(kind, value, opts):
    return Fmt(kind, value, **opts)


class Msg(str):
    """A str whose value is the English text, plus what's needed to
    re-translate it later (msgid, context, plural, placeholder values)."""
    __slots__ = ("msgid", "plural", "n", "context", "kw")

    def __new__(cls, msgid: str, *, plural: str | None = None, n=None, context: str | None = None, **kw):
        with _using(None):
            english = cls._render(msgid, plural, n, context, kw)
        obj = super().__new__(cls, english)
        obj.msgid, obj.plural, obj.n, obj.context, obj.kw = msgid, plural, n, context, kw
        return obj

    @staticmethod
    def _render(msgid, plural, n, context, kw):
        if plural is not None:
            return ngettext(msgid, plural, n, **kw)
        if context is not None:
            return pgettext(context, msgid, **kw)
        return _(msgid, **kw)

    def translate(self) -> str:
        return self._render(self.msgid, self.plural, self.n, self.context, self.kw)

    def __reduce__(self):
        return (_rebuild_msg, (self.msgid, self.plural, self.n, self.context, self.kw))


def _rebuild_msg(msgid, plural, n, context, kw):
    return Msg(msgid, plural=plural, n=n, context=context, **kw)


def english():
    """Context manager: _() and fmt_* render en / en-GB inside it."""
    return _using(None)


def lazy_(msgid: str, **kw) -> Msg:
    """Deferred _(): English now, translated by tr() at display."""
    return Msg(msgid, **kw)


def lazy_ngettext(singular: str, plural: str, n, **kw) -> Msg:
    return Msg(singular, plural=plural, n=n, **kw)


def lazy_pgettext(context: str, msgid: str, **kw) -> Msg:
    return Msg(msgid, context=context, **kw)


class _using:
    """Pin the language/region for the calling thread (a stack, so nested
    uses restore correctly). english() pins en / en-GB for Msg's stored
    English text and for text written to data files (ledger notes)."""
    _local = threading.local()

    def __init__(self, ctx: "Ctx | None" = None):
        self.ctx = ctx

    def __enter__(self):
        stack = getattr(self._local, "stack", None)
        if stack is None:
            stack = self._local.stack = []
        stack.append(self.ctx or _english_ctx())
        return self

    def __exit__(self, *exc):
        self._local.stack.pop()

    @classmethod
    def pinned(cls) -> "Ctx | None":
        stack = getattr(cls._local, "stack", None)
        return stack[-1] if stack else None


def using(ctx: Ctx):
    """Context manager: render in ``ctx``'s language and region."""
    return _using(ctx)


def frozen(fn):
    """``fn`` bound to the language/region active now — for widget
    format_funcs, which Streamlit (and AppTest) may call outside the script
    run that created the widget."""
    ctx = current()

    def call(*args, **kwargs):
        with _using(ctx):
            return fn(*args, **kwargs)
    return call


@lru_cache(maxsize=1)
def _english_ctx() -> Ctx:
    cfg = config()
    return Ctx("en", "en-GB", cfg.default_display_currency, "short", cfg.default_time_zone, "monday")


# ── Formatting (spec §5) ─────────────────────────────────────────────────────

def _is_missing(v) -> bool:
    if v is None:
        return True
    try:
        return bool(math.isnan(v))
    except (TypeError, ValueError):
        return False


def _loc(locale: str | None) -> Locale:
    return _locale(locale) if locale else current().locale


def _apply(pattern, value, loc: Locale, decimals: int, min_decimals: int | None,
           currency: str | None = None, grouping: bool = True) -> str:
    p = copy.copy(pattern)
    lo = decimals if min_decimals is None else min(min_decimals, decimals)
    p.frac_prec = (lo, decimals)
    return p.apply(value, loc, currency=currency, currency_digits=False,
                   decimal_quantization=True, group_separator=grouping)


def _signed(text: str, value, loc: Locale, signed: bool) -> str:
    """Prefix the locale's plus sign for signed values ≥ 0 (as Python's
    "{:+}" did, so zero reads "+0%")."""
    if signed and value >= 0:
        return _bnum.get_plus_sign_symbol(loc) + text
    return text


def fmt_num(value, decimals: int = 2, *, min_decimals: int | None = None, signed: bool = False,
            grouping: bool = True, locale: str | None = None) -> str:
    """Locale number: fmt_num(1234.5) → '1,234.50' (en-GB) / '1.234,50' (nl-BE).
    ``min_decimals`` < ``decimals`` trims trailing zeros (share quantities)."""
    if _is_missing(value):
        return MISSING
    loc = _loc(locale)
    value = 0.0 if value == 0 else value   # no "-0"
    out = _apply(loc.decimal_formats[None], value, loc, decimals, min_decimals, grouping=grouping)
    return _signed(out, value, loc, signed)


_SYM_TO_CODE = {"€": "EUR", "$": "USD", "US$": "USD", "£": "GBP", "CHF": "CHF", "Fr.": "CHF",
                "kr": "SEK", "¥": "JPY"}


def ccy_code(currency: str | None) -> str:
    """'€' / 'EUR' / 'CHF ' → ISO code (callers that still pass a symbol)."""
    c = (currency or "EUR").strip()
    if c in _SYM_TO_CODE:
        return _SYM_TO_CODE[c]
    return c.upper() if len(c) == 3 and c.isalpha() else "EUR"


def fmt_int(value, *, signed: bool = False, locale: str | None = None) -> str:
    return fmt_num(value, 0, signed=signed, locale=locale)


def _glued_minus(pattern) -> bool:
    """True when the negative pattern puts the minus straight after the
    currency symbol with no space ("¤-#", de-CH/it-CH)."""
    pos, neg = pattern.prefix
    return neg != pos and neg.endswith("-") and neg[:-1].rstrip() == neg[:-1] and "¤" in neg


def fmt_money(value, currency: str | None = None, decimals: int = 2, *, signed: bool = False,
              approx: bool = False, locale: str | None = None) -> str:
    """Locale currency: symbol position/spacing from CLDR (spec F-02).
    ``currency`` defaults to the user's display currency; ``approx`` adds the
    '≈' mark for converted amounts (F-04)."""
    if _is_missing(value):
        return MISSING
    loc = _loc(locale)
    ccy = currency or current().currency
    value = 0.0 if value == 0 else value   # no "-0.00"
    pattern = loc.currency_formats["standard"]
    if value < 0 and _glued_minus(pattern):
        # de-CH / it-CH: CLDR's "¤-#,##0.00" reads "CHF-4’390" next to a signed
        # "+EUR 155.72". Put the minus where the plus goes: "-CHF 4’390".
        out = _bnum.get_minus_sign_symbol(loc) + _apply(pattern, -value, loc, decimals, None, currency=ccy)
    else:
        out = _apply(pattern, value, loc, decimals, None, currency=ccy)
    out = _signed(out, value, loc, signed)
    return f"≈ {out}" if approx else out


def fmt_pct(value, decimals: int = 1, *, signed: bool = False, fraction: bool = False,
            min_decimals: int | None = None, locale: str | None = None) -> str:
    """Locale percentage (spec F-05). ``value`` is in percent points (12.5 →
    '12.5%' / '12,5 %'); pass fraction=True for 0.125."""
    if _is_missing(value):
        return MISSING
    loc = _loc(locale)
    frac = float(value) if fraction else float(value) / 100
    frac = 0.0 if frac == 0 else frac
    out = _apply(loc.percent_formats[None], frac, loc, decimals, min_decimals)
    return _signed(out, frac, loc, signed)


def fmt_compact(value, *, currency: str | None = None, decimals: int = 1,
                locale: str | None = None) -> str:
    """Compact notation for tight spaces (spec F-06): 1.2B / 1,2 Mrd."""
    if _is_missing(value):
        return MISSING
    loc = _loc(locale)
    if abs(value) < 1000:
        return fmt_money(value, currency, 0, locale=locale) if currency else fmt_num(value, 0, locale=locale)
    # CLDR has no short form for some magnitudes (German and Italian
    # thousands): Babel then prints the raw number ("12752,2"), so show the
    # full grouped amount instead.
    if not any(ch.isalpha() for ch in _bnum.format_compact_decimal(value, locale=loc, fraction_digits=decimals)):
        return fmt_money(value, currency, 0, locale=locale) if currency else fmt_num(value, 0, locale=locale)
    if currency:
        return _bnum.format_compact_currency(value, currency, locale=loc, fraction_digits=decimals)
    return _bnum.format_compact_decimal(value, locale=loc, fraction_digits=decimals)


def _to_date(value):
    if _is_missing(value):
        return None
    if isinstance(value, str):
        if not value.strip():
            return None
        try:
            value = _dt.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    if hasattr(value, "to_pydatetime"):          # pandas Timestamp
        try:
            if value != value:  # NaT
                return None
        except Exception:
            pass
        value = value.to_pydatetime()
    return value if isinstance(value, (_dt.date, _dt.datetime)) else None


def fmt_date(value, style: str | None = None, *, skeleton: str | None = None,
             locale: str | None = None) -> str:
    """Locale date (spec F-07). ``style`` defaults to the user's date format
    (short / medium / iso); ``skeleton`` (e.g. "yMMM", "MMMd") picks a CLDR
    pattern for compact labels such as chart ticks."""
    d = _to_date(value)
    if d is None:
        return MISSING
    if isinstance(d, _dt.datetime):
        d = d.date()
    loc = _loc(locale)
    if skeleton:
        return _bdates.format_skeleton(skeleton, d, locale=loc)
    style = style or current().date_format
    if style == "iso":
        return d.isoformat()
    return _bdates.format_date(d, format=style if style in ("short", "medium", "long", "full") else "short",
                               locale=loc)


def _in_tz(value, tz: str | None) -> _dt.datetime | None:
    """Aware datetimes convert to the user's time zone (F-12). Naive ones are
    shown as they are: this app's naive timestamps are already local (market
    or server time), so guessing their zone would shift them."""
    d = _to_date(value)
    if d is None:
        return None
    if not isinstance(d, _dt.datetime):
        d = _dt.datetime(d.year, d.month, d.day)
    if d.tzinfo is None:
        return d
    return d.astimezone(ZoneInfo(tz or current().time_zone))


def fmt_time(value, *, tz: str | None = None, locale: str | None = None) -> str:
    d = _in_tz(value, tz)
    if d is None:
        return MISSING
    return _bdates.format_time(d, format="short", locale=_loc(locale))


def fmt_datetime(value, *, tz: str | None = None, style: str | None = None,
                 locale: str | None = None) -> str:
    """Date + time in the user's time zone (spec F-12)."""
    d = _in_tz(value, tz)
    if d is None:
        return MISSING
    return f"{fmt_date(d, style, locale=locale)} {_bdates.format_time(d, format='short', locale=_loc(locale))}"


# ── Parsing (spec F-10, T-04) ────────────────────────────────────────────────

class NumberParseError(ValueError):
    """Input that isn't a number in the active region format."""

    def __init__(self, text: str, example: str):
        super().__init__(text)
        self.example = example

    @property
    def message(self) -> str:
        return _("Couldn't read this number. Use the format {example}.", example=self.example)


_SPACES = "    "
_APOSTROPHES = "'’ʼ"


def parse_num(text, *, locale: str | None = None) -> float | None:
    """Parse user input in the region format: '1.234,5' → 1234.5 in nl-BE,
    '1.234' → 1.234 in en-GB. Blank → None. Anything ambiguous or malformed
    raises NumberParseError rather than being guessed (F-10)."""
    loc = _loc(locale)
    example = number_example(locale)
    if text is None:
        return None
    s = str(text).strip()
    if not s:
        return None
    sym = loc.number_symbols["latn"]
    group, decimal = sym["group"], sym["decimal"]
    s = s.replace("−", "-").replace("%", "").strip()
    for ch in "€$£":
        s = s.replace(ch, "")
    s = re.sub(r"\b(EUR|USD|GBP|CHF)\b", "", s).strip()
    if group in _SPACES:
        s = re.sub(f"[{_SPACES}]", group, s)
    else:
        s = re.sub(f"[{_SPACES}]", "", s)
    if group in _APOSTROPHES:
        s = re.sub(f"[{_APOSTROPHES}]", group, s)
    neg = s.startswith("-")
    s = s.lstrip("+-").strip()
    if not s or not re.fullmatch(r"[0-9" + re.escape(group + decimal) + r"]+", s):
        raise NumberParseError(str(text), example)
    try:
        val = _bnum.parse_decimal(s, locale=loc, strict=True)
    except _bnum.NumberFormatError as e:
        raise NumberParseError(str(text), example) from e
    out = float(val)
    return -out if neg else out


def date_input_format(locale: str | None = None) -> str:
    """The region's day/month/year order and separator in the form
    st.date_input accepts ('DD/MM/YYYY', 'MM/DD/YYYY', 'YYYY-MM-DD', 'DD.MM.YYYY', …)."""
    if current().date_format == "iso":
        return "YYYY-MM-DD"
    pat = _loc(locale).date_formats["short"].pattern
    order = "".join(ch for ch in pat if ch in "dMy")
    seq = []
    for ch in order:
        if ch not in seq:
            seq.append(ch)
    sep = next((ch for ch in pat if ch in "/-."), "/")
    parts = {"d": "DD", "M": "MM", "y": "YYYY"}
    fmt = sep.join(parts[c] for c in seq) if len(seq) == 3 else "DD/MM/YYYY"
    return fmt if fmt.replace(sep, "/") in ("DD/MM/YYYY", "MM/DD/YYYY", "YYYY/MM/DD") else "DD/MM/YYYY"


def number_example(locale: str | None = None) -> str:
    return fmt_num(1234.56, 2, locale=locale)


# ── Charts (spec F-08, T-02) ─────────────────────────────────────────────────

def plotly_separators(locale: str | None = None) -> str:
    """Plotly's layout.separators: decimal mark then thousands mark."""
    sym = _loc(locale).number_symbols["latn"]
    return sym["decimal"] + sym["group"]


_CLDR_TO_D3 = (("yyyy", "%Y"), ("yy", "%y"), ("y", "%Y"), ("MM", "%m"), ("M", "%-m"),
               ("dd", "%d"), ("d", "%-d"))


def _cldr_to_d3(pat: str) -> str:
    out, i = "", 0
    while i < len(pat):
        for cldr, d3 in _CLDR_TO_D3:
            if pat.startswith(cldr, i):
                out += d3
                i += len(cldr)
                break
        else:
            ch = pat[i]
            out += "" if ch == "'" else ch
            i += 1
    return out


def d3_date_format(style: str | None = None, locale: str | None = None) -> str:
    """The user's date style as a d3 format for Plotly ticks and hovers
    (F-08). 'medium' uses the short numeric pattern: Plotly only ships
    English month names."""
    style = style or current().date_format
    if style == "iso":
        return "%Y-%m-%d"
    return _cldr_to_d3(_loc(locale).date_formats["short"].pattern)


def d3_month_format(locale: str | None = None) -> str:
    """Numeric month + year in the region's order ('09/2026', '09.2026')."""
    if current().date_format == "iso":
        return "%Y-%m"
    skel = _loc(locale).datetime_skeletons.get("yMM")
    return _cldr_to_d3(skel.pattern) if skel is not None else "%m/%Y"


def localize_fig(fig, *, date_axis: str | None = "x"):
    """Apply region separators, and on ``date_axis`` zoom-dependent numeric
    date ticks (year → month/year → full date) plus a full-date hover, to a
    Plotly figure. Returns the figure for chaining."""
    fig.update_layout(separators=plotly_separators())
    if date_axis:
        full = d3_date_format()
        stops = [dict(dtickrange=[None, "M1"], value=full),
                 # inclusive ranges: stop at M11 so yearly ticks (M12) show just the year
                 dict(dtickrange=["M1", "M11"], value=d3_month_format()),
                 dict(dtickrange=["M12", None], value="%Y")]
        fig.update_layout(**{f"{date_axis}axis": {"tickformatstops": stops, "hoverformat": full}})
    return fig


# ── Tables (spec T-03) ───────────────────────────────────────────────────────

def style_table(df, formatters: dict):
    """A Styler that shows locale strings while st.dataframe keeps sorting on
    the underlying numbers. ``formatters`` maps column → callable."""
    return df.style.format({c: f for c, f in formatters.items() if c in df.columns}, na_rep=MISSING)


# ── Collation and search (spec F-13, F-14) ───────────────────────────────────

@lru_cache(maxsize=1)
def _collator():
    from pyuca import Collator
    return Collator()


def sort_key(text) -> tuple:
    """Unicode collation key (DUCET): 'Électricité' sorts with E, 'Ørsted'
    with O. Case-insensitive at the primary level."""
    if text is None or (isinstance(text, float) and math.isnan(text)):
        return ()
    return _collator().sort_key(str(text))


def sort_df(df, column: str, *, ascending: bool = True):
    """Sort a DataFrame by a text column using sort_key()."""
    return df.sort_values(column, key=lambda s: s.map(sort_key), ascending=ascending, kind="stable")


_FOLD_EXTRA = str.maketrans({"ø": "o", "Ø": "o", "æ": "ae", "Æ": "ae", "œ": "oe", "Œ": "oe",
                             "ł": "l", "Ł": "l", "đ": "d", "Đ": "d", "ß": "ss"})
_PUNCT = re.compile(r"[\s'’ʼ`´.\-‐–—_/&,()]+")


@lru_cache(maxsize=8192)
def fold(text: str) -> str:
    """Accent-, case- and punctuation-insensitive form for search:
    "L'Oréal" → 'loreal', 'Société Générale' → 'societegenerale'."""
    s = unicodedata.normalize("NFKD", str(text).translate(_FOLD_EXTRA))
    s = "".join(c for c in s if not unicodedata.combining(c)).casefold()
    return _PUNCT.sub("", s)


def search_match(query: str, *fields) -> bool:
    q = fold(query or "")
    if not q:
        return True
    return any(q in fold(f) for f in fields if f is not None and not (isinstance(f, float) and math.isnan(f)))


# ── Names for pickers (spec §7.1, S-08) ──────────────────────────────────────

def language_name(lang: str, *, in_lang: str | None = None) -> str:
    """'nl' → 'Nederlands' (own language by default, spec §7.1)."""
    try:
        name = _locale(lang).get_display_name(in_lang or lang) or lang
    except (UnknownLocaleError, ValueError):
        return lang
    return name[:1].upper() + name[1:]


def region_name(region: str, *, in_lang: str | None = None) -> str:
    """'nl-BE' → 'België (Nederlands) — 1.234,56', names in the UI language."""
    ui = in_lang or current().lang
    loc = _locale(region)
    terr = _locale(ui).territories.get(loc.territory, loc.territory)
    lang = _locale(ui).languages.get(loc.language, loc.language)
    return f"{terr} ({lang}) — {fmt_num(1234.56, 2, locale=region)}"


def time_zones() -> list[str]:
    from zoneinfo import available_timezones
    return sorted(z for z in available_timezones() if "/" in z and not z.startswith(("Etc/", "SystemV/")))


def with_(ctx: Ctx, **changes) -> Ctx:
    return replace(ctx, **changes)


def inject_lang_attr() -> None:
    """Set <html lang> on the parent document to the interface language
    (spec L-10, N-04) — same hidden-iframe pattern as the theme sync in
    uvalu/shell.py."""
    lang = current().lang
    with st.container(key="uv_hidden_util_lang"):
        st.iframe(f"""
<script>
(function(){{
  try {{ window.parent.document.documentElement.setAttribute('lang', {lang!r}); }} catch(e) {{}}
}})();
</script>
""", height=1)


# ── Display currency (spec F-03, F-04) ───────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def _display_rate(ccy: str, on_iso: str):
    """(EUR per 1 ccy, fixing date) from fx.py's ECB source, or None."""
    import fx
    try:
        q = fx.get_rate(ccy, base="EUR", on=_dt.date.fromisoformat(on_iso))
    except Exception:
        return None
    return (q.rate, q.rate_date.isoformat()) if q.rate else None


def display_rate() -> tuple[float, str] | None:
    """EUR→display-currency quote for today, None when the display currency
    is EUR or no rate is available (totals then stay in EUR)."""
    ccy = current().currency
    if ccy == "EUR":
        return None
    return _display_rate(ccy, _dt.date.today().isoformat())


def to_display(value_eur):
    """(value, currency, converted) for a EUR portfolio total."""
    q = display_rate()
    if q is None or _is_missing(value_eur):
        return value_eur, "EUR", False
    return value_eur / q[0], current().currency, True


def fmt_total(value_eur, decimals: int = 0, *, signed: bool = False) -> str:
    """A portfolio total/aggregate (computed in EUR) in the display currency,
    '≈'-marked when converted (F-03, F-04)."""
    v, ccy, converted = to_display(value_eur)
    return fmt_money(v, ccy, decimals, signed=signed, approx=converted)


def conversion_note() -> str | None:
    """'Converted at 0.9312 on 26/09/2026' for the ≈ amounts, if any."""
    q = display_rate()
    if q is None:
        return None
    rate, day = q
    return _("Converted at {rate} on {date}",
             rate=f"1 {current().currency} = {fmt_num(rate, 4)} EUR", date=fmt_date(day))


def plotly_money_axis(currency: str | None = None, decimals: int = 0) -> dict:
    """Plotly axis settings putting the currency symbol where the region puts
    it ('€1,234' vs '1.234 €'); combine with localize_fig() separators."""
    loc = current().locale
    ccy = currency or current().currency
    sym = _bnum.get_currency_symbol(ccy, locale=loc)
    pat = loc.currency_formats["standard"].pattern.split(";")[0]
    fmt = f",.{decimals}f"
    if pat.strip().startswith("¤"):
        return {"tickprefix": sym + (" " if "¤ " in pat else ""), "ticksuffix": "", "tickformat": fmt}
    return {"tickprefix": "", "ticksuffix": (" " if " ¤" in pat else "") + sym, "tickformat": fmt}
