# Architecture review: exchange expansion plan

16 Oct 2026. Written in the role of the **Tech Lead / Software Architect** profile in [rnd-role-profiles.md](team/rnd-role-profiles.md), with the **Data Engineer** view (freshness, idempotency, data quality, vendor lock-in). It reviews the [exchange expansion plan](exchange-expansion-plan.md) against the code on master `a4ee4ad`. Like the other persona reviews, it is a first pass and doesn't replace a person in the role.

**Evidence used:**
- the code paths named in each finding;
- `logs/uvalu.log*`: 218 `universe_rescore` jobs, 1,322 stockanalysis.com calls, 41 fetch jobs;
- `.cache/fundamentals.json` (8,281 rows, 16 Oct).

## Verdict

The plan's direction is right: one exchange registry, a primary-listing rule, units fixed where data enters, and fetch hygiene first. Four things need to change before implementation starts:

1. **The ticker-list cache has to come first.** List scraping takes 90% of every rebuild today (A1).
2. **Choosing one line per company needs data on every line.** It also needs to be stable over time, and neither is in the plan yet (A2, A3).
3. **Units must be fixed before the primary-listing rule**, because that rule compares trading values in EUR. Units also have to be fixed at the one place where all market data enters, or dividend income for London holdings is 100× too high (A4).
4. **The cache file is written non-atomically**, and the fetch load is about twice what the plan assumed (A8, A9).

## Findings

| # | Finding | Severity |
|---|---|---|
| A1 | List scraping is 55 of the 61 seconds of every rebuild | High |
| A2 | The primary-listing rule needs secondary lines fetched, and §6 doesn't count them | High |
| A3 | The chosen line can flip between exchanges | High |
| A4 | Units have to be normalised at the source, before EX-W4 | High |
| A5 | The scored result is a positional tuple, one slot per exchange | Medium |
| A6 | Migration m0003 has two scopes, and renaming a key is not needed | Medium |
| A7 | A partial scrape can silently shrink the universe | Medium |
| A8 | The cache file is written non-atomically | Medium |
| A9 | Thin rows are fetched 8× a day; the load estimate is about half the real figure | Medium |
| A10 | Tests must stay network-free | Medium |
| A11 | Store provider-neutral fields now, for the EODHD switch | Low |
| A12 | The shared cool-down covers one process only | Low |

### A1. List scraping is 55 of the 61 seconds of every rebuild (high)

The median `universe_rescore` job takes **60.6 s** (max 108 s, 218 runs). The six stockanalysis.com scrapes inside it take a combined median of **55.3 s**:

| Exchange | Median |
|---|---|
| Frankfurt (22 pages) | 40.3 s |
| Milan | 5.3 s |
| Zurich | 4.0 s |
| Paris | 3.3 s |
| Amsterdam | 1.2 s |
| Brussels | 1.2 s |

**Scoring itself takes about 5 s.** With 21 exchanges (London 8 pages, Vienna 3, Warsaw and Stockholm 2 each), a rebuild without a list cache would take around 100 s and send about 50 page requests every time.

**Recommendations:**
- Move EX-12 (the ticker-list cache) to the very first package.
- Refresh lists on their own daily schedule, never inside a rebuild.
- Expected result: rebuilds of about 5–10 s even with the doubled universe. That also makes the "debounced rebuild during a fetch" (WP-1) much cheaper.

### A2. The primary-listing rule needs secondary lines fetched (high)

To choose between Airbus `.PA`, `.DE` and `.MC`, the build needs each line's country, name, share count and traded value. That means fetching every European company's secondary lines: Nestlé, Roche and Airbus on Frankfurt, the Nordea and Nokia lines on the Nordic exchanges, the European lines on Vienna's global segment, and so on. Today `known_foreign` stops refetching a line only when the company is non-European. A European company's secondary line is fetched every day, and §6 doesn't count these lines.

**Recommendations:**
- Once a line is known to be secondary, fetch it on a slow schedule (weekly). Fetch only what the comparison needs: price, volume, country, name and shares, using `fast_info`, not the full statements.
- Save the choice per company (A3), so a daily rebuild doesn't need fresh data on every line.

### A3. The chosen line can flip between exchanges (high)

"Most-traded line" (D1) is a daily measurement. For companies traded similarly in two places (STMicro in Paris and Milan, Stellantis in Milan and Paris, ArcelorMittal on three exchanges), the winner can change from one day to the next. Everything downstream is keyed by ticker:
- signal history and the daily snapshot (`uvalu/compliance/signal_history.py`);
- signal hysteresis (`_apply_signal_hysteresis`);
- watchlists, manual tickers, and the Q1 flicker measurement.

A flip would show as one stock disappearing and another appearing, with a fresh signal and no history.

**Recommendations:**
- Save the choice in `.cache/listing_choice.json`: company → chosen ticker, the date chosen, and the reason.
- Only switch when another line has traded at least 2× more over 20 days, in two weekly checks in a row.
- Log each switch as `listing.switched`, and carry the signal history and hysteresis state over to the new ticker.
- For the home-exchange case (Shell → London), the choice is fixed, with no measurement.

### A4. Normalise units at the source, before EX-W4 (high)

Pence enter the app in four places:
- `_fetch_one` (fundamentals);
- the live price batch (`uvalu/data.py`, `_fetch_prices_batch`);
- `marketdata.history`;
- `marketdata.dividends`.

`marketdata.dividends` is also read by the **portfolio's dividend auto-import** (`portfolio.py:825`), which multiplies the amount per share by the shares held. Without a fix at the source, a London holding's dividend income would be 100× too high in the cash ledger and on the Dashboard. The DPS growth statistics in `screener._dividend_stats` only use ratios, so they're safe either way.

**Recommendations:**
- Normalise inside `marketdata` and `_fetch_one`, so every consumer sees major units. Don't fix it per consumer.
- Add a test that runs every price and dividend path with a GBp fixture.
- Change the history/dividend cache key or version, so no file cached in pence is read back as pounds.
- **Run EX-W5 before EX-W4.** The primary-listing rule compares traded value in EUR, which needs correct units first.

### A5. The scored result is a positional tuple per exchange (medium)

`_build_all_screener_data` returns one frame per exchange in `ALL_EXCHANGES` order plus an extra frame. `uvalu/store.py:26` sizes its empty value from that list, and Screener, Watchlist and Analysis each `zip(ALL_EXCHANGES, dfs)`. At 21 positions this coupling gets fragile (a reordered list silently mislabels a market). It also fits badly with a rule that picks lines across exchanges.

**Recommendation:** in EX-W2, return **one scored frame with an `exchange_key` column** plus the extra-tickers frame. Pages filter by column. The registry supplies the labels.

### A6. Migration m0003 has two scopes; a key rename is not needed (medium)

- `enabled_exchanges` lives in `data/settings/shared.json` (encrypted). Dividend withholding is **per user** (`settings.load_settings(email)`, one file per user). m0003 must handle both, using the existing `ctx.settings_files()` / `ctx.user_dirs()` helpers. It must be safe to run twice, and an exchange a user explicitly switched off must stay off.
- **D10 ("Swiss" → "Zurich") should change only the label, not the internal key `swiss`.** Renaming the key would ripple through the saved settings, withholding, tests and logs, for no visible gain.

### A7. A partial scrape can silently shrink the universe (medium)

`_fetch_via_stockanalysis` returns whatever it collected before a page failed. Its fallback only covers an exception or an empty result. If page 5 of 8 times out, or the site changes its layout and serves fewer rows, the build uses a smaller list without telling anyone.

**Recommendations:**
- In the list cache, keep the last good list when a new scrape has less than 70% of its rows, and log `tickers.shrunk`.
- Write the cache files atomically.
- Record the list date in the build's data-quality summary (lineage).

### A8. The cache file is written non-atomically (medium)

`_save_cache` does `cache_file.write_text(json.dumps(cache, indent=2))` (`screener.py:557`), every 25 tickers, on a 14 MB file that grows to about 20+ MB. A crash or restart mid-write leaves a truncated file. `_load_cache` then returns `{}`, and the next build fetches the **whole universe** again: several hours of Yahoo calls, with "No signal" everywhere in the meantime.

**Recommendations:**
- Write to a temporary file and `os.replace` it (atomic on Windows and Linux).
- Drop `indent=2` (about a third smaller and faster to parse).
- Keep JSON for now. SQLite or Parquet belongs to the SaaS migration, not this plan.

### A9. Thin rows are fetched 8× a day; the load estimate is about half (medium)

On 16 Oct, **992 of the 4,059 priced rows (24%) were on the 3-hour short TTL** (WP-A). That's meant for transient partial payloads, but a company that is always data-poor stays there and is fetched about 8 times a day, which is roughly 7,900 fetches. Real daily load today is therefore about:

| Rows | Fetches per day |
|---|---|
| Normal rows: 3,067 × 1 | ~3,070 |
| Thin rows: 992 × 8 | ~7,940 |
| Dead rows: ~4,100 × 1 | ~4,100 |
| **Total** | **~15,100**, about 11 hours at 0.38 per second |

The plan's §6 figure of ~8,200 is too low. The thin markets (Athens, the Baltics, Iceland, Warsaw) would add many more always-thin rows.

**Recommendation:** add to EX-W1 an escalating short TTL for rows that stay thin: 3 h → 12 h → 24 h, then the normal TTL, resetting when a full row comes back. Together with EX-19, today's load drops to about 5,000/day (3,070 normal + about 1,500 thin + about 400 dead). The expansion then lands at about 8,000–9,000/day, still below today.

### A10. Tests must stay network-free (medium)

The CI suite runs with a no-network check. Three new parts must come with fixtures, not live calls:
- the ticker-list cache;
- `tools/refresh_index_members.py`;
- the FX test for the new currencies (EX-16).

Probe scripts like the ones used for this plan belong in `tools/`, not `tests/`.

### A11. Store provider-neutral fields now (low)

The registry's ticker conversion (EX-40) works for the EODHD switch. To make that switch easier, also store `exchange_key` and the exchange's own symbol (`INVE B`) on each fundamentals row now. The EODHD mapping can then be checked against stored data instead of re-scraping lists. It costs two fields.

### A12. The shared cool-down covers one process (low)

EX-20's shared cool-down is in memory, so it coordinates the threads of one process. That's fine for the current deployment (one Streamlit process). Write it down as an assumption in `docs/architecture.md`, so a future second worker process doesn't double the Yahoo traffic unnoticed.

## Proposed order of work packages

| Order | Package | Change from the plan |
|---|---|---|
| 1 | EX-W0: the euro sign on Zurich prices (D15) | as proposed |
| 2 | EX-W1a: ticker-list cache with shrink guard | moved out of EX-W3 (A1, A7) |
| 3 | EX-W1: fetch hygiene + atomic cache write + escalating short TTL | A8 and A9 added |
| 4 | EX-W2: registry + single scored frame | A5 added; D10 label only (A6) |
| 5 | **EX-W5: units at the source** | moved before EX-W4 (A4) |
| 6 | EX-W3: equity filters, symbol mapping, share classes | list cache removed (now EX-W1a) |
| 7 | EX-W4: primary listing, with saved and stable choices and slow secondary-line fetches | A2 and A3 added |
| 8 onward | EX-W6 … EX-W12 | as planned, plus the model review's shadow build (see [model-review-exchange-expansion.md](model-review-exchange-expansion.md)) |

Packages 1–4 change no signals and can start before 21 October.
