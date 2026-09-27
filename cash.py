"""
Cash ledger — Cash Management v1.

One cash balance per portfolio, derived from an append-only ledger of
transactions stored in the user's encrypted ``cash.json`` (retained
indefinitely — it lives under ``data/portfolio/<user>/``, which log retention
never touches). See ``docs/cash-management-implementation-plan.md`` for the
decisions this implements and ``docs/data-contracts.md`` for the contract.

Entry types and their effect (the sign is applied here, never taken from UI
input — users always type positive amounts):

    Deposit / Sell / Dividend / Interest   +      Withdrawal / Buy / Fee   −
    Adjustment                             sets the balance to `target_balance`

Rules:
- Every amount is stored in its original currency together with the FX rate
  to the base currency (frankfurter.dev / ECB via ``fx.py``, or a manual,
  flagged rate) and the resulting ``amount_base`` — fixed at post time, so a
  later rate revision never rewrites history.
- The balance is the running sum of the ledger in base currency, replayed in
  (date, seq) order. An Adjustment stores its target; its delta is computed on
  replay as ``target − running balance just before it``.
- Manual debits (Withdrawal, Fee) are blocked if the balance would go below
  zero at *any* point from their date onward (until the next Adjustment).
- Trades are never blocked (user decision D3): when a Buy (or a fee-heavy
  Sell) would take the balance below zero, an automatic, linked ``Deposit``
  (``topup=True``) for exactly the shortfall is posted right before it.
- Dividend payments are mirrored into the ledger by
  ``reconcile_dividend_postings`` — posted, updated or removed so the ledger
  always matches the dividend log (DRIP, Stock and future-dated dividends
  excluded).

No Streamlit import — everything here is a plain function, unit-tested in
tests/test_cash.py.
"""
from __future__ import annotations

import csv
import io
import json
import math
import threading
from datetime import date, datetime

import pandas as pd

import fx
import portfolio
from uvalu import logkit
from uvalu.i18n import N_, Fmt, _, english, tr

TYPES = (N_("Deposit"), N_("Withdrawal"), N_("Buy"), N_("Sell"), N_("Dividend"), N_("Fee"),
         N_("Interest"), N_("Adjustment"))
MANUAL_TYPES = ("Deposit", "Withdrawal", "Fee", "Interest", "Adjustment")
_SIGN = {"Deposit": 1, "Withdrawal": -1, "Buy": -1, "Sell": 1,
         "Dividend": 1, "Fee": -1, "Interest": 1}

# Keys are the (English) filter ids; the UI shows them through tr().
FILTER_GROUPS: dict[str, tuple[str, ...] | None] = {
    N_("All"): None,
    N_("Deposits & withdrawals"): ("Deposit", "Withdrawal"),
    N_("Trades"): ("Buy", "Sell"),
    N_("Income"): ("Dividend", "Interest"),
    N_("Fees & adjustments"): ("Fee", "Adjustment"),
}

_FIELDS = ("id", "seq", "date", "type", "amount", "currency", "fx_rate", "fx_source",
           "fx_date", "amount_base", "target_balance", "delta_at_entry", "opening",
           "note", "note_i18n", "ref_kind", "ref_id", "ref_label", "auto", "topup", "created_at")

_lock = threading.RLock()


class CashError(ValueError):
    """A ledger rule rejected the entry; the message is user-facing."""


# ── Formatting helpers (shared with the UI) ──────────────────────────────────

def money(v: float, ccy: str = "EUR", dp: int = 2) -> str:
    """€1,234.56 / −€12.40 in the region format — keeps the design's U+2212
    minus sign in front of the locale's own currency pattern."""
    from uvalu.i18n import fmt_money
    sign = "−" if v < 0 else ""
    return sign + fmt_money(abs(v), ccy, dp)


def signed_money(v: float, ccy: str = "EUR", dp: int = 2) -> str:
    return ("+" if v >= 0 else "") + money(v, ccy, dp)


def _render_note_arg(v):
    """A stored note argument → a value for _(): plain values pass through,
    [kind, value, opts] becomes a region-formatted number/money, and
    ["type_lower", "Cash", {}] a translated, lower-cased type name."""
    if isinstance(v, (list, tuple)) and len(v) == 3 and isinstance(v[2], dict):
        kind, value, opts = v
        if kind == "type_lower":
            word = tr(value)
            return word if _is_de() else word.lower()
        return Fmt(kind, value, **opts)
    return v


def _is_de() -> bool:
    from uvalu.i18n import current
    return current().lang == "de"   # German keeps nouns capitalised


def auto_note(parts: list) -> tuple[str, str]:
    """(English note, note_i18n JSON) for an automatic ledger note built
    from (msgid, args) parts joined by spaces. The English text is what's
    stored in ``note`` (and exported); note_text() re-renders the parts in
    the viewer's language and region."""
    with english():
        text = " ".join(_(mid, **{k: _render_note_arg(v) for k, v in args.items()}) for mid, args in parts)
    return text, json.dumps([{"id": mid, "args": args} for mid, args in parts])


def note_text(entry: dict) -> str:
    """A ledger entry's description in the viewer's language: automatic
    notes from their note_i18n parts, anything else (typed notes, entries
    written before note_i18n existed) through tr()."""
    raw = entry.get("note_i18n")
    if raw:
        try:
            parts = json.loads(raw)
            return " ".join(_(p["id"], **{k: _render_note_arg(v) for k, v in (p.get("args") or {}).items()})
                            for p in parts)
        except Exception:
            pass
    return tr(entry.get("note") or "")


def fmt_date(iso: str | None) -> str:
    """'2026-07-01' → the user's date format in their region (i18n spec F-07)."""
    from uvalu.i18n import MISSING, fmt_date as _fmt_date
    out = _fmt_date(iso)
    return str(iso or "") if out == MISSING else out


# ── Storage ──────────────────────────────────────────────────────────────────

def _clean(v):
    if isinstance(v, float) and math.isnan(v):
        return None
    if v is pd.NaT:
        return None
    return v


def _to_date(on) -> date:
    if on is None:
        return date.today()
    if isinstance(on, datetime):
        return on.date()
    if isinstance(on, date):
        return on
    ts = pd.to_datetime(on, errors="coerce")
    if pd.isna(ts):
        raise CashError(_("Enter a date, e.g. 07 Jul 2026."))
    return ts.date()


def _migrate(records: list[dict]) -> tuple[list[dict], bool]:
    """Bring legacy rows up to the ledger schema. The pre-v1 ``cash.json``
    shape was ``{currency, amount}`` with no type (written by nothing but a
    test, but handled defensively): it becomes one opening Adjustment."""
    legacy = [r for r in records if not r.get("type")]
    if not legacy:
        return records, False
    base = portfolio.base_currency()
    total = 0.0
    for r in legacy:
        amt = float(pd.to_numeric(r.get("amount"), errors="coerce") or 0.0)
        ccy = str(r.get("currency") or base).upper()
        rate = 1.0
        if ccy != base:
            try:
                rate = fx.get_rate(ccy, base).rate
            except fx.FxUnavailable:
                rate = 1.0
        total += amt * rate
    kept = [r for r in records if r.get("type")]
    opening = _new_entry("Adjustment", date.today(), None, base, 1.0, "base", None,
                         N_("Opening balance · migrated from earlier cash records"),
                         target_balance=round(max(total, 0.0), 2), opening=True)
    return [opening] + kept, True


def load_ledger() -> list[dict]:
    df = portfolio.load_cash()
    if df is None or df.empty:
        return []
    records = [{k: _clean(v) for k, v in r.items()} for r in df.to_dict("records")]
    records, changed = _migrate(records)
    for r in records:
        r["seq"] = int(r.get("seq") or 0)
        r["auto"] = bool(r.get("auto"))
        r["topup"] = bool(r.get("topup"))
        r["opening"] = bool(r.get("opening"))
    if changed:
        save_ledger(records)
    return records


def save_ledger(entries: list[dict]) -> None:
    rows = [{f: e.get(f) for f in _FIELDS} for e in entries]
    portfolio.save_cash(pd.DataFrame(rows, columns=list(_FIELDS)))


# ── Replay ───────────────────────────────────────────────────────────────────

def _order(e: dict) -> tuple:
    return (str(e.get("date") or ""), int(e.get("seq") or 0))


def replay(entries: list[dict]) -> list[dict]:
    """Entries in ledger order, each copied with ``base`` (its effect in base
    currency) and ``bal`` (running balance after it). 2-dp rounding at every
    step, so the displayed column always sums."""
    bal = 0.0
    out = []
    for e in sorted(entries, key=_order):
        if e.get("type") == "Adjustment":
            target = float(e.get("target_balance") or 0.0)
            base = round(target - bal, 2)
        else:
            ab = e.get("amount_base")
            if ab is None:
                ab = float(e.get("amount") or 0.0) * float(e.get("fx_rate") or 1.0)
            base = round(float(ab), 2)
        bal = round(bal + base, 2)
        out.append({**e, "base": base, "bal": bal})
    return out


def balance(entries: list[dict] | None = None) -> float:
    rows = replay(load_ledger() if entries is None else entries)
    return rows[-1]["bal"] if rows else 0.0


def balance_before(entries: list[dict], on: date) -> float:
    """Running balance just before a new entry dated ``on`` — i.e. after every
    existing entry dated on or before ``on`` (a new entry sorts after them)."""
    iso = on.isoformat()
    bal = 0.0
    for r in replay(entries):
        if r["date"] <= iso:
            bal = r["bal"]
    return bal


def min_balance_after(entries: list[dict], candidate: dict) -> float:
    """Lowest running balance from ``candidate`` onward with it inserted —
    stopping at the next Adjustment, which resets the balance and so shields
    everything after it."""
    probe = {**candidate, "_probe": True}
    if not probe.get("seq"):
        probe["seq"] = 10 ** 12
    rows = replay(entries + [probe])
    idx = next(i for i, r in enumerate(rows) if r.get("_probe"))
    low = rows[idx]["bal"]
    for r in rows[idx + 1:]:
        if r.get("type") == "Adjustment":
            break
        low = min(low, r["bal"])
    return low


def has_negative_history(entries: list[dict]) -> bool:
    return any(r["bal"] < -0.004 for r in replay(entries))


# ── Posting ──────────────────────────────────────────────────────────────────

def _new_entry(type_: str, on: date, amount: float | None, currency: str, fx_rate: float,
               fx_source: str, fx_date: str | None, note: str, **extra) -> dict:
    eid = portfolio.next_id("cash")
    amount_base = None if amount is None else round(amount * fx_rate, 2)
    e = {
        "id": eid, "seq": int(eid.split("-")[1]), "date": on.isoformat(), "type": type_,
        "amount": None if amount is None else round(amount, 2), "currency": currency,
        "fx_rate": round(float(fx_rate), 6), "fx_source": fx_source, "fx_date": fx_date,
        "amount_base": amount_base, "target_balance": None, "delta_at_entry": None,
        "opening": False, "note": note or "", "ref_kind": None, "ref_id": None,
        "ref_label": None, "auto": False, "topup": False,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    e.update(extra)
    return e


def resolve_rate(currency: str, on: date, manual_rate: float | None = None) -> tuple[float, str, str | None]:
    """(rate, fx_source, fx_date) for converting ``currency`` to base on
    ``on``. A manual rate wins (flagged "manual"); otherwise the ECB rate —
    raises fx.FxUnavailable when frankfurter has none, so the UI can ask for
    a manual one."""
    base = portfolio.base_currency()
    currency = (currency or base).upper()
    if currency == base:
        return 1.0, "base", None
    if manual_rate is not None:
        if not (manual_rate > 0):
            raise CashError(_("Enter the FX rate to convert {currency} to {base}.", currency=currency, base=base))
        return float(manual_rate), "manual", None
    q = fx.get_rate(currency, base, on)
    return q.rate, "ecb", q.rate_date.isoformat()


def blocked_message(low: float, base: str = "EUR") -> str:
    return _("Blocked: this would take the cash balance to {amount}. Balance cannot go negative.",
             amount=money(low, base))


def post_manual(type_: str, on, amount: float, currency: str | None = None, *,
                note: str = "", manual_rate: float | None = None) -> dict:
    """Deposit / Withdrawal / Fee / Interest entered by the user."""
    if type_ not in ("Deposit", "Withdrawal", "Fee", "Interest"):
        raise CashError(f"Unsupported transaction type: {type_}")
    d = _to_date(on)
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        amount = 0.0
    if not (amount > 0) or math.isinf(amount):
        raise CashError(_("Enter an amount greater than zero."))
    base = portfolio.base_currency()
    currency = (currency or base).upper()
    rate, src, fx_date = resolve_rate(currency, d, manual_rate)
    signed = _SIGN[type_] * amount
    with _lock:
        entries = load_ledger()
        if _SIGN[type_] < 0:
            probe = {"id": "probe", "seq": 10 ** 12, "date": d.isoformat(), "type": type_,
                     "amount_base": round(signed * rate, 2)}
            low = min_balance_after(entries, probe)
            if low < -0.004:
                raise CashError(blocked_message(low, base))
        cand = _new_entry(type_, d, signed, currency, rate, src, fx_date, note.strip() or type_)
        entries.append(cand)
        save_ledger(entries)
    logkit.data_mutation(actor=logkit.user_id(), action="cash.post", entity_type="cash",
                         entity_id=cand["id"], type=type_, currency=currency, fx_source=src)
    return cand


def post_adjustment(on, target_balance: float, note: str = "") -> dict:
    """Set the balance to ``target_balance`` as of ``on``, as its own entry —
    history is never overwritten. The first entry of an empty ledger is
    marked as the opening balance."""
    d = _to_date(on)
    try:
        target = float(target_balance)
    except (TypeError, ValueError):
        raise CashError(_("Enter the corrected balance."))
    if math.isnan(target) or math.isinf(target):
        raise CashError(_("Enter the corrected balance."))
    if target < 0:
        raise CashError(_("Balance cannot go negative."))
    base = portfolio.base_currency()
    with _lock:
        entries = load_ledger()
        is_opening = not entries
        delta = round(target - balance_before(entries, d), 2)
        cand = _new_entry("Adjustment", d, None, base, 1.0, "base", None,
                          note.strip() or (N_("Opening balance") if is_opening else N_("Manual balance correction")),
                          target_balance=round(target, 2), delta_at_entry=delta, opening=is_opening)
        entries.append(cand)
        save_ledger(entries)
    logkit.data_mutation(actor=logkit.user_id(), action="cash.adjust", entity_type="cash",
                         entity_id=cand["id"], opening=is_opening)
    return cand


def trade_amount(kind: str, gross: float, fee: float = 0.0) -> float:
    """Signed cash effect of a trade: buy −(gross + fee), sell +(gross − fee)."""
    fee = float(fee or 0.0)
    return round(-(gross + fee), 2) if kind == "Buy" else round(gross - fee, 2)


def preview_trade(kind: str, gross: float, fee: float = 0.0, on=None,
                  entries: list[dict] | None = None) -> dict:
    """What a trade would do to cash — for the Buy/Sell dialogs' "Cash after
    trade" line. Keys: amount, topup, after (balance after, ≥ 0)."""
    entries = load_ledger() if entries is None else entries
    d = _to_date(on)
    amt = trade_amount(kind, gross, fee)
    probe = {"id": "probe", "seq": 10 ** 12, "date": d.isoformat(), "type": kind,
             "amount": amt, "amount_base": amt, "fx_rate": 1.0}
    topup = round(max(0.0, -min_balance_after(entries, probe)), 2)
    after = round(balance(entries) + amt + topup, 2)
    return {"amount": amt, "topup": topup, "after": after}


def post_trade(kind: str, *, trade_id: str, ticker: str, shares: float, gross: float,
               fee: float = 0.0, on=None) -> list[dict]:
    """Auto-post a Buy/Sell (base currency — trades are entered in EUR).
    Never raises for an insufficient balance: the shortfall is covered by an
    automatic top-up Deposit, linked to the same trade and ordered right
    before it, so the balance never goes below zero (D3). Returns the posted
    entries (top-up first when there is one)."""
    if kind not in ("Buy", "Sell"):
        raise CashError(f"Unsupported trade kind: {kind}")
    d = _to_date(on)
    base = portfolio.base_currency()
    amt = trade_amount(kind, gross, fee)
    price = gross / shares if shares else gross
    parts = [(N_("Bought {shares} {ticker} × {price}") if kind == "Buy" else N_("Sold {shares} {ticker} × {price}"),
              {"shares": ("num", float(shares), {"decimals": 4, "min_decimals": 0}), "ticker": ticker,
               "price": ("money", float(price), {"currency": base})})]
    if fee:
        parts.append((N_("· fee {amount}"), {"amount": ("money", float(fee), {"currency": base})}))
    note, note_i18n = auto_note(parts)
    label = f"{trade_id} · {ticker}"
    with _lock:
        entries = load_ledger()
        probe = {"id": "probe", "seq": 10 ** 12, "date": d.isoformat(), "type": kind,
                 "amount": amt, "amount_base": amt, "fx_rate": 1.0}
        topup = round(max(0.0, -min_balance_after(entries, probe)), 2)
        posted: list[dict] = []
        if topup > 0:
            _tnote, _tnote_i18n = auto_note([(N_("Auto top-up to fund {label}"), {"label": label})])
            posted.append(_new_entry("Deposit", d, topup, base, 1.0, "base", None, _tnote,
                                     ref_kind="trade", ref_id=trade_id, ref_label=label,
                                     auto=True, topup=True, note_i18n=_tnote_i18n))
        posted.append(_new_entry(kind, d, amt, base, 1.0, "base", None, note,
                                 ref_kind="trade", ref_id=trade_id, ref_label=label, auto=True,
                                 note_i18n=note_i18n))
        entries.extend(posted)
        save_ledger(entries)
    logkit.data_mutation(actor=logkit.user_id(), action="cash.post_trade", entity_type="cash",
                         entity_id=trade_id, type=kind, topup=bool(topup))
    return posted


def remove_ref(ref_kind: str, ref_id: str, *, check: bool = False) -> int:
    """Delete every entry linked to one trade/dividend. Used to roll back a
    trade whose position write failed (``check=False``) and, with
    ``check=True``, when the user deletes a position or closed trade together
    with its cash — then refused (CashError) if it would take the running
    balance lower below zero. Returns the number removed."""
    with _lock:
        entries = load_ledger()
        kept = [e for e in entries if not (e.get("ref_kind") == ref_kind and e.get("ref_id") == ref_id)]
        n = len(entries) - len(kept)
        if n:
            if check:
                _check_not_worse(entries, kept)
            save_ledger(kept)
    return n


# ── Editing (manual entries) and trade links ─────────────────────────────────
# Manual entries (Deposit / Withdrawal / Fee / Interest / Adjustment) can be
# edited and deleted in place — the entry keeps its id, and the change is
# audit-logged. Auto entries (trades, top-ups, dividends) mirror another
# record and are changed only through it: the position / closed-trade dialogs
# (re-post or remove the linked trade entries) or the dividend log
# (reconcile_dividend_postings).

def get_entry(entry_id: str, entries: list[dict] | None = None) -> dict | None:
    entries = load_ledger() if entries is None else entries
    return next((e for e in entries if e.get("id") == entry_id), None)


def is_editable(e: dict | None) -> bool:
    return bool(e) and not e.get("auto") and not e.get("ref_kind") and e.get("type") in MANUAL_TYPES


def _check_not_worse(before: list[dict], after: list[dict]) -> None:
    """Edits and deletes follow the same rule as a new manual debit: the
    balance may not go below zero. A ledger that already dips below zero
    (a dividend was edited) may still be edited as long as the change doesn't
    make its lowest point any lower."""
    low_after = min((r["bal"] for r in replay(after)), default=0.0)
    if low_after >= -0.004:
        return
    low_before = min((r["bal"] for r in replay(before)), default=0.0)
    if low_after < low_before - 0.004:
        raise CashError(blocked_message(low_after, portfolio.base_currency()))


def preview_change(entry_id: str | None, replacement: dict | None,
                   entries: list[dict] | None = None) -> dict:
    """Balance after replacing (``replacement``) or deleting (None) an entry,
    for the Edit dialog's preview. Keys: ``after`` (current balance once the
    change is applied) and ``blocked`` (it would break the no-negative rule)."""
    entries = load_ledger() if entries is None else entries
    after_entries = [e for e in entries if e.get("id") != entry_id]
    if replacement is not None:
        after_entries.append(replacement)
    try:
        _check_not_worse(entries, after_entries)
        blocked = False
    except CashError:
        blocked = True
    return {"after": balance(after_entries), "blocked": blocked}


def update_manual(entry_id: str, on, amount: float | None = None, currency: str | None = None, *,
                  note: str = "", manual_rate: float | None = None, refresh_rate: bool = False,
                  target_balance: float | None = None) -> dict:
    """Edit a manual entry in place (its type never changes). FX: a manual
    rate wins; otherwise the stored rate is kept while date and currency are
    unchanged (amount-only edit, same as dividend mirroring), and a fresh ECB
    rate is fetched when either changes or ``refresh_rate`` is set. Raises
    CashError for auto entries and when the change would push the balance
    below zero (fx.FxUnavailable when a fresh rate is needed but missing)."""
    d = _to_date(on)
    base = portfolio.base_currency()
    with _lock:
        entries = load_ledger()
        old = get_entry(entry_id, entries)
        if old is None:
            raise CashError(_("This entry no longer exists."))
        if not is_editable(old):
            raise CashError(_("Automatic entries change with their trade or dividend."))
        t = old["type"]
        new = dict(old)
        new["date"] = d.isoformat()
        if t == "Adjustment":
            try:
                target = float(target_balance)
            except (TypeError, ValueError):
                raise CashError(_("Enter the corrected balance."))
            if math.isnan(target) or math.isinf(target):
                raise CashError(_("Enter the corrected balance."))
            if target < 0:
                raise CashError("Balance cannot go negative.")
            others = [e for e in entries if e.get("id") != entry_id]
            new["target_balance"] = round(target, 2)
            new["delta_at_entry"] = round(target - balance_before(others, d), 2)
            new["note"] = note.strip() or (N_("Opening balance") if old.get("opening")
                                           else N_("Manual balance correction"))
        else:
            try:
                amount = float(amount)
            except (TypeError, ValueError):
                amount = 0.0
            if not (amount > 0) or math.isinf(amount):
                raise CashError(_("Enter an amount greater than zero."))
            currency = (currency or base).upper()
            same_basis = old.get("date") == d.isoformat() and (old.get("currency") or base) == currency
            if currency == base:
                rate, src, fx_date = 1.0, "base", None
            elif manual_rate is not None:
                rate, src, fx_date = resolve_rate(currency, d, manual_rate)
            elif same_basis and not refresh_rate and old.get("fx_rate"):
                rate, src, fx_date = float(old["fx_rate"]), old.get("fx_source") or "ecb", old.get("fx_date")
            else:
                rate, src, fx_date = resolve_rate(currency, d)
            signed = _SIGN[t] * amount
            new.update({"amount": round(signed, 2), "currency": currency, "fx_rate": round(float(rate), 6),
                        "fx_source": src, "fx_date": fx_date, "amount_base": round(signed * rate, 2),
                        "note": note.strip() or t})
        after = [new if e.get("id") == entry_id else e for e in entries]
        _check_not_worse(entries, after)
        save_ledger(after)
    logkit.data_mutation(actor=logkit.user_id(), action="cash.edit", entity_type="cash",
                         entity_id=entry_id, type=t)
    return new


def delete_entry(entry_id: str) -> None:
    """Delete a manual entry. The opening flag is never handed to another
    entry — the ledger simply starts at the next one."""
    with _lock:
        entries = load_ledger()
        old = get_entry(entry_id, entries)
        if old is None:
            return
        if not is_editable(old):
            raise CashError("Automatic entries change with their trade or dividend.")
        after = [e for e in entries if e.get("id") != entry_id]
        _check_not_worse(entries, after)
        save_ledger(after)
    logkit.data_mutation(actor=logkit.user_id(), action="cash.delete", entity_type="cash",
                         entity_id=entry_id, type=old.get("type"), opening=bool(old.get("opening")))


def trade_entries(trade_id: str | None, entries: list[dict] | None = None) -> list[dict]:
    """The ledger entries (trade + any top-up) linked to one trade id."""
    if not trade_id:
        return []
    entries = load_ledger() if entries is None else entries
    return [e for e in entries if e.get("ref_kind") == "trade" and e.get("ref_id") == str(trade_id)]


def trade_in_sync(kind: str, trade_id: str | None, gross: float, fee: float = 0.0,
                  entries: list[dict] | None = None) -> bool:
    """True when ``trade_id`` has a posted ``kind`` entry whose amount still
    equals this record's gross/fee — i.e. the position or closed trade is the
    single, unchanged trade the entry was posted for (not a partly-sold lot or
    an earlier edit made without the cash). Only then may the dialogs offer
    to update or remove the cash along with it."""
    main = [e for e in trade_entries(trade_id, entries) if e.get("type") == kind]
    if len(main) != 1:
        return False
    return abs(float(main[0].get("amount") or 0.0) - trade_amount(kind, gross, fee)) < 0.011


def preview_repost(kind: str, trade_id: str, *, gross: float, fee: float = 0.0, on=None) -> dict:
    """What repost_trade() would do, without writing — for the Edit
    position / Edit trade Cash box. Keys: change (balance after − now),
    topup (the recomputed top-up), after."""
    entries = load_ledger()
    now = balance(entries)
    kept = [e for e in entries if not (e.get("ref_kind") == "trade" and e.get("ref_id") == trade_id)]
    p = preview_trade(kind, gross, fee, on=on, entries=kept)
    return {"change": round(p["after"] - now, 2), "topup": p["topup"], "after": p["after"]}


def repost_trade(kind: str, *, trade_id: str, ticker: str, shares: float, gross: float,
                 fee: float = 0.0, on=None) -> list[dict]:
    """Replace a trade's linked entries with freshly posted ones (the edit
    path of the position / closed-trade dialogs). Like any trade it is never
    blocked by the balance (D3): the top-up is recomputed, so a shortfall the
    new amounts create is covered by an automatic deposit. The old entries
    are restored if posting fails."""
    with _lock:
        before = load_ledger()
        kept = [e for e in before if not (e.get("ref_kind") == "trade" and e.get("ref_id") == trade_id)]
        save_ledger(kept)
        try:
            return post_trade(kind, trade_id=trade_id, ticker=ticker, shares=shares,
                              gross=gross, fee=fee, on=on)
        except Exception:
            save_ledger(before)
            raise


# ── Dividend mirroring ───────────────────────────────────────────────────────

def _truthy(v) -> bool:
    if v is None:
        return False
    if isinstance(v, float) and math.isnan(v):
        return False
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes")
    return bool(v)


def _dividend_net_native(row: dict) -> float:
    """Net cash received, native currency: gross − foreign WH − BE 30% on the
    remainder — exactly portfolio.dividends_in_eur()'s net_after_be_amount."""
    amount = float(pd.to_numeric(row.get("amount"), errors="coerce") or 0.0)
    tax = float(pd.to_numeric(row.get("tax_amount"), errors="coerce") or 0.0)
    if math.isnan(amount):
        amount = 0.0
    if math.isnan(tax):
        tax = 0.0
    be = round(max(amount - tax, 0.0) * portfolio.BE_WITHHOLDING_RATE, 2)
    return round(amount - tax - be, 2)


def reconcile_dividend_postings(div_df: "pd.DataFrame | None" = None) -> int:
    """Make the ledger's Dividend entries mirror the dividend log.

    Posts one linked entry per received dividend (pay date ≤ today, not DRIP,
    not a Stock dividend, net > 0) at the frankfurter rate for its pay date;
    updates an entry whose dividend changed (amount → recomputed at the stored
    rate; date or currency → fresh rate); removes entries whose dividend is
    gone. A dividend whose rate frankfurter can't supply right now is simply
    left for the next run — never posted at a guessed rate. Returns the
    number of entries added/changed/removed."""
    if div_df is None:
        div_df = portfolio.load_div_hist()
    div_df, ids_changed = portfolio.ensure_div_ids(div_df)
    if ids_changed:
        portfolio.save_div_hist(div_df)
    base = portfolio.base_currency()
    today = date.today()
    wanted: dict[str, dict] = {}
    if div_df is not None and not div_df.empty:
        for row in div_df.to_dict("records"):
            pay = pd.to_datetime(row.get("date"), errors="coerce")
            if pd.isna(pay) or pay.date() > today:
                continue
            if str(row.get("div_type") or "Cash") == "Stock" or _truthy(row.get("reinvested")):
                continue
            net = _dividend_net_native(row)
            if net <= 0:
                continue
            ticker = str(row.get("ticker") or "")
            ccy = str(_clean(row.get("currency")) or portfolio.currency_for_ticker(ticker) or base).upper()
            kind = "Special" if str(row.get("div_type")) == "Special" else "Cash"
            name = str(_clean(row.get("name")) or ticker)
            _note, _note_i18n = auto_note([(N_("{name} · {kind} dividend, net of tax"),
                                            {"name": name, "kind": ("type_lower", kind, {})})])
            wanted[str(row["div_id"])] = {
                "date": pay.date(), "amount": net, "currency": ccy,
                "note": _note, "note_i18n": _note_i18n,
                "label": f"{row['div_id']} · {ticker}",
            }

    changes = 0
    with _lock:
        entries = load_ledger()
        mirrors = {e["ref_id"]: e for e in entries if e.get("ref_kind") == "dividend"}
        out: list[dict] = []
        for e in entries:
            if e.get("ref_kind") != "dividend":
                out.append(e)
                continue
            w = wanted.get(e["ref_id"])
            if w is None:
                changes += 1          # dividend deleted / no longer eligible
                continue
            same_rate_basis = e.get("date") == w["date"].isoformat() and e.get("currency") == w["currency"]
            if not same_rate_basis:
                try:
                    rate, src, fx_date = resolve_rate(w["currency"], w["date"])
                except fx.FxUnavailable:
                    out.append(e)     # retry next run
                    continue
                e = {**e, "date": w["date"].isoformat(), "currency": w["currency"],
                     "fx_rate": round(rate, 6), "fx_source": src, "fx_date": fx_date}
                changes += 1
            if (e.get("amount") != w["amount"] or e.get("note") != w["note"] or e.get("ref_label") != w["label"]
                    or e.get("note_i18n") != w["note_i18n"]):
                e = {**e, "amount": w["amount"], "note": w["note"], "note_i18n": w["note_i18n"],
                     "ref_label": w["label"]}
                changes += 1
            e["amount_base"] = round(float(e["amount"]) * float(e.get("fx_rate") or 1.0), 2)
            out.append(e)
        for div_id, w in wanted.items():
            if div_id in mirrors:
                continue
            try:
                rate, src, fx_date = resolve_rate(w["currency"], w["date"])
            except fx.FxUnavailable:
                continue
            out.append(_new_entry("Dividend", w["date"], w["amount"], w["currency"], rate, src, fx_date,
                                  w["note"], ref_kind="dividend", ref_id=div_id,
                                  ref_label=w["label"], auto=True, note_i18n=w["note_i18n"]))
            changes += 1
        if changes:
            save_ledger(out)
    if changes:
        logkit.data_mutation(actor=logkit.user_id(), action="cash.reconcile_dividends",
                             entity_type="cash", changes=changes)
    return changes


# ── Views: summary tiles, filtering, export ──────────────────────────────────

def summary(entries: list[dict], invested_value: float) -> dict:
    """Numbers for the cash strip, the Cash activity tiles, the Dashboard
    Cash tile and the Risk banner."""
    rows = replay(entries)
    bal = rows[-1]["bal"] if rows else 0.0
    invested = float(invested_value or 0.0)
    total = invested + bal
    cash_pct = (bal / total * 100.0) if total > 0 else 0.0

    def _sum(types):
        return round(sum(r["base"] for r in rows if r["type"] in types and not r.get("opening")), 2)

    last = rows[-1] if rows else None
    return {
        "balance": bal, "invested": invested, "total": total,
        "cash_pct": cash_pct, "invested_pct": 100.0 - cash_pct if total > 0 else 0.0,
        "net_deposits": _sum(("Deposit", "Withdrawal")),
        "trade_flow": _sum(("Buy", "Sell")),
        "income": _sum(("Dividend", "Interest")),
        "fees_corrections": _sum(("Fee", "Adjustment")),
        "corrections": sum(1 for r in rows if r["type"] == "Adjustment" and not r.get("opening")),
        "count": len(rows),
        "last_date": last["date"] if last else None,
        "last_type": last["type"] if last else None,
        "fx_entries": sum(1 for r in rows if r.get("fx_source") in ("ecb", "manual")),
        "manual_fx": sum(1 for r in rows if r.get("fx_source") == "manual"),
        "negative": any(r["bal"] < -0.004 for r in rows),
    }


def filter_rows(rows: list[dict], group: str) -> list[dict]:
    types = FILTER_GROUPS.get(group)
    return rows if not types else [r for r in rows if r["type"] in types]


def export_frame(entries: list[dict] | None = None) -> pd.DataFrame:
    """The export_csv() rows as typed columns (dates as datetimes, amounts as
    floats) for the region-formatted spreadsheet export (i18n spec F-11)."""
    entries = load_ledger() if entries is None else entries
    base = portfolio.base_currency().lower()
    rows = []
    for r in replay(entries):
        amt = None if r["type"] == "Adjustment" or r.get("amount") is None else round(float(r["amount"]), 2)
        rows.append({"date": pd.to_datetime(r["date"], errors="coerce"), "type": r["type"], "amount": amt,
                     "currency": r.get("currency") or "", "fx_rate": float(r.get("fx_rate") or 1.0),
                     f"amount_{base}": round(float(r["base"]), 2), "note": r.get("note") or "",
                     "reference": r.get("ref_label") or "",
                     f"running_balance_{base}": round(float(r["bal"]), 2), "fx_source": r.get("fx_source") or ""})
    return pd.DataFrame(rows, columns=["date", "type", "amount", "currency", "fx_rate", f"amount_{base}",
                                       "note", "reference", f"running_balance_{base}", "fx_source"])


def export_csv(entries: list[dict] | None = None) -> bytes:
    """Full ledger history, oldest first, in base currency (spec §Export):
    date, type, amount, currency (original), FX rate applied, amount (base),
    note, linked trade/dividend reference, running balance — plus fx_source
    so a manually-entered rate stays flagged in the export too. An
    Adjustment's `amount` is blank; its base amount is the correction."""
    entries = load_ledger() if entries is None else entries
    base = portfolio.base_currency().lower()
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    w.writerow(["date", "type", "amount", "currency", "fx_rate", f"amount_{base}",
                "note", "reference", f"running_balance_{base}", "fx_source"])
    for r in replay(entries):
        amt = "" if r["type"] == "Adjustment" or r.get("amount") is None else f"{float(r['amount']):.2f}"
        w.writerow([r["date"], r["type"], amt, r.get("currency") or "",
                    f"{float(r.get('fx_rate') or 1.0):.6f}".rstrip("0").rstrip("."),
                    f"{r['base']:.2f}", r.get("note") or "", r.get("ref_label") or "",
                    f"{r['bal']:.2f}", r.get("fx_source") or ""])
    return buf.getvalue().encode("utf-8")
