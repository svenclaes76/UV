"""Pure value formatters shared across pages."""
from uvalu.i18n import fmt_money


def fmt_eur(v) -> str:
    """Format a value as a Euro price in the region format, or '—' if missing."""
    return fmt_money(v, "EUR")


def safe_pct(numerator: float, denominator: float) -> float:
    """Return numerator/denominator*100, or 0 if denominator is zero."""
    return numerator / denominator * 100 if denominator else 0
