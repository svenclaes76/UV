"""Draft an update of the risk-free snapshot (uvalu/risk_free_rates.json).

Exchange expansion plan EX-W5b, decisions D33 and EX2: the risk-free rate of
each quote currency is the 10-year government bond yield from the OECD's
"Long-term interest rates" series (IRLT, monthly, percent per annum); EUR uses
Germany's. The snapshot is committed with its date and refreshed each quarter,
together with the index snapshot (open items EX6, EX10). This script drafts
that refresh; it never runs in the app.

Usage:
    python tools/refresh_risk_free.py            # fetch, print the diff, write nothing
    python tools/refresh_risk_free.py --write    # also write uvalu/risk_free_rates.json

The latest month with a value is taken per country. A country without a
recent value is printed and left out (Iceland has no OECD series today); the
app then keeps that currency's stocks out of Undervalued. A month older than
four months is flagged: check it before --write. The OECD's reuse terms go
with the data-licensing questions (L29, L30).
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "uvalu" / "risk_free_rates.json"

# Quote currency → OECD reference area of its 10-year government bond.
COUNTRIES = {
    "EUR": "DEU",   # the Bund (EX2)
    "CHF": "CHE",
    "GBP": "GBR",
    "SEK": "SWE",
    "DKK": "DNK",
    "NOK": "NOR",
    "ISK": "ISL",
    "PLN": "POL",
}

URL = ("https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_FINMARK,4.0/"
       "{areas}.M.IRLT.PA.....?startPeriod={start}&dimensionAtObservation=AllDimensions"
       "&format=csvfilewithlabels")
SOURCE = "OECD, Long-term interest rates (IRLT, 10-year government bonds, monthly)"
STALE_MONTHS = 4


def fetch(start: str) -> dict[str, tuple[str, float]]:
    """{OECD area: (latest period, value in percent)}."""
    url = URL.format(areas="+".join(COUNTRIES.values()), start=start)
    resp = requests.get(url, timeout=60, headers={"User-Agent": "uvalu refresh_risk_free"})
    resp.raise_for_status()
    latest: dict[str, tuple[str, float]] = {}
    for row in csv.DictReader(io.StringIO(resp.text)):
        area, period, value = row.get("REF_AREA"), row.get("TIME_PERIOD"), row.get("OBS_VALUE")
        if not (area and period and value):
            continue
        if area not in latest or period > latest[area][0]:
            latest[area] = (period, float(value))
    return latest


def _months_between(period: str, today: date) -> int:
    y, m = (int(x) for x in period.split("-")[:2])
    return (today.year - y) * 12 + today.month - m


def build(today: date) -> dict:
    start = f"{today.year - 1}-{today.month:02d}"
    latest = fetch(start)
    rates = {}
    for ccy, area in COUNTRIES.items():
        if area not in latest:
            print(f"  {ccy} ({area}): no value since {start}, left out")
            continue
        period, pct = latest[area]
        age = _months_between(period, today)
        flag = f"  <- {age} months old, check" if age > STALE_MONTHS else ""
        print(f"  {ccy} ({area}): {pct:.2f}% for {period}{flag}")
        rates[ccy] = {"rate": round(pct / 100, 5), "country": area, "period": period}
    return {
        "_note": ("10-year government bond yield per quote currency; EUR = Germany. "
                  "Drafted by tools/refresh_risk_free.py, refreshed each quarter (EX10). "
                  "Never fetched at run time."),
        "source": SOURCE,
        "as_of": today.isoformat(),
        "rates": rates,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write", action="store_true", help="write the snapshot")
    args = ap.parse_args(argv)
    new = build(date.today())
    try:
        old = json.loads(SNAPSHOT.read_text(encoding="utf-8")).get("rates", {})
    except (OSError, ValueError):
        old = {}
    for ccy in sorted(set(old) | set(new["rates"])):
        a, b = old.get(ccy, {}).get("rate"), new["rates"].get(ccy, {}).get("rate")
        if a != b:
            print(f"  change {ccy}: {a} -> {b}")
    if args.write:
        SNAPSHOT.write_text(json.dumps(new, indent=2) + "\n", encoding="utf-8")
        print(f"written {SNAPSHOT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
