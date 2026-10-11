"""Schema 2 — drop stored fields nothing uses, fill missing dividend currencies.

Positions and sold records lose ``google_ticker`` and ``target_price`` (left
over from the founder's original Excel import) and ``account`` (never had an
input). Dividend records lose ``google_ticker``, ``declaration_date``, ``record_date``,
``reinvested`` and ``reinvested_shares`` (their inputs were removed in
Dividend Management v2). A dividend without a currency gets its exchange's
currency (.SW → CHF, otherwise EUR): those rows were read as EUR, so Swiss
dividends were counted in the wrong currency. Decision IE5 in
docs/import-export-plan.md.

Irreversible: the dropped values carry no information the app could use.
"""
NUMBER = 2
DESCRIPTION = "Drop unused position/dividend fields; fill missing dividend currencies"

_TRADE_FIELDS = ("google_ticker", "target_price", "account")
_DIVIDEND_FIELDS = ("google_ticker", "declaration_date", "record_date", "reinvested", "reinvested_shares")


def _currency(ticker) -> str:
    return "CHF" if str(ticker or "").endswith(".SW") else "EUR"


def _blank(v) -> bool:
    return v is None or (isinstance(v, float) and v != v) or str(v).strip() in ("", "None", "nan")


def up(ctx) -> None:
    for udir in ctx.user_dirs():
        for name in ("portfolio.json", "sold.json"):
            path = udir / name
            if not path.exists():
                continue
            rows = ctx.read_json(path)
            if not isinstance(rows, list):
                continue
            if any(f in r for r in rows if isinstance(r, dict) for f in _TRADE_FIELDS):
                ctx.write_json(path, [{k: v for k, v in r.items() if k not in _TRADE_FIELDS}
                                      if isinstance(r, dict) else r for r in rows])
        path = udir / "dividends_history.json"
        if not path.exists():
            continue
        rows = ctx.read_json(path)
        if not isinstance(rows, list):
            continue
        changed = False
        out = []
        for r in rows:
            if not isinstance(r, dict):
                out.append(r)
                continue
            new = {k: v for k, v in r.items() if k not in _DIVIDEND_FIELDS}
            if _blank(new.get("currency")):
                new["currency"] = _currency(new.get("ticker"))
            changed = changed or new != r
            out.append(new)
        if changed:
            ctx.write_json(path, out)
