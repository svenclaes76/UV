# Algorithm legal-compliance review

Oct 3, 2026 · reviewed against *Uvalu — Legal Requirements for Launch* (Oct 2, 2026)

This review covers the scoring and risk algorithms: `screener.py`, `risk.py`, `scoring.py` and `portfolio_enrichment.py`, plus the data-layer code that decides what they are given (`uvalu/data.py`). The original modules are **unchanged**. The fixes live in candidate copies that are not yet wired into the app:

| File | What it is |
| --- | --- |
| `screener_compliant.py` | Copy of `screener.py` stages 2–6 with the fixes below. Stage 1 (fetch/cache) is imported from `screener.py`, not copied, so there is still one fetcher and one cache. |
| `risk_compliant.py` | Copy of `risk.py`. The computations are identical; only the output wording and structure change. |
| `signal_history.py` | New: an append-only log of signal changes (REC-7, REC-11). |
| `tests/test_compliance_algorithms.py` | 35 tests. They prove the copies compute the same numbers as the originals and pin each requirement below. |
| `docs/legal/*_compliant.md` | Compliant versions of the two algorithm specs (§5). |

`scoring.py` and `portfolio_enrichment.py` need no changes: they compute descriptive sub-scores and flags only.

## 1. Findings

Severity follows the requirements document: **MUST** items are launch blockers.

| # | Req. | Level | Finding in the original | Location | Fix in the copy |
| --- | --- | --- | --- | --- | --- |
| 1 | PER-2 | MUST | The peer universe that sets sector P/E and P/B medians and every percentile rank includes each user's **manual tickers** (per-user `manual_tickers.json`). Adding a ticker moves every other stock's score, so two users can see different signals for the same stock. A test reproduces it. | `uvalu/data.py:194-220` → `screener.py:2100, 2161` | `compute_scores(peer_mask=…)`: only public-universe rows set the medians and ranks; user rows are scored against them without moving them. Helper: `peer_mask_for(df, public_tickers)`. |
| 2 | PER-1 | MUST | On a cold start the portfolio lane has no universe reference and scores the user's holdings **ranked among themselves**, so the signal depends on what the user holds. | `uvalu/data.py:331-334, 380-385` | `compute_scores(user_selected=True)` without a reference: rows get `signal_code="pending"` and no score. Fair values (not rank-based) and vetoes (absolute rules) still show. |
| 3 | PER-5 | MUST | Stage 8 turns a held stock's screener veto into "consider reducing or exiting". This is the exact example the document forbids. | `risk.py:1465-1469` | Trigger removed. The veto stays on the stock's own badge, which is the same for every user. |
| 4 | PER-4 | MUST | Every Stage 8 item carries a prescription: "Trim to ≤15%; redeploy to underweights", "Rotate into low-beta / defensive stocks", "Replace one position per pair…", "Favor payers with stronger dividend growth", and more. | `risk.py:1414-1601` | Stage 8 becomes `RiskObservations`: each item states the figure and the reference it was compared with. There is no `action` field, so advice cannot be attached later by mistake. |
| 5 | PER-4 | MUST | The composite risk bands carry actions: "Immediate rebalancing required", "Defensive repositioning — reduce exposure immediately". | `risk.py:97-103` | The third field of `RISK_BANDS` is now a description of the band. `CompositeScore.action` is renamed `description`. |
| 6 | PER-1 | MUST | "exceeds 3% loss tolerance" and "exceeds 20% hard limit" assert a personal tolerance the app does not know. | `risk.py:1431, 1446` | Worded as the model's reference levels, which are now named constants (`REF_*`) so the methodology page can publish them. |
| 7 | BDG-1/3 | SHOULD/MUST | The signal is `Strong Buy / Monitor / Avoid`, and a veto is folded into `Avoid`. | `screener.py:2226-2235` | `signal_code` (stable machine value) plus `Signal` (label): `Undervalued`, `Neutral`, `Low score`, `Fails quality screen`, `No signal`. The `Decision` column is gone. |
| 8 | REC-2 | MUST | `decision_reason` explains the signal as "both BUY conditions met", "excluded from BUY scoring", "Not a BUY". | `screener.py:1655-1701` | `signal_reason()` states the rule and the figures in descriptive terms only. |
| 9 | REC-2 / DIS-5 | MUST | `TER %` ("Total Expected Return") presents a model figure as an expected return. | `screener.py:2124` | Column renamed `Implied Return % (est.)`. The formula is unchanged and the docstring calls it an estimate. |
| 10 | REC-2 | MUST | The per-position flag in the risk report says "Undervalued" at a margin of safety of 10% or more. The screener's "Undervalued" would also need a high composite score, so one stock could carry two contradictory valuation labels on two screens. | `risk.py:524-525` | Renamed `Above / Near / Below model fair value`: named after the comparison it actually makes. |
| 11 | DATA-6 | MUST | The fair-value blend uses analyst price targets (`targetMeanPrice/High/Low`, analyst count), and momentum uses the consensus `recommendationMean`. Both are sell-side content, licensed separately from prices and fundamentals. | `screener.py:1472-1473, 1836` | `ANALYST_INPUTS_ENABLED = False`. The analyst model drops out and its weight renormalises across the other models; momentum uses growth only. `fv_dark_reasons` reports `not_licensed`. |
| 12 | REC-4 | MUST | No timestamp for when a signal was computed or for the price it used. | `screener.py:2038-2246` | `signal_computed_at` and `price_as_of` on every row. |
| 13 | REC-3 | MUST | No data source on output; reliability caveats are scattered (`fv_basis_thin`, `small_universe`, …) or missing (stale price). | — | `data_source`, plus `data_flags`: `price_stale` (more than 72 h old), `price_missing_timestamp`, `fair_value_missing`, `fair_value_thin_basis`, `fair_value_clamped`, `eps_derived_from_pe`, `small_peer_group`. |
| 14 | REC-5/6 | MUST | Thresholds and weights live only in code, and a methodology page written by hand would drift from them. | — | `methodology(**settings)` returns the exact live thresholds, weights, quality-screen rules, signal definitions, horizon, risk warning and sensitivity note. `SIGNAL_TOOLTIP` holds the BDG-2 text. |
| 15 | REC-7 | MUST | No badge-change history. | — | `signal_records()` + `signal_history.record_changes()` / `history_for()`: changes only, 12-month window, robust to a torn last line. |
| 16 | REC-11 | SHOULD | A past signal cannot be reproduced. | — | `model_version` and `model_settings_id` (a hash of thresholds, weights and the analyst switch) on every row and in every log record. |
| 17 | REC-10 | SHOULD | No distribution of signals across the coverage. | — | `signal_distribution(df)`. |
| 18 | DIS-3 | MUST | The risk report carries no statement that VaR, CVaR, Monte Carlo and stress figures are estimates. | `risk.py:1736` | `RiskReport.disclosures` (`RISK_DISCLOSURES`), which also carries the Fama-French attribution. |
| 19 | PER-3 | MUST | `income_portfolio` reweights the risk score by a user *objective*. It is hard-coded `False` today, but the name invites wiring it to a goal. | `risk.py:72, 1373`; `uvalu/data.py:539` | Becomes `weighting="standard" \| "income_weighted"`: a model setting (PER-8). Unknown values raise. |

**Checked and compliant as is:** the vetoes are absolute rules on the stock's own data. The screener settings (`buy_threshold`, `min_mos`, D/E, payout, screening style) are **shared**, admin-only settings, so they meet PER-2. The per-user dividend withholding feeds only income display, never scores. The ex-dividend, cut and raise badges on the Dashboard report facts about the user's holdings, not signals. Drift checks against targets the user sets are allowed (PER-5); the copy keeps them and marks them `basis="user_target"`.

## 2. Deliberate deviation from BDG-1

BDG-1 proposes MONITOR → "Near fair value" and AVOID → "Overvalued". The copy does **not** use those two labels. The bands come from the composite score (margin of safety + risk + quality + momentum + dividend), not from valuation alone. A stock 30% below its model fair value but with weak quality and momentum sits in the lowest band, and calling it "Overvalued" would be false. Under REC-2 and WER VI.97, a label must describe what the model measured. Hence `Neutral` and `Low score`. `Undervalued` stays for the top band, because that band requires a confirmed margin of safety. **[Counsel]**: confirm, or rework the algorithm so that the bands are purely valuation-based.

Related recommendation: the shared `min_mos` setting defaults to 0%. At that default, a price 0.5% below fair value with a high score is labelled "Undervalued". Consider raising the default to about 10% before launch.

## 3. Equivalence

The copies change what is said, not what is calculated. These tests confirm it:

- Screener, with `ANALYST_INPUTS_ENABLED` switched on and no peer mask: fair values, scores, sub-scores, MoS and implied return are identical to `screener.py`, and each `Decision` maps one-to-one onto a `signal_code`.
- Risk, for both weightings: composite score, label, sub-scores, volatility, HHI and position ratings are identical to `risk.py`.

With the defaults, fair values and scores *do* change in two ways. Dropping the analyst inputs (DATA-6) renormalises the fair-value blend and momentum. With a peer mask, user-added tickers no longer move anyone's ranks. Both changes are intended.

## 4. Needed outside the algorithm files when wiring this in

These are not algorithm changes, but the copies only take effect once they are done:

1. **`uvalu/data.py`**: build the peer mask from the enabled exchanges' ticker lists and pass `peer_mask=` in `_build_all_screener_data`. Pass `user_selected=True` in `_load_portfolio_screener_data`. Switch the imports to the `*_compliant` modules.
2. **UI**: read `signal_code`/`Signal` instead of `Decision` (`components.py`, `drawer.py`, screener/watchlist/analysis/dashboard pages, the Excel export). Show `SIGNAL_TOOLTIP`, the methodology link, `signal_computed_at`, `price_as_of` and `data_flags` next to every badge (BDG-2/3, REC-4). Gate the "Analyst Target" field that `uvalu/components.py:320, 392` shows undiscounted on the same switch (DATA-6).
3. **Risk page / Dashboard**: render `observations` (no "Rebalancing" heading or wording), `composite.description` and `disclosures`. `uvalu/components.py` derives its colours from `risk_band()`, and the tuple shape is unchanged.
4. **`apply_live_mos`** (`uvalu/data.py:394`) recomputes MoS against the live price on the portfolio screens, but the signal was computed from the cached price. Show `price_as_of` next to the signal, or recompute the signal there too, so the two cannot contradict each other.
5. **Alerts**: `alert_buy_signal` and `alert_avoid_signal` exist in `settings.py:95-96` but nothing reads them. Under PER-5 they must never fire for "a stock you hold". Either remove them, or wire them to the user's watchlist and to thresholds the user sets.
6. **Signal log**: after each universe build, call `signal_history.record_changes(signal_records(scored))`. Show `history_for(ticker)` on the stock page.
7. **Translations (INT-1)**: `tools/i18n_update.py` has added the new strings to `messages.pot` and every `.po` file, **untranslated**. The badge labels, tooltip, definitions and disclosures are legal texts, so a fluent reviewer must translate them for FR, DE, IT and ES (INT-4) before release.
8. **Methodology page (REC-5)**: render from `methodology(*get_veto_thresholds(), weights=get_score_weights())`. Add the `REF_*` risk reference levels from `risk_compliant.py`.
9. **`DATA_SOURCE`**: still says Yahoo Finance and "unlicensed for commercial use". Replace it with the licensed provider and its required attribution once DATA-2 is signed.

## 5. Algorithm specifications

The two specs in `docs/` describe the original algorithms and are **unchanged**. Their compliant counterparts describe the copies:

| Original spec | Compliant copy |
| --- | --- |
| `docs/stock_valuation_algorithm.md` | [`stock_valuation_algorithm_compliant.md`](stock_valuation_algorithm_compliant.md) |
| `docs/portfolio_risk_assessment_algorithm.md` | [`portfolio_risk_assessment_algorithm_compliant.md`](portfolio_risk_assessment_algorithm_compliant.md) |

Each copy keeps the original's technical content, applies every change in §1, and ends with a "Changes from the original spec" table. The issues found in the specs themselves, beyond those that mirror the code:

| Spec | Issue in the original | Req. | Change in the copy |
| --- | --- | --- | --- |
| Stock | Purpose given as "identifying undervalued stocks and deciding whether they are worth buying" | DIS-5, DIS-6 | Model fair value plus a descriptive signal; stated as general information, not a recommendation |
| Stock | Thresholds called "user-adjustable sliders", although the card is shared and admin-only | PER-2 | Stated as shared model settings, the same for every user |
| Stock | Peer universe documented as including "portfolio holdings on disabled exchanges", and holdings "ranked among themselves" before the first build | PER-1, PER-2 | Public universe only; no ranked signal without a public reference |
| Stock | No data source, licensing, presentation, methodology, horizon, history or reproducibility rules | DATA-1/6, REC-3 to REC-11, BDG-2/3 | New sections: data source and licensing; what every signal is shown with; methodology; update frequency, history and reproducibility |
| Stock | No standing rules that keep future changes non-personal | PER-1 to PER-7, PER-9 | New "Design rules" section, to check before each release |
| Risk | Purpose "managing … actionable rebalancing signals"; overview ends in "Action: Rebalance / Monitor / Hold" | PER-4 | Describes, never prescribes; ends in observations and disclosures |
| Risk | VaR defined as "the maximum expected loss" | DIS-3 | An estimate that real losses can exceed |
| Risk | Instructions inside metric tables: "assess recovery time", "review stock selection" | PER-4 | Removed |
| Risk | "Income mandate" / "for income portfolios" frames the user's objective | PER-3 | `weighting`, a model setting chosen by the user |
| Risk | "Rebalancing Actions" table and "act immediately" triggers | PER-4, PER-5 | Replaced by risk observations with `level`, `basis` and reference levels |
| Risk | "Monitoring Cadence" reads as a schedule the user should follow ("Full rebalancing review: semi-annually") | PER-4 | Replaced by what the app recomputes and when |

When the copies are wired in, the compliant specs replace the originals in `docs/`. Until then, both sets are kept so that each spec matches the code it describes.

## 6. Open points for counsel

- Whether the remaining "Undervalued" label, and a fair value shown with a user-adjustable model, still count as Uvalu's own "opinion" under MAR (§4 of the requirements).
- Whether position risk ratings (High/Critical) computed from the user's own position weights stay on the descriptive side of PER-4. The copy reports them without any action.
- Whether the Fama-French Data Library terms permit display in a paid service (DATA-6). Attribution is already in `RISK_DISCLOSURES`.
