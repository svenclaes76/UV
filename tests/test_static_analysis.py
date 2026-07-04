"""Static guard against undefined-name (F821) bugs across the app modules.

The AppTest smoke test only reaches page code on the no-portfolio path, so a
missing import inside a data-dependent page body (e.g. the dashboard risk
banner) escapes it and blows up at runtime. pyflakes catches that whole class
statically — this test fails if any module references an undefined name.
"""
from pathlib import Path

import pytest

pyflakes_api = pytest.importorskip("pyflakes.api")
from pyflakes import messages as pf_messages
from pyflakes.reporter import Reporter

PROJECT = Path(__file__).resolve().parents[1]
TARGETS = [PROJECT / "app.py", *(PROJECT / "uvalu").rglob("*.py")]


class _Collector(Reporter):
    """A pyflakes reporter that records only UndefinedName findings."""

    def __init__(self):
        self.undefined: list[str] = []

    def unexpectedError(self, filename, msg):  # noqa: N802 (pyflakes API)
        self.undefined.append(f"{filename}: {msg}")

    def syntaxError(self, filename, msg, lineno, offset, text):  # noqa: N802
        self.undefined.append(f"{filename}:{lineno}: syntax error: {msg}")

    def flake(self, message):  # noqa: N802 (pyflakes API)
        if isinstance(message, pf_messages.UndefinedName):
            self.undefined.append(str(message))


def test_no_undefined_names():
    collector = _Collector()
    for path in TARGETS:
        pyflakes_api.checkPath(str(path), collector)
    assert not collector.undefined, "Undefined names found:\n" + "\n".join(collector.undefined)
