"""Schema 3 — dividend withholding per country of the company, not per exchange.

Exchange expansion plan D13 / EX-33 (decided 17 Oct 2026). Withholding is
charged by the country a company is registered in, so the per-exchange table
(``dividend_withholding``: {"paris": 25.0, …}, every exchange starting at 0%)
becomes a per-country one (``withholding_by_country``: {"France": 25.0, …})
on top of each country's statutory default (uvalu/withholding.py).

Every non-zero per-exchange rate a user entered moves to that exchange's
country and stays their rate. A 0% rate is dropped: 0% was the old starting
value for every exchange, so it can't be told apart from "never set", and
the country's default now applies. Brussels is dropped too: Belgium's
withholding is the separate Belgian layer. The moved rates are listed in
``withholding_moved`` so Settings can show them once (D23).

Reversible: ``down`` puts the per-country rates back on their exchanges.
"""
NUMBER = 3
DESCRIPTION = "Dividend withholding per country of the company instead of per exchange"

# The six exchanges that existed with a per-exchange rate, and their country.
_EXCHANGE_COUNTRY = {
    "brussels": "Belgium", "amsterdam": "Netherlands", "paris": "France",
    "milan": "Italy", "frankfurt": "Germany", "swiss": "Switzerland",
}
_OLD, _NEW, _MOVED = "dividend_withholding", "withholding_by_country", "withholding_moved"


def _user_settings(ctx):
    for path in ctx.settings_files():
        if path.name == "shared.json":
            continue
        try:
            data = ctx.read_json(path)
        except Exception:
            continue
        if isinstance(data, dict):
            yield path, data


def up(ctx) -> None:
    for path, data in _user_settings(ctx):
        old = data.get(_OLD)
        if not isinstance(old, dict):
            continue
        own = dict(data.get(_NEW) or {})
        moved = []
        for key, rate in old.items():
            country = _EXCHANGE_COUNTRY.get(key)
            try:
                rate = float(rate)
            except (TypeError, ValueError):
                continue
            if not country or country == "Belgium" or rate == 0.0:
                continue
            own.setdefault(country, rate)
            moved.append([country, rate])
        data[_NEW] = own
        if moved:
            data[_MOVED] = moved
        data.pop(_OLD, None)
        ctx.write_json(path, data)


def down(ctx) -> None:
    back = {country: key for key, country in _EXCHANGE_COUNTRY.items()}
    for path, data in _user_settings(ctx):
        own = data.get(_NEW)
        if not isinstance(own, dict):
            continue
        data[_OLD] = {key: float(own.get(country, 0.0)) for country, key in back.items()}
        data.pop(_NEW, None)
        data.pop(_MOVED, None)
        ctx.write_json(path, data)
