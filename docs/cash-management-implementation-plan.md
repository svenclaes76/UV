# Cash Management v1 — Implementation Plan

Sources:
- Requirements: *Uvalu — Cash Management Requirements (v1)*, Sep 21 2026.
- Design: Claude Design project "Uvalu", file `Uvalu Cash Management.dc.html` (+ `support.js` runtime). Imported into `docs/design/` in WP-CM0.

Target release: **v1.12.0** (MINOR: new capability, no manual migration step. See CONTRIBUTING.md §"Versioning and releases").
Branch: `feature/cash-management-v1` off `master` (`3a52bf4`).

---

## 1. Starting point

| Area | Today | Gap |
| --- | --- | --- |
| Cash storage | `portfolio.save_cash()` / `load_cash()` write `cash.json`. The only caller is one round-trip test (`tests/test_portfolio.py:335`), which uses a `{currency, amount}` shape. | No schema, no UI, and not in `backup.py:_PORTFOLIO_FILENAMES` (already noted in `docs/backend-feature-gaps.md` §3). |
| Trades | `uvalu/dialogs.py` `add_position_dialog` / `sell_position_dialog` call `portfolio.add_position` / `sell_position`. Neither has a fee field or a cash check. | No fee field, no "Cash after trade", no posting, no automatic top-up, no trade id. |
| Partial sell | `portfolio.sell_position()` drops **every** row for the ticker (`pf[~mask]`) and books the full `purchase_value`, even when only some shares are sold. | Existing bug. Once cash posts `shares × price`, the ledger and the positions would disagree. Fix it first (WP-CM0). |
| Dividends | `dividends_history.json` (v2 schema), `dividends_in_eur()` (FX from yfinance `fx_to_eur_frame`), auto-import (`import_dividends_from_market_data`). | Records have **no stable id** to link to. |
| FX | `marketdata.fx_to_eur_frame` (yfinance `XXXEUR=X`). It has two callers: `portfolio.dividends_in_eur()` and `risk._to_eur()` (EUR restatement of price history). | The spec requires frankfurter.dev as a **dedicated** integration, with the rate stored on each entry. **Decision: frankfurter becomes the only FX source in the app** (D5), so both existing callers move to it as well. |
| Roles | App-wide `auth.ROLES = ("Admin", "Analyst", "Viewer")`. Each user has one portfolio in their own encrypted directory. No sharing. | The spec's Owner/Editor/Viewer maps onto these roles (decision D1). |
| Base currency | Implicitly EUR everywhere (`purchase_value`, KPIs, risk). | No stored per-portfolio base currency (D2). |
| Risk | `risk.py` only reads positions. | Cash is already excluded. Only the explanatory banner (design) is missing. |

---

## 2. Decisions (recommended defaults, flagged for confirmation)

- **D1 · Role mapping.** The spec's Owner and Editor both map to `Admin` or `Analyst` acting on their own portfolio. Viewer maps to `Viewer`. `canEdit = not current_user().is_viewer`, the same gate every other write action uses. Export is available to every role. No cash-specific permissions.
- **D2 · Base currency.** Store `base_currency: "EUR"` in a new `portfolio_meta.json` the first time the portfolio is written, and never change it afterwards. No UI to choose it. Every valuation path in the app is EUR-only, so a non-EUR base would need changes well beyond cash. The field exists so the "fixed at creation" rule is stored as data, and all cash code reads `base_currency()` rather than hard-coding `"EUR"`.
- **D3 · Trades are never blocked. A shortfall is covered by an automatic top-up.** *(Confirmed by the user, Sep 23 2026. This intentionally departs from the requirement "trades … that would push it below zero are blocked", which now applies to withdrawals only. It also changes the design's blocked Buy state.)*
  - A Buy is allowed when cash is zero or would go below zero.
  - If `cost + fee` exceeds the available balance, the Buy posts **two** linked entries on the trade date, in this order:
    1. an automatic `Deposit` for the shortfall (`auto=true`, `topup=true`, note `Auto top-up to fund TRD-0481 · TTE.PA`, same `ref_id`);
    2. the `Buy` entry itself.
  - The balance therefore ends at exactly €0.00 and never goes negative.
  - A Sell whose fee exceeds proceeds plus cash is handled the same way (rare).
  - Existing portfolios start with an empty ledger. Existing positions are **not** back-posted.
  - No opening-balance prompt is needed. The user can still record one at any time as an `Adjustment` (`opening=true` when it is the first entry).
  - Top-ups count as external money coming in, so they are included in the "Net deposits" tile. The ledger marks them with an `Auto` source chip and a `top-up` sub-label so they stay distinguishable from the user's own deposits.
- **D4 · Dividend postings are stored, linked entries, kept in sync.** They are not derived when the ledger is read (the design prototype derives them). The spec says the FX rate is "fetched and stored … at post time". A `reconcile_dividend_postings()` step runs after every dividend add, edit, delete or auto-import:
  - posts an entry for dividends that have been received, are not DRIP and are not Stock-type;
  - updates the linked entry when the amount, currency or date changes. The stored FX rate is kept unless the date or currency changes;
  - deletes the linked entry when the dividend is deleted;
  - posts future-dated dividends once `date <= today`.
- **D5 · One FX source: frankfurter.dev (ECB reference rates).** *(Confirmed by the user, Sep 23 2026.)* `fx.py` is the only module that fetches FX rates.
  - The cash ledger stores a frankfurter rate on each entry.
  - `portfolio.dividends_in_eur()` switches to the frankfurter daily series. The Dividends page, the Dashboard and the ledger then convert a dividend at the same ECB rate for its pay date, so they agree.
  - `risk._to_eur()` switches to the same series for EUR-restating price history.
  - `marketdata.fx_to_eur_frame` becomes a thin shim that delegates to `fx.py`, keeping its signature and callers. The yfinance `XXXEUR=X` pairs are no longer fetched.
  - ECB rates are published for business days only (~16:00 CET). They are forward-filled, as the yfinance series already was.
  - Side effect: risk metrics and EUR dividend totals for CHF and other non-EUR holdings shift by small amounts. This goes in the CHANGELOG. The existing fallback is kept: a currency frankfurter doesn't cover is left in native terms and logged.
- **D6 · What does *not* post cash:**
  - editing a position (design: "No cash posting on edit"), deleting a position, and Excel import;
  - closed trades entered directly (`add_closed_trade`). These are historical and predate the ledger;
  - DRIP dividends and Stock dividends.
  Only the live **Buy** and **Sell** flows post.
- **D7 · Adjustment semantics.** An adjustment stores `target_balance`. Its EUR delta is computed on replay as `target − running balance just before it`, as the design's `_ledger()` does. If an entry is later backdated to before an adjustment, the adjustment absorbs it. This is correct for "sets balance directly". The delta at entry time is also stored (`delta_at_entry`) for audit, and the UI shows "set to €X".
- **D8 · Negative-balance handling covers the whole timeline.** Manual debits (Withdrawal, Fee) are **blocked** if the running balance goes below 0 at **any** point from their date onward, not only at the final balance. Adjustments reset the running balance, so the check stops at the next adjustment.
  - For trades (D3), the same timeline scan sizes the top-up: `top-up = −min(running balance from the trade date onward, after the trade)` when that minimum is negative. A backdated buy is therefore always fully funded, including against later withdrawals.
  - Dividend edits and deletes are not blocked. If the history goes negative that way, the Cash page shows a warning banner.
- **D9 · Dashboard KPI strip.** Follows the design: Current value (incl. cash) · **Cash** · Total return · Fwd income / yr · Avg fair-value upside. *(As built: the Dashboard had only four tiles, and "Dividends received" was merely the fallback shown when forward income is unknown, so nothing was removed. The Cash tile was added as the second of five.)*

---

## 3. Data model

### 3.1 `cash.json` (encrypted, per user, retained indefinitely)

One record per ledger entry:

| field | type | notes |
| --- | --- | --- |
| `id` | str | `C-000001`, monotonically increasing (`seq` = the integer part) |
| `seq` | int | tie-breaker for entries on the same date (insertion order) |
| `date` | ISO date | transaction date (the value date, not the time it was entered) |
| `type` | enum | `Deposit` `Withdrawal` `Buy` `Sell` `Dividend` `Fee` `Interest` `Adjustment` |
| `amount` | float \| null | **signed**, in the original currency. `null` for `Adjustment` |
| `currency` | str | ISO code of the original currency |
| `fx_rate` | float | base-currency units per 1 unit of `currency`. `1.0` when `currency == base` |
| `fx_source` | enum | `base` \| `ecb` \| `manual` (manual = flagged) |
| `fx_date` | ISO date \| null | the ECB date frankfurter actually returned (weekends and holidays resolve to the previous business day) |
| `amount_base` | float \| null | `round(amount × fx_rate, 2)`, stored at post time. `null` for `Adjustment` |
| `target_balance` | float \| null | `Adjustment` only |
| `delta_at_entry` | float \| null | `Adjustment` only, for audit |
| `opening` | bool | the opening-balance adjustment (excluded from the "Fees & corrections" tile) |
| `note` | str | optional. Auto entries get a generated description |
| `ref_kind` | `trade` \| `dividend` \| null | |
| `ref_id` | str \| null | `trade_id` or `div_id` |
| `ref_label` | str \| null | e.g. `TRD-0481 · TTE.PA`, `DIV-0012 · ALV.DE` |
| `auto` | bool | Auto vs Manual source chip |
| `topup` | bool | `true` only on the automatic funding `Deposit` created by a trade (D3) |
| `created_at` | ISO datetime | |

**Sign rules** (applied in the domain layer, never taken from UI input): Deposit, Sell, Dividend and Interest are `+`. Withdrawal, Buy and Fee are `−`. The amounts the user types are always positive.

**Legacy migration:** if `cash.json` rows have the old `{currency, amount}` shape and no `type`, convert each row into a single opening `Adjustment` whose target is the sum of those rows converted to EUR.

### 3.2 `portfolio_meta.json` (new)

`{"base_currency": "EUR", "created_at": "...", "trade_seq": 481, "cash_seq": 20}`. The sequence counters live here so ids stay unique after deletes.

### 3.3 Additions to existing stores

- `portfolio.json` rows: `trade_id` (`TRD-0001` style), assigned when the position is added. Missing ids are backfilled on load.
- `sold.json` rows: `trade_id` for the sell leg. Also `fee` (the Buy side stores `fee` too).
- `dividends_history.json` rows: `div_id` (`DIV-0001`), backfilled by `_migrate_div_hist`.

---

## 4. Architecture

```
fx.py                      NEW   frankfurter.dev client: the app's only FX source (point rates + daily series)
marketdata.py              EDIT  fx_to_eur_frame → shim delegating to fx.rates_frame (drops yfinance XXXEUR=X)
cash.py                    NEW   ledger domain: replay, validation, posting, export, summaries
portfolio.py               EDIT  meta store, ids, partial-sell fix, record_buy / record_sell wrappers,
                                 reconcile hooks after dividend mutations
backup.py                  EDIT  + cash.json, portfolio_meta.json, dividend_meta.json
uvalu/dialogs.py           EDIT  Buy/Sell: fee + cash-after + block; NEW cash_transaction_dialog
uvalu/components.py        EDIT  cash_strip_html, cash_ledger_row_html, type/source chips, alloc bar
uvalu/pages_/cash.py       NEW   Cash activity full page (called from portfolio.py section router)
uvalu/pages_/portfolio.py  EDIT  cash strip on Overview; route port_section == "cash"
uvalu/pages_/dashboard.py  EDIT  KPI strip per D9
uvalu/pages_/risk.py       EDIT  "risk covers invested portion only" banner
```

`cash.py` and `fx.py` do not import Streamlit, so everything testable is a pure function. They are root modules, like `marketdata.py` and `scoring.py`.

---

## 5. Work packages

### WP-CM0 · Prerequisites

1. Import the design into the repo: copy `Uvalu Cash Management.dc.html` into `docs/design/` and add it to `docs/design/README.md`. Its `support.js` is the same generated runtime that is already committed. Diff it and replace only if it is newer.
2. **Partial-sell fix** in `portfolio.sell_position()`:
   - Selling fewer shares than held reduces `shares` and `purchase_value` pro-rata, lot by lot, oldest `date_in` first (FIFO across multi-lot rows).
   - The sold record carries only the sold shares' cost basis.
   - Tests: full sell, partial sell of one lot, and a partial sell that spans two lots.
3. Stable ids: `trade_id` on positions and sold rows, and `div_id` on dividends, with load-time backfill. Counters live in `portfolio_meta.json`. Test that backfill is idempotent.

### WP-CM1 · frankfurter.dev integration (`fx.py`), the app's single FX source

- `rates_frame(currencies, start, end=None, base="EUR") -> DataFrame`
  - Returns a daily "base per 1 unit" series (DatetimeIndex × currency code).
  - One time-series call per request: `GET /v1/{start}..{end}?base=EUR&symbols=CHF,USD,…`. frankfurter quotes units per 1 EUR, so each value is inverted.
  - The index is forward-filled over weekends and holidays.
  - Cached permanently per currency in `.cache/fx_frankfurter_series.json`. Later calls fetch only the dates after the last cached date.
  - On an outage it returns whatever is cached. A currency with no data is simply absent from the frame, matching the current `fx_to_eur_frame` contract.
- `get_rate(ccy, base, on: date) -> FxQuote(rate, rate_date, source="ecb")`
  - Calls `GET https://api.frankfurter.dev/v1/{YYYY-MM-DD}?base={ccy}&symbols={base}` via `requests` (already a dependency), with a 4 s timeout.
  - Raises `FxUnavailable` on a network error, a non-200 response, a missing symbol, or a date before 1999-01-04.
- `supported_currencies()`: `GET /v1/currencies`, cached for 24 h. Falls back to the design's list: EUR, USD, GBP, CHF, SEK, DKK, NOK.
- Caching:
  - Historical rates never change, so they are cached forever: an unencrypted `.cache/fx_frankfurter.json` keyed `ccy:base:date`. Rates are public data, so encryption is unnecessary.
  - Today's rate is cached for 1 h.
  - In-process `functools.lru_cache` on top.
- Logging: `logkit` event `fx.lookup` / `fx.unavailable`, with currency and date only.
- **Move the existing callers over (D5):**
  - Change `marketdata.fx_to_eur_frame(currencies, period)` to map `period` to a start date and return `fx.rates_frame(...)`. The signature stays the same, so `risk._to_eur()` and `portfolio.dividends_in_eur()` switch with no call-site changes.
  - Update the docstrings and comments that mention `XXXEUR=X` / yfinance FX (`marketdata.py`, `portfolio.py:387`, `dashboard.py:101`, `risk.py:1600`).
  - `dividends_in_eur()` keeps its per-row lookup by pay date, now on ECB rates. Because `get_rate` and `rates_frame` share a cache, the ledger's stored dividend rate equals the rate the Dividends page uses.
- Tests use a monkeypatched `requests.get`:
  - a normal lookup, a weekend date that resolves to Friday, an outage, a 404 for an unknown currency, and a cache hit (no second HTTP call);
  - the series: inversion, forward-fill, incremental extension, and an outage that returns the cached data;
  - rewrite the existing FX tests in `tests/test_marketdata.py`, `tests/test_portfolio.py` and `tests/test_algorithms.py` that stub yfinance `XXXEUR=X` pairs so they stub `fx.rates_frame` instead.

### WP-CM2 · Ledger domain (`cash.py`)

- `load_ledger() -> list[Entry]` / `save_ledger()`: go through `portfolio.load_cash/save_cash`. Migrates the legacy shape.
- `replay(entries) -> list[Row]`:
  - sorts by `(date, seq)`;
  - adds `base` (the stored `amount_base`, or the adjustment delta) and a running `bal`;
  - rounds to 2 dp at every step, as the design does.
- `balance(entries=None) -> float`
- `min_balance_after(entries, candidate) -> float`: the lowest running balance from the candidate's date onward, with the candidate inserted. This is the D8 timeline scan.
- `check_post(entries, candidate) -> None | str`: manual debits only. Uses `min_balance_after`. It returns the design's error string `Blocked: this would take the cash balance to −€X. Balance cannot go negative.`
- `topup_needed(entries, candidate) -> float`: for trades, `max(0, −min_balance_after(...))`.
- `post_manual(type, date, amount, currency, *, note, manual_rate=None)`:
  - resolves FX through `fx.get_rate` unless `manual_rate` is given (then `fx_source="manual"`);
  - validates;
  - appends the entry and saves;
  - logs `logkit.data_mutation(action="cash.post", entity_type="cash", entity_id=id, type=...)`, never amounts (the existing `save_cash` convention).
- `post_adjustment(date, target_balance, note)`: target must be ≥ 0. Stores `delta_at_entry`.
- `post_trade(kind, trade_id, ticker, shares, price, fee, date, currency="EUR") -> list[Entry]`:
  - `amount = −(shares·price + fee)` for a buy, `+(shares·price − fee)` for a sell;
  - generated note `Bought 60 TTE.PA × €58.90 · fee €9.90`;
  - `ref_label` `TRD-0481 · TTE.PA`.
  - If `topup_needed > 0`, it first appends the automatic `Deposit` (`topup=true`, same `ref_id`, lower `seq`) and then the trade entry, and saves both in one write (D3).
  - It never raises for an insufficient balance.
- `reconcile_dividend_postings(div_df)`: implements D4. Uses the net after all withholding (`net_after_be_amount` in native currency) × frankfurter rate at the pay date. If frankfurter is down, it retries on the next reconcile run and posts nothing in the meantime. It does **not** post using a guessed rate.
- `summary(entries, invested_value) -> dict`: the five tiles (balance, net deposits, trade flow, income, fees & corrections excluding the opening balance, plus the number of corrections), cash %, invested %, total value, last-entry text.
- `export_csv(entries) -> bytes`: see WP-CM9.
- **As built:** `preview_trade()` (what a trade does to cash, including any top-up) feeds the Buy/Sell dialogs, and `remove_ref()` rolls back a trade's entries.
- Tests (`tests/test_cash.py`):
  - replay ordering and ties;
  - adjustment target semantics, including a backdated entry absorbed by a later adjustment;
  - D8 cases: a backdated withdrawal that breaks an intermediate point, and one that is saved by a later adjustment;
  - D3 top-up cases:
    - a buy with an empty ledger gives a top-up equal to cost + fee, and the balance is exactly 0;
    - a partly covered buy gives a top-up equal to the shortfall;
    - a covered buy creates no top-up;
    - a backdated buy before a later withdrawal is sized to keep the whole timeline ≥ 0;
    - the top-up has a lower `seq` than its trade and the same `ref_id`;
  - sign rules;
  - manual-rate flagging;
  - legacy migration;
  - NaN safety. A ledger `DataFrame` round-trips through JSON, and numeric guards must use `pd.notna` (see the NaN-vs-None memory).

### WP-CM3 · Trade auto-posting

- New `portfolio.record_buy(row, fee)` / `record_sell(ticker, shares, price, fee, date)`:
  - write the position change, then call `cash.post_trade` (which adds any top-up, D3), under one `threading.Lock` per user directory;
  - roll back the position write if the cash save raises. Two files cannot be atomic; this keeps them consistent in practice.
- No blocking. The design's `apErr` "Blocked: this buy needs …" and `sellErr` "Fees exceed proceeds…" states are **dropped**.
- The dialogs call the `record_*` wrappers. The lower-level `add_position` / `sell_position` stay as they are for Excel import and edit paths, which do not post (D6).
- Tests:
  - a buy with cash posts one entry with the correct `ref_id`;
  - a buy with zero cash posts a top-up plus the buy, and the balance is 0;
  - a partial sell posts the correct proceeds;
  - the rollback path removes the position and leaves no orphan entries.

### WP-CM4 · Dividend auto-posting

- Call `cash.reconcile_dividend_postings()` at the end of:
  - `add_dividend`;
  - `update_div_hist`, which covers edits and deletes on the Dividends page;
  - `import_dividends_from_market_data`;
  - page load. The page-load call is throttled once per session through `st.session_state`, so future-dated dividends post when they come due.
- Tests:
  - add → posted, edit amount → mirror updated, delete → mirror removed;
  - DRIP / Stock → not posted, future date → not posted until due;
  - CHF dividend → FX stored with `ecb` and **equal** to the rate `dividends_in_eur()` applies to that row, so the ledger and the Dividends page net EUR match to the cent;
  - frankfurter down → no post and a retry later.

### WP-CM5 · Buy / Sell dialog changes (`uvalu/dialogs.py`)

These match the design's modals at lines 49–101 and 334–369.

- **Add position:** a new row after Shares / Total cost / Price, split 1 : 1:
  - **Fees (opt.)** input;
  - **Cash after trade**, a read-only mono value. When the trade needs a top-up it shows `€0.00`, plus a second line in faint amber (`--warn-txt`): `+€X auto top-up from outside cash`. It is never red and never blocks (D3).
  - Edit-position dialogs show `No cash posting on edit` in that slot.
- **Sell (Close position):** the same row. Button label **Confirm sale**, keeping the danger style.
- Errors render inline in `var(--down-txt)`, like the design's `ap.err` / `sell.err`, instead of `st.error`, to keep dialog height stable.
- AppTest coverage: fee changes cash-after, a buy above the balance shows the top-up line and still saves (top-up + buy entries), a Viewer cannot open the dialog.

### WP-CM6 · Add cash transaction dialog

Matches design lines 263–332. Width **500 px** (`_dialog_width_css(500)`).

- Title "Add cash transaction". Subtitle "Trades and dividend payments post automatically. Use this for everything else."
- **Type:** a five-way `st.segmented_control` (Deposit · Withdrawal · Fee · Interest · Adjustment). The preselect comes from the caller: the strip's Deposit / Withdraw buttons and the page's Add transaction.
- **Non-adjustment layout:** Date / Amount / Currency in a 1.15 : 1 : 0.8 grid.
  - Date: `st.date_input`, format `DD MMM YYYY`, no future dates.
  - Amount: positive.
  - Currency: from `fx.supported_currencies()`, defaulting to the base currency.
  - FX panel when currency ≠ base:
    - **Auto:** a mint dot, `1 USD = €0.8540`, `ECB reference rate for <date> · frankfurter.dev`, and an "Enter manually" link. The rate is looked up on each rerun and served from cache.
    - **Manual or outage:** an amber panel with `1 USD = €[input]`, a **Manual rate** chip and a "Use ECB rate" link. The link is hidden during an outage. The outage copy is the design's exact string.
- **Adjustment layout:** Date / **Corrected balance · EUR**, plus the hint `Current balance €X. Saved as a separate correction entry; earlier entries stay unchanged.`
- **Note** (optional). The placeholder depends on the type.
- **"Calculated · EUR base" panel:** Current balance / Amount in EUR (or Correction) / **Balance after**, red with `· blocked` when negative.
- Actions: Cancel · `Add deposit` / `Add withdrawal` / … / `Log correction`.
- Validation messages are the design's strings (`Enter a date…`, `Enter an amount greater than zero.`, `Enter the FX rate to convert USD to EUR.`, the blocked message).
- Call `enter_dialog()` first (fragment reruns skip `set_user`; see the active-user memory).
- AppTest: each type posts with the correct sign, a USD entry stores the ECB rate, an outage forces manual entry and flags it, a withdrawal over the balance is blocked, the adjustment computes its delta.

### WP-CM7 · Portfolio page: cash strip + Cash activity page

**Cash strip** (Overview, directly under the 5 KPI cards; design lines 863–889). New `components.cash_strip_html(...)` plus native buttons:

- Header "Cash balance" + an `EUR base` chip + a ⤢ icon that opens the full page (`port_section = "cash"`).
- A three-column grid:
  1. The balance (mono, 23 px) and `Last entry 01 Jul 2026 · fee`.
  2. The Invested / Cash legend with percentages, an 8 px split bar (teal / mint), and `Total portfolio value €X · risk metrics use the invested portion only`.
  3. **Deposit** / **Withdraw** buttons, hidden for Viewers.
- Empty ledger: the balance reads €0.00 and the last-entry line reads `No entries yet · buys top up automatically`. The buttons stay as they are. An opening balance, if wanted, is recorded as an Adjustment from the Cash activity page (D3).

**Cash activity full page** (`uvalu/pages_/cash.py`, design lines 1043–1113):

- "← Back to Positions", the title and subtitle from the design, and on the right:
  - a `Viewer · read-only` chip (Viewer only);
  - **Export CSV**;
  - **Add transaction** (primary, hidden for Viewers).
- Five tiles with the existing `kpi_card`: Cash balance · Net deposits · Trade flow · Income (mint value) · Fees & corrections. Sub-texts come from the design's `_cashVM` tiles.
- Ledger card:
  - Filter pills (`st.pills`): All · Deposits & withdrawals · Trades · Income · Fees & adjustments, with `N of M entries` on the right.
  - Newest first. Grid `96px 104px 1fr 132px 78px 118px 118px 60px`: Date · Type chip · Description (+ ref line in faint mono) · Original (`+USD 2,500.00`, or `set to €X` for an adjustment) · FX rate (+ `ECB` / `manual` in amber / `base`) · Amount · EUR (up-green when positive) · Balance · Source chip (Auto / Manual).
  - Automatic top-up deposits: the Deposit chip plus a `top-up` sub-label under the ref line.
  - Type-chip colours come from the design's `tS` map. Map `#FDF0E8` / `#854F0B` / `#C98A3A` to new `styles.py` tokens (`--warn-bg`, `--warn-txt`, `--warn-line`) with dark-theme variants, rather than hard-coding hex.
  - Long histories: render the first 200 filtered rows, then a "Show all" button. The whole ledger is kept indefinitely, so it can grow.
- The design's `§` spec-note blocks (`annOn`) are handoff annotations. **Do not ship them.** A short `st.caption` under the table carries the multi-currency explanation.
- Negative-history warning banner (D8), shown only when triggered.
- Navigation: allow `?section=cash` on `/portfolio` so the Risk banner's "View cash activity" link and the strip's ⤢ icon can deep-link. Top-nav clicks don't register in the preview browser, so URL navigation is the tested path.

### WP-CM8 · Dashboard and Risk integration

- **Dashboard** KPI strip per D9:
  - Current value = market value + cash, with sub-text `incl. €X cash`.
  - The new **Cash** tile: value, a mint `%` chip, sub-text `of total value · not in risk`.
  - The skeleton row keeps 5 cards.
- `record_value_snapshot` gains an optional `cash` column (older rows backfill to 0). The value chart stays invested-only in v1, so its line doesn't jump on the day cash tracking starts. Changing that is a separate, deliberate follow-up.
- **Risk page:** under the heading, a bordered info banner: `Risk metrics cover the invested portion only (€X). Cash of €Y, Z% of total value, is excluded from HHI, VaR, CVaR, factor exposure and Monte Carlo.` plus a **View cash activity** link. No change to `risk.py`. Add a regression test showing that `risk.py` inputs are unchanged by a non-zero cash ledger.

### WP-CM9 · CSV export

- `cash.export_csv()` writes columns in the spec's order and names:
  `date,type,amount,currency,fx_rate,amount_base,note,reference,running_balance` (header suffix `_eur` when base = EUR, as in the design: `amount_eur`, `running_balance_eur`).
- ISO dates, full history, oldest first, `QUOTE_MINIMAL`, UTF-8 **without** a BOM (as built — matches every other Uvalu CSV export, which are plain `to_csv()` strings). An adjustment's `amount` is blank; its `amount_base` holds the delta. As built there is one extra trailing column, `fx_source` (`base` / `ecb` / `manual`), so a manually entered rate stays flagged in the export as well.
- File name `uvalu-cash-activity-EUR.csv`. Uses `st.download_button` (all roles).
- Test: column order, running balance matches `replay`, quoting of commas and quotes in notes.

### WP-CM10 · Backup, retention, docs, release

- `backup.py`: add `cash.json`, `portfolio_meta.json` and `dividend_meta.json` to `_PORTFOLIO_FILENAMES`. Round-trip test. This also closes `docs/backend-feature-gaps.md` §3.
- Retention: the ledger lives in `data/portfolio/<user>/`, which `logkit.retention` never touches. Add a test asserting the retention purge ignores `data/`, so the "retained indefinitely" rule is enforced by a test.
- Docs:
  - `docs/data-contracts.md`: the cash ledger contract, the top-up rule, and FX provenance (frankfurter / ECB is the single source).
  - `docs/portfolio_risk_assessment_algorithm.md`: the EUR restatement now uses ECB reference rates.
  - `docs/architecture.md`: new `fx.py` / `cash.py` modules.
  - `docs/user-guide.md`: a Cash section.
  - `docs/configuration.md`: frankfurter endpoint and timeout, if configurable.
  - `docs/backend-feature-gaps.md`: mark §3 resolved.
- `CHANGELOG.md` `[1.12.0]`, including a "Changed" note that FX now comes from ECB via frankfurter for dividends and risk, so non-EUR figures may shift slightly. Bump `pyproject.toml`, `--no-ff` merge, tag on the merge commit, GitHub Release (same checklist as v1.11.0).

---

## 6. Order and dependencies

```
CM0 ──► CM1 ──► CM2 ──┬─► CM3 ──► CM5
                      ├─► CM4
                      ├─► CM6
                      └─► CM9
CM2 + CM6 ──► CM7 ──► CM8 ──► CM10
```

Suggested commits, each green on its own:

1. CM0
2. CM1 + CM2 (domain only, no UI)
3. CM3 + CM5
4. CM4
5. CM6
6. CM7 + CM9
7. CM8
8. CM10

## 7. Verification

- Unit: `tests/test_fx.py`, `tests/test_cash.py`, plus additions to `test_portfolio.py`, `test_dialogs.py`, `test_pages_portfolio.py`, `test_pages_dashboard.py`, `test_pages_risk.py`, `test_backup.py`, `test_data_contracts.py`.
- Full suite must stay green (currently ~1000+ tests).
- Live check with `/run-uvalu`. Screenshots in dark and light theme of:
  - the Portfolio overview with the strip;
  - the Cash activity page (Owner and Viewer);
  - the Add cash transaction dialog in auto-FX, manual-FX and outage states (outage simulated by pointing the endpoint at an unroutable host);
  - a Buy above the balance showing the top-up line, and the resulting top-up + Buy rows in the ledger;
  - a before/after comparison of Risk page metrics and Dividends-page EUR totals, to confirm the FX-source switch changes them only slightly;
  - the Dashboard KPI strip;
  - the Risk banner.
- Manual reconciliation: seed the design's 20 sample entries and 13 sample dividends, then confirm the final balance matches the prototype's `_cashBal()`. The dividend rows will differ by a few cents because the prototype hard-codes its sample rates (`fxDiv`).

## 8. Out of scope (per spec §Deferred)

True multi-currency ledger, broker API sync, CSV/bulk import of cash history, cash in risk models, date-range filter on export, a choosable non-EUR base currency.
