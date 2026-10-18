"""Check or start the hand-entered demo fundamentals (demo-mode plan DM-4).

    python tools/demo_fundamentals.py check              # every file in demo-data/fundamentals/
    python tools/demo_fundamentals.py check ABI.BR       # one stock
    python tools/demo_fundamentals.py template KBC.BR    # write an empty file to fill in

``check`` prints each problem and a coverage line (which demo stocks have a
file); exit code 1 when any file has an error. ``template`` refuses to
overwrite an existing file.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from uvalu.demo import fundamentals, universe  # noqa: E402

DATA = ROOT / "demo-data"


def check(tickers: list[str], root: Path = DATA, out=print) -> int:
    errors = 0
    for t in tickers:
        path = fundamentals.path_for(root, t)
        if not path.exists():
            continue
        try:
            doc = fundamentals.load(path)
        except ValueError as exc:
            out(f"{t}: error: not valid JSON ({exc})")
            errors += 1
            continue
        problems = fundamentals.validate(doc, file_ticker=t)
        n_err = sum(p.level == "error" for p in problems)
        errors += n_err
        status = "OK" if not problems else f"{n_err} error(s), {len(problems) - n_err} warning(s)"
        out(f"{t}: {status} (as of {fundamentals.as_of(doc) or '?'})")
        for p in problems:
            out(f"  {p}")
    have = [t for t in universe.STOCKS if fundamentals.path_for(root, t).exists()]
    missing = [t for t in universe.STOCKS if t not in have]
    out(f"Coverage: {len(have)} of {len(universe.STOCKS)} stocks"
        + (f"; missing: {', '.join(missing)}" if missing else ""))
    return 1 if errors else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("tickers", nargs="*")
    t = sub.add_parser("template")
    t.add_argument("ticker")
    a = ap.parse_args(argv)

    if a.cmd == "check":
        tickers = a.tickers or list(universe.STOCKS)
        bad = [x for x in tickers if x not in universe.STOCKS]
        if bad:
            ap.error(f"not a demo stock: {', '.join(bad)}")
        return check(tickers)

    if a.ticker not in universe.STOCKS:
        ap.error(f"not a demo stock: {a.ticker}")
    path = fundamentals.path_for(DATA, a.ticker)
    if path.exists():
        print(f"{path} already exists; not overwriting.")
        return 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(fundamentals.template(a.ticker), indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    print(f"Wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
