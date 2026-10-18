"""D13 / EX-33: dividend withholding per country of the company, the §5b
defaults, and migration m0003."""
import pytest

import settings
from uvalu import withholding
from uvalu.migrations import m0003_withholding_by_country as m0003
from uvalu.migrations import runner


@pytest.mark.parametrize("country, rate", [
    ("Netherlands", 15.0), ("France", 12.8), ("Germany", 26.375), ("Switzerland", 35.0),
    ("United Kingdom", 0.0), ("Belgium", 0.0), ("Atlantis", 0.0), (None, 0.0),
])
def test_default_rates(country, rate):
    assert withholding.default_rate(country) == rate


def test_own_rate_wins_except_for_belgium():
    own = {"France": 25.0, "Belgium": 30.0}
    assert withholding.rate_for("France", own) == 25.0
    assert withholding.rate_for("Italy", own) == 26.0
    assert withholding.rate_for("Belgium", own) == 0.0     # the Belgian layer is separate


def test_company_country_beats_the_exchange():
    """Airbus trades in Paris but is Dutch: the Netherlands rate applies."""
    assert withholding.company_country("AIR.PA", "Netherlands") == "Netherlands"
    assert withholding.company_country("AIR.PA") == "France"        # nothing known: the exchange's country
    assert withholding.company_country("AAPL") is None


def test_settings_lookup_by_ticker(monkeypatch):
    monkeypatch.setattr(settings, "load_settings", lambda email="": {"withholding_by_country": {"Switzerland": 15.0}})
    assert settings.get_dividend_withholding("NESN.SW") == 15.0
    assert settings.get_dividend_withholding("AIR.PA", country="Netherlands") == 15.0
    assert settings.get_dividend_withholding("SAP.DE") == 26.375
    assert settings.get_dividend_withholding("UCB.BR") == 0.0
    assert settings.get_dividend_withholding(None) == 0.0


def test_country_names_are_translated():
    assert withholding.country_name("Germany", "de") == "Deutschland"
    assert withholding.country_name("Netherlands", "fr") == "Pays-Bas"
    assert withholding.country_name("Belgium", "nl") == "België"


def test_every_default_has_an_iso_code():
    for country, (iso, rate) in withholding.STATUTORY.items():
        assert len(iso) == 2 and 0 <= rate <= 50, country


class TestMigration:
    @pytest.fixture
    def ctx(self, tmp_path, monkeypatch):
        # Hermetic like the rest of the suite: CI has no .env (tests.yml).
        monkeypatch.setenv("ENCRYPTION_KEY", "unit-test-key-123")
        c = runner.MigrationContext(tmp_path / "data", tmp_path / "cache")
        (c.data_dir / "settings").mkdir(parents=True)
        return c

    def _write(self, ctx, name, data):
        path = ctx.data_dir / "settings" / name
        ctx.write_json(path, data)
        return path

    def test_up_moves_rates_to_countries(self, ctx):
        user = self._write(ctx, "user.json", {"language": "nl", "dividend_withholding": {
            "brussels": 0.0, "amsterdam": 15.0, "paris": 25.0, "milan": 26.0,
            "frankfurt": 26.4, "swiss": 0.0}})
        shared = self._write(ctx, "shared.json", {"enabled_exchanges": ["brussels"]})
        m0003.up(ctx)
        data = ctx.read_json(user)
        assert data["withholding_by_country"] == {"Netherlands": 15.0, "France": 25.0, "Italy": 26.0,
                                                  "Germany": 26.4}
        assert "dividend_withholding" not in data and data["language"] == "nl"
        assert ["France", 25.0] in data["withholding_moved"]
        assert ctx.read_json(shared) == {"enabled_exchanges": ["brussels"]}     # untouched

    def test_down_puts_them_back(self, ctx):
        user = self._write(ctx, "user.json", {"dividend_withholding": {"paris": 25.0}})
        m0003.up(ctx)
        m0003.down(ctx)
        data = ctx.read_json(user)
        assert data["dividend_withholding"]["paris"] == 25.0
        assert "withholding_by_country" not in data and "withholding_moved" not in data

    def test_up_is_safe_to_run_twice(self, ctx):
        user = self._write(ctx, "user.json", {"dividend_withholding": {"paris": 25.0}})
        m0003.up(ctx)
        m0003.up(ctx)
        assert ctx.read_json(user)["withholding_by_country"] == {"France": 25.0}
