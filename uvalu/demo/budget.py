"""The EODHD call budget (demo spec N-01, demo-mode plan "API budget").

The free plan allows 20 calls a day per key. The counter stops at 18 so a
retry or a hand-run check never hits the hard limit, and each run has its own
cap on top (default 12). Every call is counted *before* it is made and saved
straight away, so a crash mid-run still leaves the right count on disk.

The counter lives in ``demo-data/budget.json`` and only knows about runs that
save it. The limit is per key, not per machine: a local live run and the
GitHub Action share the same 20 calls.

Days are UTC days (EODHD resets its counter at midnight GMT).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

DAILY_LIMIT = 20
STOP_AT = 18
RUN_CAP = 12          # a weekday run is 11 calls (10 tickers + the benchmark index)


class BudgetExhausted(Exception):
    """No call left: our own stop (daily or per run) or EODHD's limit reply."""


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


@dataclass
class Budget:
    path: Path
    stop_at: int = STOP_AT
    run_cap: int = RUN_CAP
    day: str = field(default_factory=_today)
    calls_today: int = 0
    calls_this_run: int = 0

    def __post_init__(self) -> None:
        try:
            state = json.loads(Path(self.path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            state = {}
        if state.get("day") == self.day:
            self.calls_today = int(state.get("calls", 0))

    @property
    def remaining(self) -> int:
        return max(0, min(self.stop_at - self.calls_today, self.run_cap - self.calls_this_run))

    def spend(self, n: int = 1) -> None:
        """Count ``n`` calls about to be made, or raise BudgetExhausted."""
        if self.calls_today + n > self.stop_at:
            raise BudgetExhausted(f"daily stop reached: {self.calls_today} of {self.stop_at} "
                                  f"calls used on {self.day} (EODHD limit {DAILY_LIMIT})")
        if self.calls_this_run + n > self.run_cap:
            raise BudgetExhausted(f"run cap reached: {self.calls_this_run} of {self.run_cap} calls")
        self.calls_today += n
        self.calls_this_run += n
        self.save()

    def exhaust(self) -> None:
        """EODHD said the limit is reached: record that, so no later run today tries."""
        self.calls_today = max(self.calls_today, self.stop_at)
        self.save()

    def save(self) -> None:
        p = Path(self.path)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps({"day": self.day, "calls": self.calls_today,
                                   "stop_at": self.stop_at, "limit": DAILY_LIMIT}, indent=2) + "\n",
                       encoding="utf-8")
        tmp.replace(p)
