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
import math
import threading
from datetime import date, datetime

import pandas as pd

import fx
import portfolio
from uvalu import logkit

TYPES = ("Deposit", "Withdrawal", "Buy", "Sell", "Dividend", "Fee", "Interest", "Adjustment")
MANUAL_TYPES = ("Deposit", "Withdrawal", "Fee", "Interest", "Adjustment")
_SIGN = {"Deposit": 1, "Withdrawal": -1, "Buy": -1, "Sell": 1,
         "Dividend": 1, "Fee": -1, "Interest": 1}

FILTER_GROUPS: dict[str, tuple[str, ...] | None] = {
    "All": None,
    "Deposits & withdrawals": ("Deposit", "Withdrawal"),
    "Trades": ("Buy", "Sell"),
    "Income": ("Dividend", "Interest"),
    "Fees & adjustments": ("Fee", "Adjustment"),
}

_FIELDS = ("id", "seq", "date", "type", "amount", "currency", "fx_rate", "fx_source",
           "fx_date", "amount_base", "target_balance", "delta_at_entry", "opening",
           "note", "ref_kind", "ref_id", "ref_label", "auto", "topup", "created_at")

_lock = threading.RLock()


class CashError(ValueError):
    """A ledger rule rejected the entry; the message is user-facing."""


# ── Formatting helpers (shared with the UI) ──────────────────────────────────

_SYMBOLS = {"EUR": "€", "USD": "$", "GBP": "£"}


def money(v: float, ccy: str = "EUR", dp: int = 2) -> str:
    """€1,234.56 / −€12.40 — the design's money format (minus sign U+2212)."""
    sym = _SYMBOLS.get(ccy, ccy + " ")
    sign = "−" if v < 0 else ""
    return f"{sign}{sym}{abs(v):,.{dp}f}"


def signed_money(v: float, ccy: str = "EUR", dp: int = 2) -> str:
    return ("+" if v >= 0 else "") + money(v, ccy, dp)


def fmt_date(iso: str | None) -> str:
    """'2026-07-01' → '01 Jul 2026'."""
    try:
        return pd.Timestamp(iso).strftime("%d %b %Y")
    except Exception:
        return str(iso or "")


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
        raise CashError("Enter a date, e.g. 07 Jul 2026.")
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
                         "Opening balance · migrated from earlier cash records",
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
            raise CashError(f"Enter the FX rate to convert {currency} to {base}.")
        return float(manual_rate), "manual", None
    q = fx.get_rate(currency, base, on)
    return q.rate, "ecb", q.rate_date.isoformat()


def blocked_message(low: float, base: str = "EUR") -> str:
    return (f"Blocked: this would take the cash balance to {money(low, base)}. "
            "Balance cannot go negative.")


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
        raise CashError("Enter an amount greater than zero.")
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
        raise CashError("Enter the corrected balance.")
    if math.isnan(target) or math.isinf(target):
        raise CashError("Enter the corrected balance.")
    if target < 0:
        raise CashError("Balance cannot go negative.")
    base = portfolio.base_currency()
    with _lock:
        entries = load_ledger()
        is_opening = not entries
        delta = round(target - balance_before(entries, d), 2)
        cand = _new_entry("Adjustment", d, None, base, 1.0, "base", None,
                          note.strip() or ("Opening balance" if is_opening else "Manual balance correction"),
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
    verb = "Bought" if kind == "Buy" else "Sold"
    note = f"{verb} {shares:g} {ticker} × {money(price, base)}"
    if fee:
        note += f" · fee {money(float(fee), base)}"
    label = f"{trade_id} · {ticker}"
    with _lock:
        entries = load_ledger()
        probe = {"id": "probe", "seq": 10 ** 12, "date": d.isoformat(), "type": kind,
                 "amount": amt, "amount_base": amt, "fx_rate": 1.0}
        topup = round(max(0.0, -min_balance_after(entries, probe)), 2)
        posted: list[dict] = []
        if topup > 0:
            posted.append(_new_entry("Deposit", d, topup, base, 1.0, "base", None,
                                     f"Auto top-up to fund {label}",
                                     ref_kind="trade", ref_id=trade_id, ref_label=label,
                                     auto=True, topup=True))
        posted.append(_new_entry(kind, d, amt, base, 1.0, "base", None, note,
                                 ref_kind="trade", ref_id=trade_id, ref_label=label, auto=True))
        entries.extend(posted)
        save_ledger(entries)
    logkit.data_mutation(actor=logkit.user_id(), action="cash.post_trade", entity_type="cash",
                         entity_id=trade_id, type=kind, topup=bool(topup))
    return posted


def remove_ref(ref_kind: str, ref_id: str) -> int:
    """Delete every entry linked to one trade/dividend (used to roll back a
    trade whose position write failed). Returns the number removed."""
    with _lock:
        entries = load_ledger()
        kept = [e for e in entries if not (e.get("ref_kind") == ref_kind and e.get("ref_id") == ref_id)]
        n = len(entries) - len(kept)
        if n:
            save_ledger(kept)
    return n


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
            kind = "special" if str(row.get("div_type")) == "Special" else "cash"
            name = str(_clean(row.get("name")) or ticker)
            wanted[str(row["div_id"])] = {
                "date": pay.date(), "amount": net, "currency": ccy,
                "note": f"{name} · {kind} dividend, net of tax",
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
            if e.get("amount") != w["amount"] or e.get("note") != w["note"] or e.get("ref_label") != w["label"]:
                e = {**e, "amount": w["amount"], "note": w["note"], "ref_label": w["label"]}
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
                                  ref_label=w["label"], auto=True))
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
