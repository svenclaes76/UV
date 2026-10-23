"""A minimal EODHD client for the demo refresh job (demo-mode plan DM-3).

Only the two endpoints the demo uses, 1 call each: end-of-day prices
(``/eod/{SYMBOL}``) and dividends (``/div/{SYMBOL}``). One request returns the
whole date range asked for, so the daily run re-asks for the full year: same
cost, and the adjusted closes stay consistent after a dividend.

Every call goes through the Budget first. The API token is never logged: it
isn't in the logged params, and network errors are re-raised without the
request URL (requests puts the full URL, query string included, in its
exception messages).

Only tools/demo_refresh.py uses this; the app never does.
"""
from __future__ import annotations

import os
from typing import Callable

import requests

from uvalu import logkit
from uvalu.demo.budget import Budget, BudgetExhausted

API_BASE = os.environ.get("UVALU_EODHD_API", "https://eodhd.com/api").rstrip("/")
TIMEOUT_S = 30.0

# A transport takes (url, params) and returns (status, parsed JSON or None).
Transport = Callable[[str, dict], "tuple[int, object]"]


class EodhdError(Exception):
    """Any EODHD failure; the message never contains the token."""


class NotFound(EodhdError):
    """404: the code is wrong or EODHD doesn't cover it. Not worth a retry."""


class AuthError(EodhdError):
    """401/403: bad key, or the plan doesn't cover this request."""


class Transient(EodhdError):
    """Network error, timeout or 5xx: one retry may help."""


def requests_transport(url: str, params: dict) -> "tuple[int, object]":
    try:
        r = requests.get(url, params=params, timeout=TIMEOUT_S)
    except requests.RequestException as exc:
        # Not `from exc`, and not str(exc): both carry the URL with the token.
        raise Transient(f"network error: {type(exc).__name__}") from None
    try:
        body = r.json() if r.status_code == 200 else None
    except ValueError:
        body = None
    return r.status_code, body


class Client:
    def __init__(self, token: str, budget: Budget, transport: "Transport | None" = None):
        if not token:
            raise AuthError("no EODHD API key (set EODHD_API_KEY)")
        self._token = token
        self.budget = budget
        self._transport = transport or requests_transport

    def _get(self, endpoint: str, symbol: str, params: dict) -> list:
        self.budget.spend(1)
        url = f"{API_BASE}/{endpoint}/{symbol}"
        with logkit.external_call(f"eodhd.{endpoint}", params={"symbol": symbol, **params},
                                  logger="uvalu.demo") as call:
            try:
                status, body = self._transport(url, {**params, "fmt": "json", "api_token": self._token})
            except Transient:
                call.note(status="network")
                raise
            if status != 200:
                call.note(status=str(status))
        if status == 404:
            raise NotFound(f"{symbol}: not found at EODHD")
        if status in (401, 403):
            raise AuthError(f"{symbol}: EODHD refused the key or the plan ({status})")
        if status in (402, 429):
            self.budget.exhaust()
            raise BudgetExhausted(f"EODHD reports the daily limit is reached ({status})")
        if status >= 500 or status != 200:
            raise Transient(f"{symbol}: EODHD returned {status}")
        if not isinstance(body, list):
            raise Transient(f"{symbol}: unexpected EODHD response")
        return body

    def eod(self, symbol: str, start: str, end: str) -> list:
        """Daily bars from ``start`` to ``end`` (ISO dates): dicts with date,
        open, high, low, close, adjusted_close, volume."""
        return self._get("eod", symbol, {"from": start, "to": end, "period": "d"})

    def dividends(self, symbol: str, start: str) -> list:
        """Dividends since ``start``: dicts with date, value, unadjustedValue,
        currency, paymentDate, ..."""
        return self._get("div", symbol, {"from": start})
