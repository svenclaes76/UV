"""Tests for the hand-entered demo fundamentals (demo-mode plan DM-4):
the validator, the template and every committed file."""
import copy
import json
from pathlib import Path

import pytest

from tools import demo_fundamentals
from uvalu.demo import fundamentals, universe

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "demo-data"
ABI = fundamentals.load(fundamentals.path_for(DATA, "ABI.BR"))


def _errors(doc, **kw):
    return [p for p in fundamentals.validate(doc, **kw) if p.level == "error"]


@pytest.mark.parametrize("ticker", [t for t in universe.STOCKS
                                    if fundamentals.path_for(DATA, t).exists()])
def test_every_committed_file_is_valid(ticker):
    doc = fundamentals.load(fundamentals.path_for(DATA, ticker))
    assert _errors(doc, file_ticker=ticker) == []


def test_abi_is_clean_and_dated():
    assert fundamentals.validate(ABI, file_ticker="ABI.BR") == []
    assert fundamentals.as_of(ABI) == "2025-12-31"
    assert ABI["reporting_currency"] == "USD" and ABI["dividend_currency"] == "EUR"


def _mutated(fn):
    doc = copy.deepcopy(ABI)
    fn(doc)
    return doc


@pytest.mark.parametrize("change, where", [
    (lambda d: d.update(ticker="VWCE.DE"), "ticker"),                 # the benchmark has no fundamentals
    (lambda d: d.update(reporting_currency="usd"), "reporting_currency"),
    (lambda d: d.update(fiscal_year_end="31-12"), "fiscal_year_end"),
    (lambda d: d.pop("sources"), "sources"),
    (lambda d: d["years"].pop(), "years"),                            # only 2 years left
    (lambda d: d["years"].reverse(), "years"),                        # oldest first
    (lambda d: d["years"][0].pop("revenue"), "years[0].revenue"),
    (lambda d: d["years"][0]["cfo"].update(value=None), "years[0].cfo"),
    (lambda d: d["years"][0]["cfo"].update(value="14 883"), "years[0].cfo"),
    (lambda d: d["years"][0]["cfo"].update(source="ar25"), "years[0].cfo"),
    (lambda d: d["years"][0]["cfo"].update(page=""), "years[0].cfo"),
    (lambda d: d["years"][0]["capex"].update(value=-3656), "years[0].capex"),
    (lambda d: d["years"][0]["ebit"].update(value=15405000), "years[0].ebit"),       # unit slip
    (lambda d: d["years"][0]["equity"].update(value=300000), "years[0].equity"),
    (lambda d: d["years"][0]["eps_basic"].update(value=34.5), "years[0].eps_basic"), # typo
])
def test_validator_catches(change, where):
    errs = _errors(_mutated(change))
    assert any(p.where == where for p in errs), errs


def test_file_name_must_match_ticker():
    assert any(p.where == "ticker" for p in _errors(ABI, file_ticker="KBC.BR"))


def test_optional_fields_may_be_null():
    doc = _mutated(lambda d: d["years"][2]["dps"].update(value=None))
    assert _errors(doc) == []


def test_bank_statements_skip_industrial_fields():
    def as_bank(d):
        d["statement_type"] = "bank"
        for y in d["years"]:
            for f in ("ebit", "cfo", "capex", "current_assets", "current_liabilities"):
                y.pop(f)
    assert _errors(_mutated(as_bank)) == []
    industrial = _mutated(lambda d: d["years"][0].pop("cfo"))
    assert any(p.where == "years[0].cfo" for p in _errors(industrial))
    assert any(p.where == "statement_type" for p in _errors(_mutated(lambda d: d.update(statement_type="insurer"))))


def test_small_eps_gap_is_only_a_warning():
    doc = _mutated(lambda d: d["years"][0]["eps_basic"].update(value=3.55))   # ~3% off
    problems = fundamentals.validate(doc)
    assert not [p for p in problems if p.level == "error"]
    assert any(p.where == "years[0].eps_basic" and p.level == "warning" for p in problems)


def test_template_is_complete_but_fails_until_filled():
    doc = fundamentals.template("KBC.BR")
    assert doc["ticker"] == "KBC.BR" and len(doc["years"]) == 3
    assert set(doc["years"][0]) == {"fiscal_year", *fundamentals.FIELDS}
    assert _errors(doc)                              # empty values are errors


def test_check_tool_reports_coverage_and_errors(tmp_path):
    root = tmp_path / "demo-data"
    path = fundamentals.path_for(root, "ABI.BR")
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(ABI), encoding="utf-8")
    lines = []
    assert demo_fundamentals.check(["ABI.BR"], root, lines.append) == 0
    assert any("Coverage: 1 of 9" in l for l in lines)

    broken = _mutated(lambda d: d["years"][0].pop("revenue"))
    path.write_text(json.dumps(broken), encoding="utf-8")
    assert demo_fundamentals.check(["ABI.BR"], root, lines.append) == 1
