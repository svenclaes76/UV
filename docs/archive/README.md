# Archived implementation plans

These are point-in-time planning documents written before or during specific
pieces of work. Every one below is self-labeled complete and the described
work has shipped (confirmed against `CHANGELOG.md`) — they're kept here for
historical rationale (why a decision was made, what was deliberately
deferred), not as living references. **For current behavior, use the linked
doc instead** — these are not updated as the code evolves and can drift out
of sync with it.

| File | What it planned | Current reference |
|---|---|---|
| [`stock_valuation_improvement_plan.md`](stock_valuation_improvement_plan.md) | WS-10…WS-18 valuation-engine workstreams (statement history, sector/PEG PE, graduated DDM, composite-weight rebalance) | [`../stock_valuation_algorithm.md`](../stock_valuation_algorithm.md) |
| [`valuation_fv_coverage_plan.md`](valuation_fv_coverage_plan.md) | FV-1…FV-8 fair-value coverage overhaul (DDM/EPV no longer vanishing for trough-earnings payers) | [`../stock_valuation_algorithm.md`](../stock_valuation_algorithm.md), [`../data-contracts.md`](../data-contracts.md) |
| [`logging-implementation-plan.md`](logging-implementation-plan.md) | Phased rollout of the `uvalu/logkit/` structured-logging subsystem | [`../logging.md`](../logging.md) |
| [`uvalu-auth-implementation-plan.md`](uvalu-auth-implementation-plan.md) | Original pre-build auth proposal — note this describes a different technical design (SQL `users` table, `argon2-cffi`) than what actually shipped (bcrypt + encrypted JSON store, `linked_identities`); kept for the original design rationale only, not as a spec | [`../architecture.md`](../architecture.md) (`auth.py` section), `CHANGELOG.md` 1.8.0 |
| [`valuation_audit_plan.md`](valuation_audit_plan.md) | Design of the standalone valuation/risk accuracy audit tool | `tools/valuation_audit.py` (see its own docstring + `CONTRIBUTING.md`) |

## Why archived instead of deleted

Each of these captures *why* a decision was made (rejected alternatives,
tradeoffs, what was deliberately deferred and why) that a living reference
doc doesn't carry — that context is worth keeping searchable rather than
relying on git archaeology. If a plan doc turns out to have nothing worth
keeping beyond what the current reference already says, delete it outright
instead of archiving it.
