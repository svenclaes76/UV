# Data contracts

Cross-cutting invariants the UI depends on. Each was a real inconsistency
between screens at some point (see the `dq/*` history); the tests in
`tests/test_data_contracts.py` and the per-helper unit tests lock them in.

---

## Price

- **`prices.fetch_prices(tickers)`** returns, per ticker: `price`, `prev_close`,
  `day_change_pct`, `volume`, `as_of` (ISO-8601 **UTC**, the batch fetch time —
  every ticker in one batch shares it), `stale` (served from the
  last-known-good cache), and **`quote_source`**:
  - `"intraday"` — a fresh 1-minute bar;
  - `"eod"` — fell back to the most recent daily close (lags during a live
    session);
  - `"stale"` — served from `_last_good` because the fetch returned nothing.
- **`uvalu.data._fetch_prices_cached`** is the single entry point every
  price-bearing page uses (Dashboard, Portfolio, Risk). It normalises the
  ticker tuple so all callers share one cache entry, and stashes
  `price_feed_status()` in `st.session_state["_price_feed_status"]` for the
  shell's freshness pill.
- The shell pill (`shell._price_indicator`) is **Live** / **Delayed N/total** /
  **Feed stale** / **Market closed** with the feed's own `as_of` rendered in
  the market timezone (`uvalu.market_hours.MARKET_TZ`) — never a hardcoded
  "Live".

## Margin of safety

- `MoS % = (fair_value − price) / fair_value` — a **margin of safety**, not
  upside `(fair_value / price − 1)`. Every user-facing label says "Margin of
  safety" / "MoS". `screener._margin_of_safety` is the definition;
  `compute_scores` produces the `margin_of_safety` (fraction) and `MoS %`
  columns.
- `compute_scores` computes MoS against the **fundamentals-cache `Price`**
  snapshot. The portfolio screens render it next to a **live** price, so they
  overlay **`uvalu.data.apply_live_mos(scored, live_prices)`**, which
  recomputes `Price` / `live_price` / `MoS %` / `margin_of_safety` from the
  batch `fair_value` and the live quote and sets **`price_stale`** (no live
  quote, live >10% off the cached price, or an `eod`/`stale` source during
  market hours).
- `apply_live_mos` deliberately does **not** touch `fair_value`, the six
  sub-models, `Value Score`, the `Sub *` ranks or `Decision` — those need the
  whole scored universe and are not live figures.
- **Invariant:** on any Holdings-ladder row the printed price, printed `fv` and
  printed `%` reconcile: `pct ≈ (fv − price) / fv`.

## Fair value

- `screener._fair_value_models` blends up to six core models, plus two
  conditional fallbacks. If the blend exceeds `FV_SANITY_MULT` (2.0) × price but
  at most one individual model is that high, the composite is clamped to the
  models' median (floored at the current price) and **`fair_value_clamped`** is
  set. Individual model values are never modified. The two DDM variants count as
  **one** corroborating vote here (same model family, identical inputs) —
  otherwise a Gordon-model blow-up where only `ddm` + `ddm_multistage` are high
  could never be caught.
- **FV-3 fallbacks.** `pb_fair_value` (`bookValue` × winsorized sector-median
  `priceToBook`) and `fcf_fair_value` (`freeCashflow` × 15 − net debt, per
  share) are computed and blended (weight 0.10 each, outside the six-model sum)
  **only** when none of Graham / PE / EPV produced a value — a genuine
  loss-maker. Both are `None` for any row with a live earnings anchor. The
  drawer / Analysis ladder keeps six rows: a fired fallback replaces the first
  dark Graham/PE/EPV slot and is relabelled ("Book value" / "FCF value",
  `components.six_model_ladder_rows`). FV-8: on the **resolved** sector
  (`sector_for()`, so a provider-null REIT still matches), `Real Estate` /
  `Financial Services` (`_GRAHAM_EPV_SKIP_SECTORS`) skip Graham + EPV — and P/E
  too for `Real Estate` (`_PE_SKIP_SECTORS`). The **book-value model** fires for
  these sectors as a *primary* anchor regardless of `_trio` (`pb_eligible`), so
  a bank is valued off P/E + P/B + DDM + analyst and a REIT off P/B + DDM +
  analyst; FCF stays a pure loss-maker fallback. `Utilities` are unaffected.
- **FV-6.** A dark ladder row shows a short "why" phrase from
  `components.six_model_ladder_reasons`, which only *formats* the authoritative
  **`fv_dark_reasons`** codes (`{model_key → code}`) that `_fair_value_models`
  emits alongside the guards themselves — the component re-derives nothing. The
  ladder also prints "basis · N of 6 models" (`fv_model_count`, amber when
  `fv_basis_thin`) and a caption reconciling the fallback substitution and the
  analyst-target haircut (`components.six_model_ladder_caption`).
- `_payout_source` records which payout proxy fed the DDM ramp: `reported`
  (raw `payoutRatio`, trusted only in `(0, 0.95]` — an exact `0.0` is
  missing-as-zero), `cash` (`cashPayoutRatio`), `coverage`
  (`1 / dividendCoverage`), or `none`.
- `ev_source` records where the EPV model's enterprise value came from:
  `provider` (`enterpriseValue`), `reconstructed`
  (`(marketCap or Price×shares) + totalDebt − totalCash`, FV-4; the EPV net-debt
  term then comes straight from `totalDebt − totalCash`), or `none`.
  `epv_negative` is `True` when a per-share EPV was computed but came out ≤ 0
  (net debt > capitalised earnings power); it is excluded from the blend, the
  flag is for the UI.
- **FV-5.** `fv_model_count` is `len(avail)` — how many *independent* sub-models
  fed the composite — with `ddm` + `ddm_multistage` counted **once** (one Gordon
  family) and Graham + PE counted **once** when the EPS behind them was
  reconstructed from `trailingPE` (`trailingEps_derived`). `fv_basis_thin`
  (`compute_scores`) is `True` when a row *has* a `fair_value` but
  `fv_model_count < MIN_FV_MODELS` (2) — a real but weakly-corroborated
  composite, as opposed to `data_thin` (no composite at all). Any scorable row
  with `fv_model_count < MIN_FV_MODELS` is treated as a degraded payload:
  `_fetch_and_store` re-fetches it on `CACHE_TTL_SHORT_HOURS` and
  `backfill_thin_rows_from_screener_lane` swaps in the screener lane's row when
  that one has *more* live models. `fv_basis_thin` also gates Stage 6: a thin
  row cannot reach `Decision == "Strong Buy"` (it falls through to Monitor on
  score instead) — a weakly-corroborated composite alone isn't a hard veto,
  just not enough to confirm a BUY. This was the FV-5 "Composite-score
  asterisk" deferred at ship time; the NAITR.AS incident (a lone book-value
  fallback off a corrupted price producing a spurious Strong Buy) is what
  prompted implementing it.
- **Known residual gap — untraded secondary listings with no volume data at
  all.** The zero-volume veto above only fires on a *confirmed* `averageVolume
  == 0`. A listing where `averageVolume` is simply unreported (`None` —
  e.g. `INPHI.AS`, a secondary Amsterdam line for Koninklijke Philips N.V.
  that shares its fundamentals with the real `PHIA.AS` listing but trades at
  a materially different, seemingly stale price) is not vetoed by it, and
  could in principle inherit ≥2 fair-value models from the real company's
  fundamentals (so it isn't `fv_basis_thin` either) while its own divergent
  price produces a plausible-looking, uncaught MoS. Two heuristics to close
  this were investigated and rejected as unsafe, not merely undesirable:
  - *Same-page duplicate company name* (within one `fetch_tickers.py`
    exchange fetch). Checked live against all 6 exchange listings: Frankfurt
    alone carries **681** duplicate company names among 10,614 rows, the
    large majority legitimate multi-tranche cross-listings of foreign
    megacaps with both lines actively trading (e.g. `NVIDIA Corporation →
    NVD | NVDG`, `Alphabet Inc. → ABE0 | ABEA | ABEC`, `Roche Holding AG →
    RHO | RHO6`). A same-page dedupe would misfire on hundreds of real,
    liquid securities.
  - *`averageVolume` and `sharesOutstanding` both missing.* Checked against
    the cache: **4,226 of 7,861 tickers (54%)** match, including `ROG.SW` —
    Roche Holding AG, one of the most liquid stocks in Europe — whose gap
    here is an ordinary Yahoo coverage artifact, not evidence of anything.
    Far too broad to veto on.
  No narrow, safe signal was found; closing this gap would need genuine
  per-ticker ground truth the app doesn't have, not a smarter guess from
  existing fields. Left as an accepted limitation — `INPHI.AS` itself lands
  on `Avoid` today via the unrelated pre-existing revenue-decline trend veto
  and a deeply negative MoS, so the *volume-absent* shape of this gap has not
  been observed to produce a wrong signal in the current universe. A related
  but distinct shape — a real, actively-traded listing whose per-share
  fundamentals were computed off a *different* security's basis — has been
  observed and is documented separately below (`LISPE.SW`).
- **Per-share input sanity floor (`PTB_SANITY_FLOOR`).** `_fair_value_models`
  holds Graham, PE Fair Value, and the Book value model dark, any sector, when
  `Price / bookValue < PTB_SANITY_FLOOR` (0.02) — `bookValue` and
  `trailingEps` share the same `sharesOutstanding` basis for a row, so an
  implausible implied P/B taints both. Deliberately P/B-only: a symmetric P/E
  floor was tried and rejected — `trailingEps` is a flow figure that
  legitimately swings on ordinary earnings volatility (real Strong Buy rows
  with implied P/E well under 2, e.g. `TPG0.DE`, `ALWEC.PA`, were found and
  would have been broken by it), so a low P/E alone isn't a safe signal the
  way an extreme P/B is. Calibrated against the full scored universe: the
  lowest P/B among legitimate `Strong Buy` rows sits at ~0.11, a 5×+ margin
  above the floor; a controlled before/after diff across all 7,859 cached
  tickers changed exactly one row (`SNBN.SW`, added to `Strong Buy`/removed
  by the fix), zero collateral additions or removals elsewhere. Found via the
  Swiss National Bank (`SNBN.SW`, 100,000 shares outstanding against an
  enormous balance sheet → bookValue/trailingEps in the hundreds of
  thousands per share, feeding a >CHF 6M composite fair value against a
  ~CHF 3,140 price) — the market price correctly reflects that the National
  Bank Act caps the dividend shareholders receive, so per-share book
  value/earnings don't translate to a proportional equity claim at all. New
  `fv_dark_reasons` code `implausible_book`
  (`components._REASON_TEXT`: "price too far below book value to trust").
- **Known residual gap — share-class fundamentals contamination
  (`LISPE.SW`).** A *different*, real, currently-live failure mode from the
  two above: `LISPE.SW` (Lindt & Sprüngli participation certificates, €8,530)
  and `LISN.SW` (the registered share, €88,700) are legitimate, independently
  and actively traded securities of the same company, but our cached
  `bookValue`/`trailingEps` are identical between them — the registered
  share's per-share figures, applied unchanged to the certificate. Graham/PE
  fair value then price the certificate off earnings that actually belong to
  the 10×-pricier share, producing a spurious Strong Buy. Unlike `INPHI.AS`
  or `SNBN.SW`, this is not caught by anything shipped: `LISPE.SW` has real
  trading volume and ≥`MIN_FV_MODELS` corroborating models (so it isn't
  `fv_basis_thin`), and its own implied P/B (0.44) looks entirely normal — the
  problem is a plausible ratio built from someone else's numerator, not an
  implausible ratio, so `PTB_SANITY_FLOOR` above doesn't reach it. Closing
  this would need reliable cross-ticker company-identity data, which the app
  doesn't have: `ISIN` is fetched into the schema but populated on 0 of 7,861
  cached tickers (`fetch_tickers.py` hardcodes `"isin": ""` for every ticker;
  stockanalysis.com's own listing tables don't expose one to scrape either),
  and the cached `Name` field differs per share class already (`LINDT N` vs
  `LINDT PS 2.LINIE`), so it can't be used to group siblings. Left as an
  accepted limitation for the same reason as `INPHI.AS`: no narrow, safe
  signal was found.
- **Scorable row.** `screener._row_is_scorable(row)` is True when a fundamentals
  row carries enough for at least one of the six models to produce a value
  (`trailingEps > 0`, or `bookValue` + a sane `trailingPE`, or
  `targetMeanPrice`, or a dividend rate whose **payout signal** —
  `_payout_signal`: reported ratio in (0, 0.95], else `cashPayoutRatio`, else
  `1 / dividendCoverage` — lands inside the DDM ramp band, or ≥3yr
  `ebitHistory` + an enterprise value from `_enterprise_value` (provider or the
  FV-4 reconstruction)). It mirrors `_fair_value_models`' own per-model input
  guards and must be kept in step with them. A row that is not
  scorable produces a NaN `fair_value` / `MoS`, which the rank layer papers over
  with a neutral 50 (`_pct_rank` / `_abs_band`) — so such a row still gets a
  `Decision`, usually `Monitor`.
- **A thin fetch never sticks for a day.** `_fetch_one` recovers a missing
  `trailingEps` from `trailingPE` (`trailingEps_derived` flags it). If the row
  still isn't scorable but has a price, `_fetch_and_store` retries it, then
  caches it on `CACHE_TTL_SHORT_HOURS` (not the 24h TTL) so a partial provider
  payload heals on the next fetch cycle.
- **The two lanes agree on "has a fair value".** `_load_portfolio_screener_data`
  runs `backfill_thin_rows_from_screener_lane(fund)` before scoring: any
  portfolio-lane row that isn't scorable is replaced by the `SCREENER_FETCH`
  lane's row for the same ticker when that one is scorable and no older. Both
  lanes run the identical scorer, so a held ticker never shows a fair value on
  the Screener page and a blank ladder on the Dashboard.
- **UI.** `uvalu.data.apply_live_mos` adds **`data_thin`** (`~_row_is_scorable`
  per row). The Dashboard Holdings ladder renders "fv pending" for a
  `data_thin` row with no fair value, instead of the bare "—" a genuinely
  unvaluable business gets.

## Sectors

- **`screener.sector_for(ticker, raw_sector)`** is the single source: the
  provider's value when present, else a curated `SECTOR_OVERRIDES` fallback,
  else `None`. Used by the Holdings sector tag, the Dashboard allocation
  donut, `portfolio_enrichment.enrich_for_risk` and the Analysis page.
- **Invariant:** a NaN / missing sector or country never reaches the UI as the
  string `"nan"` — `risk._category_label` and `sector_for` both collapse it to
  `"Unknown"` / `None`, and the label is identical on every screen.

## Concentration

- `risk.ConcentrationMetrics.hhi` is the **position-count** Herfindahl
  (`Σ wᵢ²`) — it feeds the composite risk score and the rebalance triggers.
- `risk.ConcentrationMetrics.sector_hhi` is the **sector-level** Herfindahl
  (`Σ sector_weightᵢ²`) — this is what the Risk page's "Sector HHI" tile
  shows. The two are distinct numbers with distinct labels.

## Signal badge

- `components.signal_badge_for_decision(decision, veto)` has **three** states:
  - real hard veto (`components.is_hard_veto`, NaN-safe) → **VETO**;
  - a scored `Strong Buy` / `Monitor` / `Avoid` → that;
  - anything else (no `Decision` — the holding has no scored screener row) →
    neutral **NO DATA**.
- `bool(nan)` is `True` in Python, so every veto read goes through
  `is_hard_veto`, never a bare `bool(row.get("veto"))`.
- **Invariant:** the hard-veto count is identical on the Dashboard Holdings
  badges, the Dashboard conviction card, and the Risk page.
- `screener.decision_reason(row, *, buy_threshold, min_mos)` explains a row's
  Decision in one line (why not BUY / why Avoid vs Monitor) — shown on the
  Analysis page and the drawer for non-veto rows.

## Portfolio risk report

- **`uvalu.data.load_portfolio_risk(pf)`** is the only path to a
  `risk.RiskReport` for a portfolio. It enriches `pf`
  (`enrich_for_risk`), builds the hard-veto lookup, passes the target
  allocation and prior snapshot, and session-caches the result (1-hour TTL,
  keyed on tickers / veto / targets).
- Both the Risk page and the Dashboard "Conviction & risk" card call it.
- **Invariant:** the composite risk score shown on the Dashboard equals the
  one on the Risk page for the same portfolio in the same session.

## Risk contribution

- The Risk page's "Contribution to risk" is **percent contribution to
  portfolio variance** — `wᵢ · (Σw)ᵢ` with `Σᵢⱼ = σᵢ σⱼ ρᵢⱼ`, from each
  holding's own volatility and `r.quant.corr_matrix`. It falls back to
  `weight × |beta|` (with a visible caption) only when there isn't enough
  correlated return history.
