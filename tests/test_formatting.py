"""Tests for uvalu/formatting.py's pure value formatters."""
import pandas as pd

from uvalu.formatting import fmt_eur, fmt_div_flag, safe_pct, f_str


class TestFmtEur:
    def test_formats_value(self):
        assert fmt_eur(12.5) == "€12.50"

    def test_missing_value_is_dash(self):
        assert fmt_eur(None) == "—"
        assert fmt_eur(float("nan")) == "—"


class TestFmtDivFlag:
    def test_at_risk(self):
        assert fmt_div_flag("At Risk") == "At Risk"

    def test_ok(self):
        assert fmt_div_flag("OK") == "OK"

    def test_blank_is_dash(self):
        assert fmt_div_flag("") == "—"

    def test_missing_is_dash(self):
        assert fmt_div_flag(None) == "—"
        assert fmt_div_flag(float("nan")) == "—"

    def test_unknown_value_is_dash(self):
        assert fmt_div_flag("Something Else") == "—"


class TestSafePct:
    def test_computes_percentage(self):
        assert safe_pct(25.0, 100.0) == 25.0

    def test_zero_denominator_returns_zero(self):
        assert safe_pct(25.0, 0) == 0


class TestFStr:
    def test_passes_through_value(self):
        assert f_str("hello") == "hello"
        assert f_str(5) == 5

    def test_missing_is_dash(self):
        assert f_str(None) == "—"
        assert f_str(float("nan")) == "—"
