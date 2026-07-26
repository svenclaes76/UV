# Backend feature gaps (post-redesign audit)

Audited 2026-07-26, after the `feature/design-import-v3` redesign (PR #6) rebuilt every page's HTML/CSS. This document tracks backend capability that exists in the root-level modules but is not currently reachable through any page, dialog, or admin panel in `uvalu/`. It's a punch list for later work, not a bug report — some entries are intentional (documented as such below).

Verified by grepping every public symbol in each root module against `app.py` + all of `uvalu/**/*.py`.

## Priority candidates

### 1. Risk engine — three whole analysis stages never rendered

`risk.assess_portfolio()` (`risk.py:1070`) computes 8 stages on every run; [uvalu/pages_/risk.py](../uvalu/pages_/risk.py) only renders composite/quant/concentration/factor/position-level output. Entirely unsurfaced:

- **Income risk** (`IncomeRisk`, `risk.py:147-157`, computed at `risk.py:1116`) — `portfolio_yield`, `weighted_dgr`, `top3_income_shares`, `top3_cut_eur`/`pct`, `income_concentration_flag`, `flagged_payers`, `flagged_income_pct`.
- **Stress testing** (`StressResults`, `risk.py:180-186`, computed at `risk.py:1117`) — 4 historical crash scenarios (dot-com, GFC, COVID, 2022 rate hikes), factor scenarios (rate rise, recession, sector crash, credit crunch, dividend freeze), and a 10,000-path Monte Carlo simulation (`mc_1y`/`mc_3y`/`mc_5y`, `risk.py:824-849`: p05/p25/p50/p75/p95/prob_loss).
- **Rebalancing signals** (`RebalanceSignals`, `risk.py:205-209`, computed at `risk.py:1119`) — hard/soft triggers plus recommended `actions` (e.g. "trim position >20%", "reduce beta>1.5", "diversify income").
- Secondary fields left unused within the stages that *are* shown: `var_95_1d_eur`, `var_99_1d_eur`, `cvar_95_1d_eur` (`QuantMetrics`), `mdd_3y`, `mdd_5y`, `sortino`, `corr_matrix`, `high_corr_pairs`, `effective_diversification`, `returns_available`; `r_squared`, `alpha_annualised` (`FactorExposure`); `div_hhi`, `div_top3_pct` (`ConcentrationMetrics`); per-position `.mos`, `.valuation_flag`, `.div_sustainability`, `.financial_health`, `.earnings_quality`, `.var_95_1d_eur` (`PositionRisk`).

**Follow-up:** design a second risk-page section (or tab) for income risk + stress/Monte Carlo + rebalancing actions. This is the highest-value gap — fully computed, zero UI cost to prototype since no backend work is needed first.

### 2. Admin can't reset a user's password

`auth.reset_password(email, new_password)` (`auth.py:219`) exists but is not imported by [uvalu/pages_/admin.py](../uvalu/pages_/admin.py) (which imports `ROLES, list_users, set_role, set_status, delete_user, invite_user` only, `admin.py:30`). An Admin can invite/suspend/delete/change-role but has no way to reset an existing (non-`Invited`) user's password.

Note: [docs/architecture.md:163](architecture.md:163) currently claims `reset_password()` "surfaced in the Admin portal's Users tab" — that line is stale and should be corrected once this is either wired up or confirmed intentionally deferred.

### 3. Cash balances — fully invisible feature

`portfolio.save_cash()` / `load_cash()` (`portfolio.py:184-185`) have no UI anywhere (no display, no add/edit form) and aren't even in `backup.py`'s `_PORTFOLIO_FILENAMES` (`backup.py:32`), so cash data — if anyone starts using it — wouldn't survive a backup/restore cycle either.

### 4. Backup restore only works from history, not an arbitrary file

`backup.import_zip(zip_bytes, email)` (`backup.py:104-141`) is only ever called internally by `restore_backup()` against a backup-history entry (`admin.py:343-346`). There is no `st.file_uploader` for a `.zip` anywhere (unlike the Excel import at `settings.py:232`), so a backup downloaded to another machine, or an old manually-made archive, can't be fed back in through the UI.

## Smaller / lower-priority items

- **`screener.py` `TER %`** (Total Expected Return, `screener.py:728-733`) — computed for every scored row, shown on no page. Its tooltip text exists in `uvalu/formatting.py:22-25` (`COLUMN_HELP["TER %"]`) but that whole dict is unused (see below).
- **`portfolio.remove_positions()`** (`portfolio.py:82-87`) — dead code, not a missing feature: the UI (`uvalu/pages_/portfolio.py:360,473,556`) reimplements the same delete-then-save logic inline instead of calling it. Candidate for a cleanup pass (replace 3 call sites), not new UI work.
- **`uvalu/data.py` `_cache_age_str()`** (`uvalu/data.py:35-50`) — computes a "Cache age: X min" string, never called; Screener shows fetch progress instead.
- **`uvalu/formatting.py` `COLUMN_HELP`** (~40 tooltip entries) — entirely unused since `help.py` was rewritten to a signal-legend/FAQ layout during the redesign. `docs/architecture.md:130` still describes it as shown on the Help page — also stale.

## Confirmed intentional (not gaps)

- **`auth.register()`** (`auth.py:73`) — self-service signup is implemented but deliberately unused; `uvalu/authgate.py:169-176` documents invite-only as the product decision.
- **Notification alert toggles** (`settings._USER_DEFAULTS["alert_*"]`, `settings.py:49-51`) and **density setting** (`settings.py:46`) — both explicitly noted in `uvalu/pages_/settings.py` as removed-on-purpose; dead schema, not missing UI.
- **US-listed exchange toggle** (`settings._SHARED_DEFAULTS["us_listed_enabled"]`, `settings.py:42`) — shown in Settings as a disabled/no-op toggle; source comment says "not yet wired — no US ticker universe exists" yet.

## Method

For each root module (`auth.py`, `backup.py`, `crypto.py`, `fetch_tickers.py`, `portfolio.py`, `prices.py`, `risk.py`, `screener.py`, `settings.py`) and `uvalu/data.py`: enumerated public functions/classes, then grepped each symbol name across `uvalu/**/*.py` + `app.py`. Anything with zero matches (outside its own definition/internal callers) is listed above. Re-verify against current code before acting — this is a point-in-time snapshot, not a live view.
