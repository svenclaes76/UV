"""Approximate cash-session clock for the European exchanges this app covers.

Euronext (Brussels / Amsterdam / Paris / Milan), Deutsche Börse Xetra and SIX
Swiss all run a continuous session roughly 09:00–17:30 Central European Time on
weekdays. This module answers "is that window open right now?" for the live
price feed's refresh cadence (uvalu/ui.py's price_autorefresh) and its cache
TTL bucket (uvalu/data.py's _price_bucket).

Deliberately simple: no exchange-holiday calendar, and one shared window rather
than per-exchange open/close times. This matches the rest of the app's
naive-time posture (see the "Live ·" note in uvalu/shell.py); the only cost of
being wrong on a holiday is that the price feed keeps polling at its normal
cadence instead of backing off.
"""
from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

_TZ    = ZoneInfo("Europe/Brussels")   # CET/CEST, DST handled by the tz database
_OPEN  = time(9, 0)
_CLOSE = time(17, 30)


def is_market_hours(now: datetime | None = None) -> bool:
    """True when the shared 09:00–17:30 CET/CEST weekday window is open.

    `now` defaults to the current time. A tz-aware value is converted to
    Brussels time; a naive value is assumed to already be in that zone.
    """
    if now is None:
        now = datetime.now(_TZ)
    elif now.tzinfo is not None:
        now = now.astimezone(_TZ)

    if now.weekday() >= 5:          # Saturday / Sunday
        return False
    return _OPEN <= now.time() <= _CLOSE
