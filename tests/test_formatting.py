"""Tests for uvalu/formatting.py's pure value formatters."""
from uvalu.formatting import fmt_eur, safe_pct


class TestFmtEur:
    def test_formats_value(self):
        assert fmt_eur(12.5) == "€12.50"

    def test_missing_value_is_dash(self):
        assert fmt_eur(None) == "—"
        assert fmt_eur(float("nan")) == "—"


class TestSafePct:
    def test_computes_percentage(self):
        assert safe_pct(25.0, 100.0) == 25.0

    def test_zero_denominator_returns_zero(self):
        assert safe_pct(25.0, 0) == 0
