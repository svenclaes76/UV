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

- `screener._fair_value_models` blends up to six models. If the blend exceeds
  `FV_SANITY_MULT` (2.0) × price but at most one individual model is that
  high, the composite is clamped to the models' median (floored at the current
  price) and **`fair_value_clamped`** is set. Individual model values are
  never modified.

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
