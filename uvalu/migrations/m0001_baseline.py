"""Schema 1 — the data layout as of October 2026, before versioned migrations.

Changes nothing. Existing installations are recorded at schema 1 on their first
start with migrations. Older shapes that predate it (pre-v1 cash.json rows,
legacy dividend-history columns) are still upgraded lazily on read by
cash._migrate and portfolio._migrate_div_hist; new layout changes go through
numbered migrations only.
"""
NUMBER = 1
DESCRIPTION = "Baseline: data layout of October 2026"


def up(ctx) -> None:
    pass


def down(ctx) -> None:  # nothing below the baseline; present so the rules stay uniform
    pass
