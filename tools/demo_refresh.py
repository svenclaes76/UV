"""Refresh the demo snapshot in ``demo-data/`` from EODHD and the ECB.

Demo-mode plan DM-3. The only code that calls EODHD: the demo app, the tests
and CI never do. Without ``--live`` nothing is called and nothing is written;
the script prints the calls it would make and the budget left.

    python tools/demo_refresh.py                          # dry run (default)
    python tools/demo_refresh.py --live --tickers ABI.BR  # first live check, 1 call
    python tools/demo_refresh.py --live                   # prices + FX, 11 calls
    python tools/demo_refresh.py --live --dividends       # dividends only, 10 calls

Each price request asks for the whole last year: one call either way, and the
adjusted closes stay consistent after a dividend. FX comes from the ECB via
frankfurter (fx.py) and costs no EODHD call.

The key comes from ``EODHD_API_KEY`` (the GitHub Actions secret, or your local
.env). Exit codes: 0 all done, 1 some tickers failed, 2 stopped (budget or key).
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from uvalu import logkit  # noqa: E402
from uvalu.demo import store, universe  # noqa: E402
from uvalu.demo.budget import RUN_CAP, Budget, BudgetExhausted  # noqa: E402
from uvalu.demo.eodhd import AuthError, Client, EodhdError, NotFound, Transient  # noqa: E402

_log = logkit.get_logger("uvalu.demo")

HISTORY_DAYS = 366          # the free plan's 1 year
DIVIDEND_DAYS = 3 * 366     # the free plan returns what it has; ask wide


def _fx_rates(currencies, start, end):
    import fx
    return fx.rates_frame(currencies, start, end)


def _call(fn, *args):
    """One call, plus one retry on a network error or 5xx (each costs a call)."""
    try:
        return fn(*args)
    except Transient:
        return fn(*args)


def run(*, root: Path, tickers: list[str], prices: bool, dividends: bool, fx: bool,
        live: bool, max_calls: int = RUN_CAP, token: str = "", transport=None,
        fx_rates=_fx_rates, today=None, out=print) -> int:
    today = today or datetime.now(timezone.utc).date()
    start, end = (today - timedelta(days=HISTORY_DAYS)).isoformat(), today.isoformat()
    budget = Budget(Path(root) / "budget.json", run_cap=max_calls)
    plan = [(t, universe.eodhd_code(t)) for t in tickers]
    n_calls = sum(int(prices) + int(dividends and t not in universe.INDEX_SERIES) for t in tickers)

    if not live:
        out(f"Dry run, nothing called or written. Window {start} to {end}.")
        for t, code in plan:
            jobs = [j for j, on in (("eod", prices),
                                    ("div", dividends and t not in universe.INDEX_SERIES)) if on]
            out(f"  {t:<10} -> {code:<12} {', '.join(jobs) or '-'}")
        out(f"  FX (ECB, no EODHD call): {', '.join(universe.currencies()) if fx else '-'}")
        out(f"Would use {n_calls} calls; {budget.calls_today} used today, "
            f"{budget.remaining} left (stop at {budget.stop_at}, run cap {budget.run_cap}).")
        return 0

    client = Client(token, budget, transport)
    status = store.read_refresh(root)
    last_bars = dict(status.get("last_bar") or {})
    errors: dict[str, str] = {}
    updated: list[str] = []
    stopped = False

    for t, code in plan:
        if stopped:
            break
        try:
            if prices:
                new, last = store.write_eod(root, t, _call(client.eod, code, start, end))
                if last:
                    last_bars[t] = last
                if new:
                    updated.append(t)
                out(f"  {t:<10} {code:<12} prices: {new} new bar(s), last {last or '-'}")
            if dividends and t not in universe.INDEX_SERIES:
                since = (today - timedelta(days=DIVIDEND_DAYS)).isoformat()
                new = store.write_dividends(root, t, _call(client.dividends, code, since))
                out(f"  {t:<10} {code:<12} dividends: {new} new")
        except (BudgetExhausted, AuthError) as exc:
            errors[t] = str(exc)
            out(f"  {t:<10} STOPPED: {exc}")
            stopped = True
        except (NotFound, EodhdError) as exc:
            errors[t] = str(exc)
            out(f"  {t:<10} failed: {exc}")

    fx_rows = 0
    if fx and not stopped:
        try:
            fx_rows = store.write_fx(root, fx_rates(universe.currencies(), start, end))
            out(f"  FX: {fx_rows} day(s) of {', '.join(universe.currencies())}")
        except Exception as exc:              # fx.py already logged the cause
            errors["fx"] = f"FX: {type(exc).__name__}"
            out(f"  FX failed: {type(exc).__name__}")

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    status.update({
        "source": "EODHD end-of-day; ECB reference rates via frankfurter",
        "last_bar": last_bars,
        "last_run": {"at": now, "calls": budget.calls_this_run, "updated": updated,
                     "errors": errors, "prices": prices, "dividends": dividends, "fx": fx},
    })
    if updated or fx_rows:
        status["refreshed_at"] = now
    store.write_refresh(root, status)

    _log.info("demo refresh done", extra={
        "event": "demo_refresh.done", "calls": budget.calls_this_run,
        "calls_today": budget.calls_today, "updated": updated, "errors": errors})
    out(f"Done: {budget.calls_this_run} call(s) this run, {budget.calls_today} today; "
        f"{len(updated)} ticker(s) updated, {len(errors)} error(s).")
    return 2 if stopped else (1 if errors else 0)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--live", action="store_true", help="really call EODHD and write files")
    ap.add_argument("--tickers", help="comma-separated stored tickers or index keys "
                                      "(default: the 10 tickers and the benchmark index)")
    ap.add_argument("--prices", action="store_true", help="end-of-day prices")
    ap.add_argument("--dividends", action="store_true", help="dividends")
    ap.add_argument("--fx", action="store_true", help="ECB FX rates (no EODHD call)")
    ap.add_argument("--max-calls", type=int, default=RUN_CAP, help="cap for this run")
    ap.add_argument("--out", type=Path, default=ROOT / "demo-data", help="snapshot folder")
    a = ap.parse_args(argv)

    tickers = [t.strip() for t in a.tickers.split(",")] if a.tickers else list(universe.SERIES)
    unknown = [t for t in tickers if t not in universe.SERIES]
    if unknown:
        ap.error(f"not in the demo universe: {', '.join(unknown)}")
    prices, dividends, fx = a.prices, a.dividends, a.fx
    if not (prices or dividends or fx):
        prices, fx = True, True

    logkit.init_logging(synchronous=True)
    token = ""
    if a.live:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
        token = os.environ.get("EODHD_API_KEY", "").strip()
    try:
        return run(root=a.out, tickers=tickers, prices=prices, dividends=dividends, fx=fx,
                   live=a.live, max_calls=a.max_calls, token=token)
    except AuthError as exc:
        print(f"Stopped: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
