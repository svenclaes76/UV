# Exchange expansion and index filter: plan

*Draft for review, 16 October 2026. Nothing is implemented yet.*

The Screener covers six exchanges today: Brussels, Amsterdam, Paris, Milan, Frankfurt and Zurich (SIX). This plan:

- adds **15 exchanges**: the 12 you listed, plus Stockholm, Vienna and Warsaw;
- changes the coverage rule to **one line per company, on its primary listing**, so Airbus (a Dutch company) is back in the universe, on Paris;
- adds an **Index** filter next to Market on the Screener (Euro Stoxx 50, Stoxx Europe 50 and every national blue-chip index);
- fixes the problems found in the current design that matter more once the universe doubles (§3);
- shows every price in its own currency (today Zurich prices show "€" in Screener rows), always written as a three-letter code (`EUR 55.86`, never `€`), and sets dividend withholding per country instead of per exchange.

Contents: [1 Decisions](#1-decisions-for-you) · [2 Requirements](#2-requirements) · [3 Review of the current design](#3-review-of-the-current-design) · [4 Exchanges](#4-exchanges) · [5 Indices](#5-indices) · [6 Load estimate](#6-load-estimate) · [7 Work packages](#7-work-packages) · [8 Tests](#8-tests) · [9 Timing and gates](#9-timing-and-gates)

---

## 0. Decisions taken (17 Oct 2026)

Sven answered the open decisions on 17 Oct. **Where this section differs from a table below, this section wins.**

| Topic | Decision | Plan items |
|---|---|---|
| Sequencing vs. EODHD | **Build the provider-neutral parts now** (fix, list cache, fetch hygiene, registry, units, currency/UI, model fixes); keep the Yahoo/stockanalysis-specific EX-W3/W4 thin; send the EODHD questions first, including the 15 exchanges, index lists and stockanalysis.com | §7 order, L2 |
| Releases | **Three releases:** R1 = EX-W0, W1a, W1, W2 (no signal change); R2 = model M5 + units + batch 1 + Index filter; R3 = London + batch 3 | §9 |
| Go-live | **All new exchanges on at release** (D9 as first written; the per-exchange gate in D36 is dropped). A **one-week hidden shadow build still runs before R2 as a check**: it reports the per-market signal mix and data quality, and you decide on the release with those numbers. Admins can still switch any exchange off. | D9, D36 |
| Scope | **All 15:** Athens, Copenhagen, Dublin, Helsinki, Reykjavik, Lisbon, London, Madrid, Oslo, Riga, Stockholm, Tallinn, Vienna, Vilnius, Warsaw | EX-1, D6 |
| Line per company | **Home exchange if listed there, otherwise the most-traded line**, with the stable switching rule | D1, D32 |
| Non-European companies | **Excluded, except a hand-reviewed allow-list** | D2, D3 |
| London funds | **Excluded** (closed-end funds, non-equity lines) | D5 |
| Share classes | **Every class kept**, labelled "· A shares" / "· B shares" | D4, D20 |
| Market filter | **Multiple choice, options "Official name · Country"** ("Euronext Brussels · Belgium"), sorted by country | D18 |
| Indices | **Euro Stoxx 50, Stoxx Europe 50 and one blue-chip index per market** | D7 |
| Where the Index filter appears | **Screener and Analysis**, plus **index tags in the drawer** (max 2 + "+n"); not on the Watchlist | EX-24, EX-28, EX-29 |
| Exchange names | **Official exchange names + country everywhere**: Market filter, Exchange column (Analysis, export), drawer, venue-badge tooltip, Admin and Settings. `.DE` is **Xetra**. Names aren't translated; country names come translated from the locale data. Internal keys stay as they are (`swiss`, `frankfurt` …). Replaces the "Zurich" rename. | D10, D11, D30 |
| Currency notation | **Codes always** (EUR 55.86), no symbols; brand guidelines v1.4 | D14, EX-41 |
| Own-currency line | **Everywhere** a foreign amount appears | D25, EX-42 |
| Large prices | **No decimals from 1,000 up** (brand v1.4 exception) | D22 |
| Withholding | **Per company country, prefilled with statutory rates**, editable with "Reset to default"; existing values kept | D13, §5b |
| Discount rate | **Risk-free rate per currency** (10-year government yield, official data, quarterly) | D33 |
| Peer group | **Decide on evidence** in the shadow build: pooled stays unless one market's Undervalued share exceeds 3× the average, then sector × region | D37 |
| Liquidity | **Traded value in EUR**, bands calibrated on today's universe | D35 |
| Model version | D33/D35 change today's scores too, so **`MODEL_VERSION` M4 → M5**, with a methodology change-log entry and an explanation in the release notes | R2 |
| stockanalysis.com | Not disclosed as a source today: **added to L2** (terms of use, listing on the Data sources page) | L2 |

All other proposals (D11–D38 not named above) are accepted as recommended.

---

## 1. Decisions for you

Each decision has a recommendation. Unless you say otherwise, the plan follows it.

| # | Decision | Recommendation | Why |
|---|---|---|---|
| D1 | Which line represents a company listed on several covered exchanges? | **Its home exchange if it is listed there, otherwise its most-traded line** (average volume × price, in EUR). | This is what review #5 already recommended ("one line per company, its primary or most liquid listing"). Shell and Unilever → London, Nordea → Helsinki, Airbus → Paris, ArcelorMittal → its most-traded line. |
| D2 | Companies registered outside Europe (US stocks traded in Frankfurt, Vienna or Warsaw) | **Leave them out, except an allow-list** of companies whose primary listing really is in Europe (for example Hafnia, registered in Singapore, primary listing Oslo). | Removing them was the point of V2. The allow-list starts small and is reviewed by hand. |
| D3 | What counts as "Europe" for D2 | **EEA + UK + Switzerland + the Crown dependencies (Jersey, Guernsey, Isle of Man) + Gibraltar, Monaco, Liechtenstein.** Bermuda and other offshore registrations go through the D2 allow-list. | Glencore (Jersey/Switzerland), WPP (Jersey) and the Cyprus shipping companies on Oslo stay in. |
| D4 | Different share classes of one company on one exchange (VOLV-A / VOLV-B, Maersk A / B, Henkel / Henkel Vz.) | **Keep every class, as today.** Removing duplicates only works across different exchanges. | They are separate instruments with different prices and dividends. Users hold specific classes. |
| D5 | London: investment trusts and closed-end funds | **Leave them out** (Yahoo industry "Closed-End Fund …", or a quote type other than EQUITY). | They are funds, not companies. The valuation models don't fit them, and there are hundreds. |
| D6 | Warsaw (PLN) | **Include it, in the last batch.** | It is the largest market in Central and Eastern Europe. It is cheap once the generic pieces exist. Drop it if you want to stay Western Europe only. |
| D7 | Which indices to offer in the filter | **Euro Stoxx 50, Stoxx Europe 50, and one blue-chip index per covered market** (list in §5). No second-tier indices (MDAX, SBF 120, FTSE 250) in this first version. | Keeps the dropdown short and the snapshot easy to maintain. Second-tier indices can come later. |
| D8 | Where index members come from | **A committed snapshot in the repo** with an "as of" date per index, refreshed by hand each quarter with a helper script that drafts the changes. No scraping at run time. | §3 F6 and §5: Wikipedia tables are inconsistent; some are missing or include former members. Index reviews are quarterly, so a quarterly refresh is enough. |
| D9 | Which new exchanges are enabled by default | ~~All of them~~ **Each one once it passes the go/no-go after the shadow build (D36)**, through migration m0003. Admins can still switch any exchange on or off in Admin → Data feeds. | Otherwise existing installs keep the six exchanges saved in `shared.json` and never see the new ones. |
| D10 | How exchanges are named | **Official name + country, everywhere** (decided 17 Oct): "Euronext Brussels · Belgium", "Xetra · Germany", "SIX Swiss Exchange · Switzerland". The full list is in §4. Names live only in the registry, so a rename (Athens → Euronext Athens, April 2026) is one line. | Admin and Settings already use official names; the Screener's city labels were the odd one out. One name per exchange everywhere. |
| D11 | Translation of names in the Market and Index filters | **Exchange and index names are never translated** (proper names). **Country names are translated** from the locale data (Babel), and "All markets" / "All indices" through the usual i18n flow. | Fewer strings to translate, and a name is the same in every language. |
| D12 | Which ticker format users see | **Keep Yahoo's format (`INVE-B.ST`) as the stored key for now, and show it as today.** Make the registry the only place that converts between formats, so the EODHD switch only changes the registry. Showing the exchange's own symbol ("INVE B") is a later option. | Ticker formats belong to each data vendor, not to the exchange (EX-40). Yahoo-format tickers are already stored in every user's portfolio, watchlist and import files, so changing the stored key now would need a data migration for no visible gain. |
| D14 | How a currency is written | **Always the three-letter code, never a symbol:** `EUR 55.86`, `GBP 2.10`, `CHF 12.40`, `SEK 422.60`, in every language, for prices and totals alike. The region still decides the number format and where the code goes (`EUR 55,86` in nl-BE, `55,86 EUR` in de-DE). | Symbols can't work for every currency: "kr" means SEK, NOK, DKK and ISK alike, and today's formatter already mixes them (en-GB: `€1,234.50`, `£1,234.50`, but `CHF1,234.50`, `SEK1,234.50`). Codes are the only rule that stays the same everywhere. This changes the brand guidelines (§ numbers, which show `€42.80`), so it needs a v1.4 entry. |
| D13 | Dividend withholding: per exchange or per country | **Per country of the company (where it is registered), one row per country, prefilled with that country's statutory rate (§5b) and editable in Settings.** Use the exchange's country when the company's country is unknown. | Withholding is charged by the country the company is registered in, not by the exchange. Airbus pays Dutch withholding, even though it trades in Paris. With per-exchange rates, the primary-listing rule (EX-4) would give the wrong default. |

### From the UX review (16 Oct)

The [UX review](ux-review-exchange-expansion.md) (expert profile 08) proposes these changes. They are not yet in the requirements below; once you approve them, they are added to the matching work package.

| # | Change | From | Work package |
|---|---|---|---|
| D15 | **Fix the euro sign on Zurich prices now**, as its own small release, before any new exchange (EX-39 for the Screener and Watchlist rows and the drawer) | X1 | new EX-W0 |
| D16 | **Sort Price on its value in the user's own currency** while showing the native price; the converted value is shown under it (D25) | X2 | EX-W11b |
| D17 | **Index selected → the headline names it and counts members** ("23 of 50 Euro Stoxx 50 members pass your filters"), says which filters hide members, and offers "Show all members"; done together with U1 (show active default filters) | X3 | EX-W10 |
| D18 | **Market as multiple choice, options "Official name · Country"**, sorted by country | X4 | EX-W10 |
| D19 | **"Hide positions I own" and "you hold this" match by company, not ticker** | X5 | EX-W4 |
| D20 | **Share class in the name** ("Investor AB · B shares"); search finds "NOVO B" / "NOVO.B" | X6 | EX-W3 |
| D21 | **Markets still being added are marked** in the Market list with their progress, with an explaining empty state; release on a warmed server | X7 | EX-W6 |
| D22 | **Price column: code small and muted; no decimals from 1,000 up** (brand v1.4 exception) | X8 | EX-W11b |
| D23 | **Withholding: held countries first, others collapsed; Belgium shown as an explanation, not a field; help text with the Airbus example; one-time notice after the migration** | X9 | EX-W11b |
| D25 | **Every foreign-currency amount also shows its value in the user's own currency**, on a second line in small muted type, the same style as the "… gross" line in the dividend list (EX-42). This replaces the tooltip in D16. | your request, 16 Oct | EX-W11b |
| D24 | **Venue badge tooltip** with the official name and country ("Nasdaq Copenhagen · Denmark"); **drawer index tags** at most two plus "+n" | X11, X12 | EX-W10 |

### From the architecture and model reviews (16 Oct)

Proposed in the [architecture review](architecture-review-exchange-expansion.md) (Tech Lead / Architect with the Data Engineer view) and the [model review](model-review-exchange-expansion.md) (Valuation 05 + Quant 06). Like D15–D25, they are proposals until you approve them.

| # | Change | From | Work package |
|---|---|---|---|
| D26 | **Ticker-list cache first**, with lists refreshed on their own daily schedule and never inside a rebuild. Rebuilds go from ~61 s (55 s of it scraping) to ~5–10 s. | A1 | EX-W1a (new, 2nd) |
| D27 | **Shrink guard:** a scrape with less than 70% of the last good list keeps the last good list and logs `tickers.shrunk`; list files written atomically | A7 | EX-W1a |
| D28 | **Atomic cache write** (temp file + `os.replace`) and no `indent=2` | A8 | EX-W1 |
| D29 | **Escalating short TTL** for rows that stay thin: 3 h → 12 h → 24 h → normal | A9 | EX-W1 |
| D30 | **One scored frame with an `exchange_key` column** instead of a tuple per exchange; the new official names (D10) are label changes only, the keys stay `swiss`, `frankfurt` … | A5, A6 | EX-W2 |
| D31 | **Units normalised at the source** (`_fetch_one`, live prices, `marketdata.history` / `dividends`), history cache versioned; **EX-W5 runs before EX-W4** | A4 | EX-W5 |
| D32 | **Saved, stable line choice per company:** switch only at ≥2× traded value over 20 days in two weekly checks; signal history and hysteresis carried over; secondary lines fetched weekly with a light call | A2, A3, M7 | EX-W4 |
| D33 | **Risk-free rate per currency** (10-year government yield from official data, quarterly); ISK and PLN stay out of Undervalued until it's in | M2 | new EX-W5b |
| D34 | **EPV tax:** 0% or near-0% registrations use the 25% default; Estonia and Latvia use the distribution rate | M3 | EX-W5b |
| D35 | **Liquidity on traded value in EUR**, bands calibrated so today's scores barely move | M5 | EX-W5b |
| D36 | **Shadow build for a week after 21 Oct, then go/no-go per exchange** (≥60% with a fair value, <5% `currency_unverified`, Undervalued ≤3× the universe, London golden sample passes). **Replaces "all on" in D9.** | M6, M4, M8 | EX-W6–W8 |
| D37 | **Per-exchange signal mix and median P/E** in the data-quality summary with a >3× alert; compare pooled vs. sector × region medians in the shadow build | M1 | EX-W11 |
| D38 | Network-free fixtures for the list cache, index script and FX; `exchange_key` and the exchange's own symbol stored on each row; the one-process cool-down written down in `architecture.md`; "not for backtests" note on the index snapshot; per-market distribution on the methodology page | A10–A12, M9, M10 | as listed |

---

## 2. Requirements

Requirement IDs (EX-…) are referenced by the work packages in §7 and the tests in §8.

### Coverage

- **EX-1** The universe covers 21 exchanges: the six current ones plus Athens, Copenhagen, Dublin, Helsinki, Iceland (Reykjavik), Lisbon, London, Madrid, Oslo, Riga, Stockholm, Tallinn, Vienna, Vilnius and Warsaw (D6).
- **EX-2** Each exchange can still be switched on or off in Admin → Data feeds. A disabled exchange is left out of the universe, and holdings on it are still scored as extra tickers (PER-2, unchanged).
- **EX-3** **All the facts about an exchange live in one registry**: key, official name, country, Yahoo suffix, MIC, list URL, currency, symbol mapping, equity filter, fallback index and time zone. Every other module reads from it. Today the same facts are copied into about ten files (§3 F7).

### Which listing represents a company (replaces the home-listing rule)

- **EX-4** A listing is in the public universe when it is the company's **primary listing** among the enabled exchanges:
  1. the company is registered in a D3 European country, or is on the D2 allow-list;
  2. among that company's listings on different enabled exchanges, it is the home-exchange line, or, if there is none, the most-traded line (D1);
  3. it trades (confirmed average volume > 0, as today).
- **EX-5** "Same company" across exchanges = same normalised name (legal-form suffixes such as SA, AG, plc, ASA, AB, Oyj, N.V., S.p.A. removed, accents and case ignored) **and** same country. A pair is merged only when share counts are within 5% of each other (or one is missing). ISIN would be better, but the cache has none today (data-contracts "known residual gap"); EODHD provides it, and EX-5 switches to ISIN once it is available.
- **EX-6** If the chosen line's exchange is disabled, the next line in the D1 order is used. Switching off London does not make Shell disappear while it is still listed in Amsterdam.
- **EX-7** The Screener's Market filter keeps meaning "the exchange the listing trades on": Airbus shows under Paris, Nordea under Helsinki.
- **EX-8** Every listing that is left out records why (`not_european`, `secondary_listing`, `dormant`, `fund`, `country_unknown`). The build logs a count per reason per exchange, and the existing data-quality summary includes it.

### Ticker lists and filters

- **EX-9** Each exchange has its own equity filter. **The Frankfurt rule (`_is_equity_symbol`) and its self-learning exceptions file stay as they are, for Frankfurt only.** Its symbol-shape rules would reject valid Baltic tickers such as `TAL1T`. The exceptions mechanism becomes generic (one exceptions file per exchange) for exchanges that need it.
- **EX-10** Pre-filters run before any Yahoo call (they cost nothing):
  - **London:** drop symbols that start with a digit (2,948 of 3,591 lines are the international order book, `0R1I` …).
  - **Madrid:** drop the `X…` Latibex lines (Latin American companies).
  - **Stockholm / Copenhagen / Helsinki:** recognise currency-suffixed second lines (`NOKIA.SEK`, `SAMPO.DKK`, `NDA.SE`, `NDA.DK`) and fetch them only so EX-4 can choose between lines.
- **EX-11** Symbol mapping from stockanalysis.com to Yahoo: share-class dots become dashes (`INVE.B` → `INVE-B.ST`, `BT.A` → `BT-A.L`, `GRF.P` → `GRF-P.MC`, `NOVO.B` → `NOVO-B.CO`), then the exchange suffix is added. Each exchange's mapping is checked against a sample of real symbols.
- **EX-12** **Ticker lists are cached on disk** (one file per exchange, 24-hour time-to-live, last good list kept if a scrape fails). Today every universe rebuild scrapes every list again (§3 F5).
- **EX-13** The hardcoded fallback lists (BEL20, CAC40 …) are replaced by the index snapshot (§5), so there is one maintained list of index members, not two. Today's fallback lists are out of date: Atlantia, Tod's and CNH (Milan) and Just Eat Takeaway (Amsterdam) have left.

### Units and currencies

- **EX-14** **Prices are always in the main currency unit.** For London, Yahoo quotes in pence (`GBp`): price, previous close, 52-week range, price history and dividend history are in pence, while EPS, book value, market cap and `dividendRate` are in pounds (checked on BT-A.L and ULVR.L, 16 Oct). Every pence field is divided by 100 when it is fetched and `Currency` is stored as `GBP`. This covers the fundamentals fetch, the live price batch, price history (`marketdata.py`) and dividend history.
- **EX-15** `dividendRate` is checked against Yahoo's own `dividendYield` after EX-14. If it is off by about 100×, it is corrected and the row records that it was. (For Unilever on London, `dividendRate` looks like it is in EUR, the reporting currency.)
- **EX-16** New quote currencies: GBP, SEK, NOK, DKK, ISK, PLN. All are in the ECB reference rates that `fx.py` uses. A test confirms each one, ISK included.
- **EX-17** Users enter trade prices for London stocks in pounds, not pence. The trade dialog shows the currency next to the price field. Import from a broker file that gives pence is a separate question, out of scope here.
- **EX-18** `COUNTRY_TAX_RATES` gets the missing countries: Iceland, Estonia, Latvia, Lithuania, Cyprus, Malta, Jersey, Guernsey, Isle of Man, Bermuda. Headline rates as for the others, **except** that 0% or near-0% registrations use the 25% default and Estonia and Latvia use their distribution rate (D34, model review M3).

### Fetch load and back-off (§3 F1–F4)

- **EX-19** **Dead rows back off.** A row with no price and no country (a symbol Yahoo doesn't know) is retried after 1, 2, 4, 8, 16 days, then every 30 days, and goes back to daily as soon as a fetch returns a price. Today about 4,100 such rows are fetched again every day.
- **EX-20** **One rate-limit cool-down shared by all workers in both lanes.** When any worker gets a 429, all workers pause until the cool-down ends, instead of three workers carrying on while one waits.
- **EX-21** A not-found (404) result gets a `next_fetch_at` like any other failure, so it isn't fetched again on every rebuild.
- **EX-22** Rows for tickers that have been in no list and no portfolio for 30 days are removed from the cache file (today they stay forever, for example `COFB.BR`).
- **EX-23** The first fetch of a new exchange is spread out: new exchanges are queued behind existing stale rows (portfolio first, as today), so adding London never delays a holding's refresh.

### Index filter

- **EX-24** The Screener's filter bar gets an **Index** dropdown right after **Market**. Default "All indices". It works together with Market and the other filters ("Madrid" + "Euro Stoxx 50" = Santander, BBVA, Iberdrola, Inditex …).
- **EX-25** The dropdown lists only indices with at least one member in the current universe, in a fixed order: Euro Stoxx 50, Stoxx Europe 50, then the national indices in alphabetical order.
- **EX-26** A member is matched to the universe's chosen line (EX-4), whatever ticker the index provider uses. Airbus in the DAX and the CAC 40 matches `AIR.PA`. A member that matches no row is logged, so a stale snapshot shows up.
- **EX-27** The snapshot's "as of" date is shown in the Index filter's help tooltip: "Index members as of 30 Sep 2026. Updated each quarter."
- **EX-28** The drawer shows a stock's index memberships as small tags under its name (read-only, no extra data).
- **EX-29** Watchlist and Analysis get the same Index filter only if you want it (not in this scope by default).

### UI, text and settings

- **EX-30** The Market filter lists the 21 exchanges as "Official name · Country", sorted by translated country name, as a multiple choice (D18). Selected markets show as chips; check that several long chips ("London Stock Exchange · United Kingdom") wrap cleanly at 1024 px.
- **EX-31** Exchange and index names stay untranslated (D11). Country names come from the locale data. "All markets", "All indices", "· A shares" / "· B shares" and the new help texts are translated into all six languages and reviewed through the usual i18n review CSV.
- **EX-32** Everything that says "six exchanges" is updated: the sign-in screen stat ("6"), the Data sources page, methodology, help, `docs/configuration.md`, `docs/architecture.md`, the user guide, the legal pages that describe coverage, and the release notes.
- **EX-33** **Dividend withholding is set per country, one row per country** (D13), replacing the per-exchange grid of three per row. Each row: the country name (translated), then the % field. One row per covered country plus the D3 countries that occur in the universe (Luxembourg, Jersey …), sorted by translated name. **Each country starts at its statutory rate from §5b** instead of 0%. The user can change any rate. A changed rate is marked "your rate" with a "Reset to default" link, and an unchanged one is marked "default". The defaults live in one country table (next to `COUNTRY_TAX_RATES`, which moves there from `screener.py`), with the date they were last checked. The dividend dialog takes its default from the holding's company country, falling back to its exchange's country. Migration m0003 copies each current per-exchange value to that exchange's country (brussels → Belgium, swiss → Switzerland …), so no value a user entered is lost. The workbook's settings sheet lists the rates by country as well.
- **EX-34** Market hours: the shared 09:00–17:30 CET window stays. London, Dublin and Lisbon fit it exactly; Oslo, Helsinki, Athens, Iceland and the Baltics close a little earlier, which only affects the price-refresh rate. The module docstring is updated.

### Currency in every price field

- **EX-39** **Every price is shown in its own currency.** Per-share figures (price, fair value, the fair-value models, the sensitivity table, 52-week range, dividend per share, trade price, dividend amount) are shown in the listing's quote currency, using the registry and the row's `Currency`. Totals (position value, P&L, portfolio, cash, income) are shown in the user's display currency (`fmt_total`), as today, with "≈" where they were converted. No price is formatted with a hardcoded currency. Already wrong today: Screener and Watchlist rows format every price as EUR (`stock_row`, `uvalu/components.py:1209`), so Zurich stocks show "€" for CHF prices. The audit covers all 32 `fmt_money(…, "EUR")` calls and the 4 helpers with a `currency="€"` default, page by page: Screener, Watchlist, drawer, Analysis, Dashboard, Portfolio, Risk, the trade / dividend / cash dialogs, and the workbook export (currency column). A test fails if a per-share field is formatted without the row's currency.
- **EX-41** **One currency notation everywhere (D14).** `fmt_money`, `fmt_compact` and `fmt_total` write the ISO code in place of the symbol: the region's CLDR pattern with the code instead of the symbol, with a non-breaking space between code and number (CLDR otherwise glues them: `CHF1,234.50`). After this, no screen shows "€" or "£". Places that write a currency by hand change too:
  - the trade dialogs' "Total cost (€)" label (`uvalu/dialogs.py:407`, `:496`) becomes "Total cost ({currency})" with the trade's own currency, so a London buy reads "Total cost (GBP)";
  - the FX rate line in the cash dialog (`uvalu/dialogs.py:1029`, "1 SEK = €") and the conversion note (`uvalu/i18n.py:1310`, "… EUR") use codes on both sides;
  - the `currency="€"` defaults in `uvalu/components.py` (4 helpers) become a required currency code (EX-39);
  - the text-width table used for column sizing (`uvalu/components.py:381`) is checked for the wider code.
  
  Import keeps accepting "€", "£" and codes in uploaded files (`workbook.py:434`), and Excel export keeps a separate Currency column. The brand guidelines' numbers section and its examples are updated to `EUR 42.80` (v1.4). Every locale gets a test: no currency symbol in any formatted amount, and the code sits where the region puts it.
- **EX-42** **A foreign-currency amount also shows its value in the user's own currency (D25).** "Own currency" is the display currency from the user's region setting (EUR for most users today). When a per-share amount is in another currency, a second line under it shows the converted value, marked "≈": 10–10.5 px, monospace, muted, right-aligned, the same style as the "… gross" line in the dividend list (`uvalu/components.py:546`). Example: `SEK 422.60` with `≈ EUR 38.40` underneath. Rules:
  - No second line when the amount is already in the user's currency, so a euro-only list looks as it does today.
  - It uses the same ECB rate as every other conversion (`fx.py`, through `to_display`); the existing conversion note ("Converted at … on …") explains the "≈".
  - Where: Screener and Watchlist rows (price), drawer and Analysis (price, fair value, the per-model fair values, 52-week range, dividend per share), Portfolio and Dashboard per-share columns (buy price, current price), the trade and dividend dialogs (live preview under the amount field), and the cash dialog's FX line. Export files keep the native amount and a separate converted column, not a second line.
  - If no rate is available, the second line is left out (never a wrong or zero value), and the row keeps its native amount.
  - Row height: the Screener and Watchlist rows already have two lines (ticker and name), so a second line under the price fits without making the row taller. Checked at 1440 and 1024 px in the visual check.
- **EX-40** **Ticker formats belong to the data vendor, not to the exchange.** The same Investor B share is `INVE B` at Nasdaq Stockholm, `INVE.B` on stockanalysis.com, `INVE-B.ST` at Yahoo, and different again at Bloomberg (`INVEB SS`) and LSEG (`INVEb.ST`). EODHD uses its own exchange codes too (for example `.LSE` for London, `.XETRA` for Xetra). The registry keeps, per exchange, the rules to convert from the list source to the stored key (Yahoo form, D12), and is the only code that knows them. The EODHD switch then adds a second conversion rule in the registry and nothing else.

### Model and signals

- **EX-35** Adding exchanges changes the peer group, so sector medians and percentile ranks move for everyone. The first build after the change writes `universe_change` as the changed input for each signal it changes, so the Q1 flicker numbers don't count it as noise. The release notes say signals were recalculated against a larger European peer group.
- **EX-36** Rows still flagged `currency_unverified` stay out of the peer group and out of Undervalued, as today. The data-quality alert thresholds are checked against the new mix after the first full build.

### Legal and licensing

- **EX-37** Add to the L2 / EODHD question list: does the plan cover display of LSE, Nasdaq Nordic & Baltic, BME, Athens, Euronext Dublin/Lisbon/Oslo, Wiener Börse and GPW data, and index constituent lists (STOXX, FTSE Russell, Euronext, Nasdaq)? Until L2 is settled, the existing rule stands: personal contacts only.
- **EX-38** Index names are used descriptively only, with no logos. Add a line to the Data sources page: index names are trademarks of their owners; Uvalu is not affiliated with them.

---

## 3. Review of the current design

You asked me to check the current algorithm in detail. The design is sound: two fetch lanes, carry-forward on partial fetches, jittered time-to-live, priority for holdings, one peer group, currency conversion. **The per-worker exponential back-off on 429 errors does exist** (`screener.py:1155–1177`: 5, 10, 20, 40 s, plus a refreshed crumb on 401). The findings below are problems that exist today and get worse with 21 exchanges. Each has evidence from the code, cache or logs.

| # | Finding | Evidence | Severity | Fixed by |
|---|---|---|---|---|
| F1 | **About half of each day's Yahoo calls go to symbols that return nothing.** 4,220 of 8,281 cached rows have no price; 4,127 of them were fetched again in October; 4,043 are Frankfurt lines that pass the symbol-shape filter but that Yahoo doesn't know. They have no country, so `known_foreign` never leaves them out. | `.cache/fundamentals.json`, 16 Oct | **High**: the main lever for absorbing the new exchanges | EX-19 |
| F2 | **Back-off is per worker, not shared.** When Yahoo rate-limits, the other three workers keep calling, and the portfolio lane and the live price batch call independently too. | `_fetch_and_store`, `MAX_WORKERS = 4`, two lanes | Medium; 77 rate-limit lines in the current logs | EX-20 |
| F3 | **A 404 stub has no `next_fetch_at`**, so it counts as stale on every rebuild and is fetched again. | `_is_fresh` returns False on `fetched_at == ""` | Low today (2 stubs), grows with new lists | EX-21 |
| F4 | **The cache is never pruned.** Rows for delisted tickers (`COFB.BR`, last fetched 12 Sep) stay in the 14 MB file that is parsed on cold start. | 93 rows last fetched before October | Low | EX-22 |
| F5 | **Ticker lists are scraped on every universe rebuild** (architecture review A1: 55 of the 61 s median rebuild). During a fetch, the 22-page Frankfurt list was scraped every ~2 minutes (15 Oct, 12:16–12:32). With 21 exchanges that is about 50 page requests per rebuild: slow builds, and a real chance of being blocked by stockanalysis.com. | `_build_all_screener_data` calls `fetch_fn()` each time; 1,322 stockanalysis log lines | **High** with 21 exchanges | EX-12 |
| F6 | **The fallback index lists are out of date** and duplicate what the Index filter needs. | Atlantia, Tod's, CNH in FTSE MIB; Just Eat in AEX | Low | EX-13 |
| F7 | **Exchange facts are copied into about ten places** that must all agree: `settings.py` (keys, labels), `universe.py` (country), `fetch_tickers.py` (URL, suffix, MIC, fallback), `uvalu/data.py` (fetch map), `portfolio.py` (currency), `formatting.py`, and `screener.py` / `watchlist.py` / `analysis.py` / `admin.py` (labels, suffixes). Adding 15 exchanges this way would make 150 edits that can drift apart. | grep of `ALL_EXCHANGES` / suffix maps | Medium | EX-3 |
| F8 | **The home-listing rule drops European companies registered in another country**: Airbus, Stellantis and STMicro (Dutch), ArcelorMittal (Luxembourg), Shell and Unilever on Amsterdam (UK). Airbus, a Euro Stoxx 50 member, is not in the universe today. | cache: `AIR.PA` country Netherlands, `MT.AS` Luxembourg | Medium; would break the Index filter | EX-4 |
| F9 | **Pence would make every London fair value wrong by 100×.** `_convert_reporting_currency` upper-cases `GBp` to `GBP`, so it sees no mismatch, and it recomputes P/E as price ÷ EPS, also 100× off. | BT-A.L: price 209.7 GBp, EPS 0.11 GBP | **High** for London | EX-14, EX-15 |

Throughput, measured from 41 fetch jobs in the logs: **0.38 tickers per second** (range 0.28–0.57) with 4 workers, about 33,000 tickers per day if it ran non-stop. §6 uses this figure.

---

## 4. Exchanges

All suffixes were checked against Yahoo on 16 Oct with a real ticker, and all list pages against stockanalysis.com. "Lines" is the raw list size before filters.

| Batch | Name shown (D10) | Country | Suffix | MIC | stockanalysis list | Lines | Currency | Special handling |
|---|---|---|---|---|---|---|---|---|
| 1 | Bolsa de Madrid | Spain | `.MC` | XMAD | `madrid-stock-exchange` | 291 | EUR | drop 17 `X…` Latibex lines; class dots (`GRF.P`) |
| 1 | Nasdaq Stockholm | Sweden | `.ST` | XSTO | `nasdaq-stockholm` | 746 | SEK | 255 class-dotted symbols; currency-suffixed second lines |
| 1 | Nasdaq Copenhagen | Denmark | `.CO` | XCSE | `copenhagen-stock-exchange` | 143 | DKK | class dots (`NOVO.B`, `MAERSK.A/B`); second lines (`NDA.DK`, `SAMPO.DKK`) |
| 1 | Nasdaq Helsinki | Finland | `.HE` | XHEL | `nasdaq-helsinki` | 198 | EUR | `NDA.FI` → `NDA-FI.HE`; Ericsson/others as second lines |
| 1 | Oslo Børs | Norway | `.OL` | XOSL | `oslo-bors` | 293 | NOK | Cyprus/Bermuda shipping companies (D2/D3); part of Euronext, **check the current official branding** |
| 1 | Euronext Lisbon | Portugal | `.LS` | XLIS | `euronext-lisbon` | 48 | EUR | none |
| 1 | Euronext Dublin | Ireland | `.IR` | XMSM | `euronext-dublin` | 25 | EUR | many Irish companies have their primary listing elsewhere (D1 handles this) |
| 1 | Wiener Börse | Austria | `.VI` | XWBO | `vienna-stock-exchange` | 1,125 | EUR | most lines are the "global market" (US stocks): left out by D2 after one fetch |
| 2 | London Stock Exchange | United Kingdom | `.L` | XLON | `london-stock-exchange` | 3,591 | GBP (quoted in GBp) | pence (EX-14); drop 2,948 digit-start lines; funds (D5); Jersey/Guernsey (D3) |
| 3 | Euronext Athens | Greece | `.AT` | XATH | `athens-stock-exchange` | 147 | EUR | thin data expected; renamed from Athens Exchange in April 2026 |
| 3 | Nasdaq Iceland | Iceland | `.IC` | XICE | `nasdaq-iceland` | 32 | ISK | class dots (`SFS.B`); confirm the ISK rate |
| 3 | Nasdaq Tallinn | Estonia | `.TL` | XTAL | `nasdaq-tallinn` | 29 | EUR | digits inside tickers (`TAL1T`) |
| 3 | Nasdaq Riga | Latvia | `.RG` | XRIS | `nasdaq-riga` | 12 | EUR | very small |
| 3 | Nasdaq Vilnius | Lithuania | `.VS` | XLIT | `nasdaq-vilnius` | 25 | EUR | none |
| 3 | Warsaw Stock Exchange | Poland | `.WA` | XWAR | `warsaw-stock-exchange` | 762 | PLN | foreign "GlobalConnect" lines left out by D2 (D6) |

Current exchanges, with their D10 names: Euronext Brussels · Belgium `.BR`, Euronext Amsterdam · Netherlands `.AS`, Euronext Paris · France `.PA`, Euronext Milan · Italy `.MI` (Admin says "Borsa Italiana" today), **Xetra** · Germany `.DE` (Yahoo's `.DE` prices are Xetra's; Admin says "Deutsche Börse" today), SIX Swiss Exchange · Switzerland `.SW`.

Yahoo checks on 16 Oct included: `INVE-B.ST` (SEK, Sweden), `NOVO-B.CO`, `MAERSK-B.CO` (DKK quote, USD reports, already converted by M2), `NDA-FI.HE`, `EQNR.OL` (NOK / USD), `GLEN.L` (GBp / USD, country Switzerland), `ELEVR.RG` (country Luxembourg), `AIR.MC` (Airbus, a third line). Thin example: `GRF-P.MC` came back with no fundamentals at all.

---

## 5. Indices

| Index | Market(s) | Members | Snapshot source (drafted by script, checked by hand) |
|---|---|---|---|
| Euro Stoxx 50 | Euro area | 50 | Wikipedia table (parses cleanly, Yahoo tickers) + STOXX factsheet |
| Stoxx Europe 50 | Europe incl. UK/CH/Nordics | 50 | STOXX factsheet (Wikipedia has no ticker table) |
| AEX | Amsterdam | 25 | Wikipedia (clean) |
| ATX | Vienna | 20 | Wiener Börse site (no Wikipedia table) |
| BEL 20 | Brussels | 20 | Euronext site (the Wikipedia table includes former members) |
| CAC 40 | Paris | 40 | Wikipedia (clean) |
| DAX | Frankfurt (+ Airbus on Paris) | 40 | Wikipedia (clean) |
| FTSE 100 | London | 100 | Wikipedia (plain tickers) |
| FTSE/Athex Large Cap | Athens | 25 | Athex site |
| FTSE MIB | Milan | 40 | Wikipedia (clean) |
| IBEX 35 | Madrid | 35 | Wikipedia (clean) |
| ISEQ 20 | Dublin | 20 | Wikipedia ("Euronext Dublin: A5G" format) |
| OBX | Oslo | 25 | Wikipedia ("OSE: EQNR" format) |
| OMX Baltic Benchmark | Tallinn, Riga, Vilnius | ~15–20 | Nasdaq Baltic site |
| OMX Copenhagen 25 | Copenhagen | 25 | Wikipedia ("MAERSK B" format) |
| OMX Helsinki 25 | Helsinki | 25 | Wikipedia (clean) |
| OMX Iceland 15 | Reykjavik | 15 | Wikipedia |
| OMX Stockholm 30 | Stockholm | 30 | Wikipedia (clean) |
| PSI | Lisbon | ~16–18 | Wikipedia (plain tickers) |
| SMI | Zurich | 20 | Wikipedia (plain tickers) |
| WIG20 | Warsaw | 20 | GPW site (no Wikipedia table) |

**Format.** The snapshot is `uvalu/index_members.json`, committed. Per index: `name`, `owner` (STOXX, Euronext, Deutsche Börse, FTSE Russell, Nasdaq, BME, Wiener Börse, GPW, Athex), `as_of`, `source_url`, and `members`, a list of `{ticker, name}` in Yahoo form. `tools/refresh_index_members.py` fetches what it can, normalises tickers (EX-11), prints a diff against the snapshot (added / removed / unmatched), and writes only after a `--write` flag. Index reviews take effect after the third Friday of March, June, September and December, so the refresh goes into `docs/open-items.md` as a recurring task. The script needs to be checked by hand for the indices with no clean source (Stoxx Europe 50, ATX, Athex, WIG20, OMX Baltic, BEL 20).

**Matching (EX-26).** A member ticker that isn't the universe's chosen line (for example a DAX member listed as `AIR.DE`) is matched through the same company identity as EX-5. A member that matches nothing is logged as `index.unmatched` and counted in the data-quality summary.

---

## 5b. Dividend withholding defaults per country

These are the **headline rates each country withholds at source on dividends paid to a non-resident individual**, before any treaty refund. They are the defaults in Settings (D13, EX-33), and every rate stays editable. **They come from my own knowledge (rates as of 2025–2026), not from an official source, and must be checked by the tax advisor (expert #04) before the release.** Rates change, so the table carries a "last checked" date.

| Country | Default | Note |
|---|---|---|
| Austria | 27.5% | |
| Belgium | (none) | For Belgian residents, the 30% roerende voorheffing is applied as a separate layer (`portfolio.BE_WITHHOLDING_RATE`). Shown as an explanation, not a field (D23), so it can't be counted twice. |
| Cyprus | 0% | |
| Denmark | 27% | |
| Estonia | 0% | |
| Finland | 35% | 35% on shares held through a nominee (the usual broker account); 30% when the owner is identified. |
| France | 12.8% | Rate for individuals. Brokers that don't apply it withhold 25% (the rate for companies), and the difference is reclaimed later. |
| Germany | 26.375% | 25% + solidarity surcharge. |
| Greece | 5% | |
| Guernsey | 0% | |
| Iceland | 22% | |
| Ireland | 25% | |
| Isle of Man | 0% | |
| Italy | 26% | |
| Jersey | 0% | |
| Latvia | 0% | |
| Liechtenstein | 12.5% | |
| Lithuania | 15% | |
| Luxembourg | 15% | |
| Netherlands | 15% | |
| Norway | 25% | |
| Poland | 19% | |
| Portugal | 28% | Rate for individuals (25% for companies). |
| Spain | 19% | |
| Sweden | 30% | |
| Switzerland | 35% | |
| United Kingdom | 0% | |
| Bermuda and other allow-listed countries (D2) | 0% | |

**What the rate means in the app:** the tax withheld at source, which is what a broker statement shows. It is not the final tax after a treaty refund (for example Switzerland 35% reclaimable down to 15%). The help text says so in one line.

**Existing users:** rates already entered per exchange are copied to their country by m0003 and take precedence over the defaults. For the founder's account this means France stays at 25% (the value entered for Paris), not the 12.8% default. The one-time notice (D23) lists the moved values, so they can be checked.

---

## 6. Load estimate

These estimates use the measured 0.38 tickers per second. *Corrected 16 Oct after the architecture review (A9): the first version missed the rows on the 3-hour thin-row retry.*

| | Rows fetched per day | Hours of fetching per day |
|---|---|---|
| Today | ~15,100 (3,067 normal + 992 thin × ~8 + ~4,100 dead) | ~11 |
| Today, after EX-19 and D29 (dead-row back-off, escalating short TTL) | ~5,000 | ~3.7 |
| After all 15 exchanges, steady state | ~8,000–9,000 (new primary lines ~3,000, their thin rows, secondary lines weekly; foreign lines stop after their first fetch) | ~6–6.5 |
| One-off first fetch of the new lists (after pre-filters) | ~4,500 (~3,700 without Warsaw) | ~3.3, spread behind existing work (EX-23) |

**With the back-off fixes, the daily Yahoo load after expansion is well below today's.** That is why EX-W1 comes before any new exchange. List scraping drops from about 50 page requests per rebuild to about 50 per day (EX-12, D26), and rebuilds from ~61 s to ~5–10 s.

The public universe roughly doubles. The cache file grows from 14 MB to about 20 MB. The cold-start parse is already guarded (`warm_lock`). The build's `compute_scores` cost grows in line with the number of rows; WP-7's partial vectorisation is enough for this size, and the build will be timed in EX-W8.

---

## 7. Work packages

Each package is one reviewable commit (or a few) on `feature/exchange-expansion`, with tests.

**Order after the reviews** (D15, D26, D31, D33, D36): EX-W0 (euro sign on Zurich prices) → EX-W1a (ticker-list cache + shrink guard) → EX-W1 (fetch hygiene + atomic write + escalating TTL) → EX-W2 (registry + single frame) → **EX-W5** (units at the source) → EX-W5b (rate per currency, EPV tax, liquidity in EUR) → EX-W3 (filters, mapping, share classes) → EX-W4 (stable primary listing) → shadow build for a week → EX-W6/W7/W8 per go/no-go → EX-W9 … EX-W12. EX-W0 to EX-W2 change no signals and can start before 21 October. The table below keeps the original numbering.

| # | Package | Requirements | Main files | Done when |
|---|---|---|---|---|
| EX-W1 | **Fetch hygiene**: dead-row back-off, shared rate-limit cool-down (both lanes + live price batch), 404 `next_fetch_at`, cache pruning | EX-19–23 | `screener.py` (`_Fetcher`, `_run_fetch`, `_is_fresh`), `uvalu/data.py` | Unit tests for each rule; a dev run shows the ~4,100 dead rows leave the daily queue and fetch-job logs show the drop |
| EX-W2 | **Exchange registry**: one `uvalu/exchanges.py` with an `Exchange` record per exchange (EX-3); every module reads from it; D10 rename (with migration of saved keys if needed) | EX-3, EX-30, EX-33 | new `uvalu/exchanges.py`; `settings.py`, `fetch_tickers.py`, `uvalu/data.py`, `uvalu/universe.py`, `portfolio.py`, `formatting.py`, pages `screener` / `watchlist` / `analysis` / `admin` / `settings`, `workbook.py`, `uvalu/store.py` | Still six exchanges; same screens, same universe; a test fails if a suffix or label is defined outside the registry |
| EX-W3 | **Ticker-list cache** with last-good fallback; per-exchange equity filters and generic exceptions files; symbol mapping (EX-11) | EX-9–12 | `fetch_tickers.py` | Rebuilds no longer scrape (log check); Frankfurt result identical to today |
| EX-W4 | **Primary-listing rule** replacing home-listing: company identity, D1 ordering, D2 allow-list, D3 country set, exclusion reasons | EX-4–8 | `uvalu/universe.py`, `uvalu/data.py`, `docs/data-contracts.md` | Airbus, Stellantis, STMicro, ArcelorMittal in the universe on one line each; US Frankfurt/Milan lines still out; per-reason counts logged |
| EX-W5 | **Units and currencies**: pence normalisation everywhere a price enters, `dividendRate` cross-check, new tax rates, FX test for the new currencies, currency next to the trade price field | EX-14–18 | `screener.py` (`_fetch_one`), `marketdata.py`, `uvalu/data.py` (live prices), `fx.py` tests, `uvalu/dialogs.py` | BT-A.L / ULVR.L / SHEL.L give fair values in GBP within a sane range; P/E matches Yahoo's |
| EX-W6 | **Batch 1 exchanges**: Madrid, Stockholm, Copenhagen, Helsinki, Oslo, Lisbon, Dublin, Vienna, plus migration m0003 (D9) | EX-1, EX-2, EX-10 | registry entries, `uvalu/migrations/m0003_…` | A full build with real data; per-exchange counts in, left out and why, reviewed with you before moving on |
| EX-W7 | **London** | EX-1, EX-10, D5 | registry entry, London filter | FTSE 100 members all present once; no investment trusts; spot-check 20 fair values |
| EX-W8 | **Batch 3**: Athens, Reykjavik, Tallinn, Riga, Vilnius, Warsaw; build timing | EX-1 | registry entries | Full build time and cache size measured and recorded |
| EX-W9 | **Index snapshot + refresh script** | EX-13, EX-26, D7, D8 | `uvalu/index_members.json`, `tools/refresh_index_members.py`, `fetch_tickers.py` fallbacks | Every member of every index matches a universe row, or is listed as unmatched with a reason |
| EX-W10 | **Index filter + drawer tags** | EX-24–28 | `uvalu/pages_/screener.py`, `uvalu/drawer.py`, `uvalu/styles.py` | Browser check at 1440 / 1024 px; filter bar wraps cleanly; Euro Stoxx 50 shows 50 rows |
| EX-W11 | **Signals and quality**: `universe_change` changed-input marker, data-quality thresholds re-checked | EX-35, EX-36 | `uvalu/data.py`, `uvalu/compliance/signal_history.py`, `uvalu/data_quality.py` | First build after the change logs `universe_change`; no false data-quality alert |
| EX-W11b | **Currency audit, one notation, converted second line, withholding per country**: every price field uses its own currency; codes instead of symbols everywhere (D14); the user's own currency underneath every foreign amount (D25); withholding table by country, dialog default by company country, m0003 copies the old values | EX-33, EX-39, EX-41, EX-42 | `uvalu/i18n.py`, `docs/uvalu-brand-guidelines.md`, `uvalu/components.py`, `uvalu/drawer.py`, all pages listed in EX-39, `uvalu/dialogs.py`, `settings.py`, `uvalu/pages_/settings.py`, `portfolio.py`, `workbook.py` | Zurich, London, Stockholm and Copenhagen rows show CHF / GBP / SEK / DKK everywhere a per-share figure appears, and totals stay EUR; the currency test passes; old withholding values arrive under the right country |
| EX-W12 | **Text, translations, docs, legal**: new strings in six languages, "six exchanges" wording, Data sources trademark line, L2 questions, open-items entries, release notes | EX-31, EX-32, EX-37, EX-38 | `locales/*`, help / methodology / data sources, `docs/*`, `docs/open-items.md`, `RELEASE_NOTES.md`, `CHANGELOG.md` | i18n review CSV approved by you |

**What changes in the UI.** One new control: the **Index** dropdown, right after **Market**. Changes to existing screens:

1. Market filter: 21 exchanges as "Official name · Country", multiple choice; today's city labels become official names everywhere (Exchange column, drawer, badge tooltip).
2. **Every amount written with a currency code** ("EUR 55.86", "DKK 24,270.00", "SEK 422.60"), no more "€" (D14); amounts get a little wider, in the fixed-width Screener and Watchlist columns. This is the most likely layout problem; check at 1440 and 1024 px together with the P1 fair-value label fix.
3. Venue badge codes for the 11 exchanges that have none yet in `formatting.EXCHANGE_CODES` (moved into the registry), so no row shows a raw suffix such as "CO" or "OL".
4. The filter bar wraps to a second line sooner at 1024 px.
5. Share-class tickers such as `INVE-B.ST` (D12).
6. Admin → Data feeds: 21 switches.
7. Settings: dividend withholding as one row per country (EX-33).
8. Trade dialog: the currency next to the price field (EX-17).
9. Sign-in stat and the Data sources / methodology / help text.
10. Optional: index tags in the drawer (EX-28). Drop them for a smaller change.

**Visual check** (run-uvalu skill, after EX-W10 and EX-W11b): Screener with Market = Stockholm, Index = OMX Stockholm 30; Market = London; Market = SIX Swiss Exchange (CHF prices); Index = Euro Stoxx 50 across markets; row widths at 1440 / 1024 px with DKK and ISK prices; drawer prices, fair value and tags for a SEK stock; Admin → Data feeds with 21 switches; Settings withholding by country; a dividend for Airbus defaulting to the Netherlands rate; Analysis and Watchlist Market labels; Portfolio with a GBP holding (per-share figures in GBP, totals in EUR).

---

## 8. Tests

- **Registry (EX-3):** every suffix in the app comes from the registry; every registry entry has a label in all six locales.
- **Symbol mapping (EX-11):** a table of real symbols per exchange → expected Yahoo ticker (`INVE.B` → `INVE-B.ST`, `NDA.FI` → `NDA-FI.HE`, `TAL1T` → `TAL1T.TL` …).
- **Equity filters (EX-9/10):** the Frankfurt cases unchanged; London digit-start dropped; Latibex dropped; Baltic digits kept.
- **Primary listing (EX-4–6):** fixtures for Airbus (PA/DE/MC, NL), Shell (AS/L, UK), Nordea (HE/ST/CO, FI), ArcelorMittal (AS/PA/MC, LU), a US company on DE/MI/VI, Volvo A/B (both kept), Shell with London disabled (→ Amsterdam), Hafnia on the allow-list.
- **Pence (EX-14/15):** a BT-A.L-shaped row → Price 2.097 GBP, P/E ≈ 19; a ULVR.L-shaped row with EUR reporting is converted once, not twice; dividend history divided by 100.
- **Back-off (EX-19–22):** the dead-row schedule; a shared cool-down stops all workers; 404 gets `next_fetch_at`; pruning keeps held tickers.
- **Ticker-list cache (EX-12):** a scrape failure returns the last good list; a fresh cache causes no HTTP call.
- **Index filter (EX-24–27):** options limited to indices present; AND with Market; a member on another exchange's ticker matches the chosen line; unmatched members logged.
- **Migration m0003 (D9, D13):** an old `shared.json` with six exchanges gets all 21, and an explicitly disabled exchange stays disabled; per-exchange withholding values move to their country.
- **Currency (EX-39):** a CHF, GBP and SEK row render their own currency in the Screener / Watchlist row, the drawer and the portfolio per-share columns; totals render in the display currency; no per-share figure is formatted with a hardcoded currency.
- **Converted line (EX-42):** a SEK row shows `≈ EUR …` under the price for a EUR user, and `≈ CHF …` for a user whose display currency is CHF; a EUR row shows no second line for a EUR user; no rate → no second line; Price sorts on the converted value (D16).
- **Withholding (D13):** Airbus (`AIR.PA`, Netherlands) defaults to the Netherlands rate (15%); a holding with unknown company country uses its exchange's country; a new user starts with the §5b defaults; a user's own rate survives a change to the defaults; "Reset to default" restores the §5b rate; Belgium has no field.
- **Existing suites:** full pytest in CI (`tests.yml`), plus `test_signal_qualifier`, `test_universe`, `test_reporting_currency` and `test_data_quality` updated for the new rules.

---

## 9. Timing and gates

- **Wait for Q1 (21 October).** The flicker measurement compares 14–21 October with the 4–13 October baseline. A universe change before then would spoil it. EX-W1 to EX-W3 change no signals and can start now. EX-W4 onwards should merge after 21 October.
- **Withholding defaults need a check** by the tax advisor (expert #04) before release (§5b). Add this to `docs/open-items.md` with the other expert items.
- **L2 still applies.** More exchanges don't change the rule (personal contacts only while prices come from Yahoo), but they make the EODHD question list longer (EX-37). Sending that list sooner helps.
- **Release.** One CalVer MINOR-style release for the whole set (signals change). RELEASE_NOTES.md: "Uvalu now covers 21 European exchanges, with an Index filter"; CHANGELOG.md: the full detail. If you'd rather ship batch 1 + index filter first and London later, EX-W7/EX-W8 can move to a second release without rework.
- **Rough size**, at the current side-project pace: EX-W1–W3 about one session each; EX-W4 and EX-W5 the largest (one to two sessions each); exchanges and index work one session per package; text and translations one session plus your review.

---

## 10. Further points (17 Oct)

Found in a last pass over the plan against the code. Each one is assigned to a work package.

| # | Point | Why it matters | Proposal | Package |
|---|---|---|---|---|
| P1 | **The founder-holdings disclosure matches by ticker** (`screener.py:2679`, REC-8) | If the founder holds a company through another line (for example `AIR.DE`), and the Screener shows `AIR.PA`, the conflict-of-interest notice is missing. **This is a legal gap, not cosmetic.** | Match `founder_holds` by company identity (EX-5), like "Hide positions I own" (D19). Add a test with a holding on a secondary line. | EX-W4 |
| P2 | **Watchlist stars and manual tickers on lines that become secondary** | A user who starred `NESN.DE` keeps a line the Screener no longer shows; it stays as an extra ticker, separate from `NESN.SW`. | Mark the star on the company, not the line. A one-time notice offers to move stars to the shown line, and nothing moves silently. | EX-W4 |
| P3 | **Adding a stock by hand or by import uses Yahoo tickers only** | Users know "NOVO B", "Novo Nordisk", or an ISIN from their broker statement, not `NOVO-B.CO`. With 21 exchanges this gets harder. | The add-ticker field and the workbook import accept the exchange's own symbol, and later an ISIN (with EODHD), and convert through the registry (EX-11, EX-40). | EX-W3 (symbol), EODHD (ISIN) |
| P4 | **Price freshness and exchange holidays** | The freshness indicator and the data-quality checks treat all markets alike. UK bank holidays, Nordic midsummer and Orthodox Easter in Athens would show as stale prices or raise alerts. | A tolerance of 3 business days per exchange before a price counts as stale, with no full holiday calendars (in line with `market_hours.py`'s simple approach). | EX-W6 |
| P5 | **Long company names** | Yahoo's long names for Polish, Greek and Nordic companies are long ("Powszechna Kasa Oszczednosci Bank Polski Spólka Akcyjna"), and rows cut them off. | Use Yahoo's `shortName` when `longName` is over about 40 characters. Add `HF`, `A/S`, `ASA`, `SPÓŁKA AKCYJNA` to the legal-form rules in `formatting.py`. | EX-W3 |
| P6 | **No currency exposure on the Risk page** | Portfolios with SEK, GBP and CHF become normal. VaR already includes FX (prices are restated in EUR), but users can't see their share per currency. | Not in this plan: add "Currency exposure" to the backlog. | backlog |
| P7 | **Factor model for Warsaw and Athens** | The Fama-French Developed factors fit the UK and the Nordics, but are a weaker fit for Poland (and Greece, a recent upgrade). | Keep them, and add one line on the methodology page. | EX-W12 |
| P8 | **Rolling back model M5** | Release 2 changes the model for today's six exchanges too (rate per currency, liquidity in EUR). If it misbehaves, switching exchanges off in Admin doesn't undo it. | Each M5 change goes behind a setting (default on). Switching them off returns to M4 behaviour without a code revert, and `MODEL_VERSION` follows the setting. | EX-W5b |
| P9 | **Dashboard benchmark** | The default is the Euro Stoxx 50. With UK, Swiss and Nordic holdings, a pan-European index (Stoxx Europe 600) is a fairer comparison. | Offer Stoxx Europe 600 as a benchmark and keep the current default; decide after the user study. | backlog |
| P10 | **Valuation audit fixtures** | `tools/valuation_audit.py` and its fixtures cover today's six exchanges only. | Add fixtures for a GBp, SEK, DKK (Maersk) and ISK row, so the audit covers the new unit and currency paths. | EX-W5 |
| P11 | **The withholding defaults are a new tax feature** | The tax review's rule TAX-7 says any new tax feature needs its own review first. The Dividends screen's rules text (`uvalu/compliance/disclosures.py`, `TAX_RULES`) says the rate is set "per exchange in Settings". | The §5b defaults use the existing `TAX_RULES_REVIEWED` date as their "last checked" date (one date, reviewed every January under L28), not a second one. `TAX_RULES` changes to "per country of the company". The tax advisor's check of §5b is the TAX-7 review. | EX-W11b |
| P12 | **Holdings are never converted to EUR** (found 17 Oct while building EX-W0) | `current_value = shares × live_price` with the price in the stock's own currency, in `portfolio_enrichment.py:32` (Risk), `uvalu/pages_/dashboard.py:93` (Dashboard totals) and `uvalu/drawer.py` (position value, P&L). A CHF holding is added to the EUR total as if CHF were EUR (about 5–7% off), and its P&L subtracts a EUR purchase value from a CHF value. With SEK, NOK, DKK or ISK the error is about 10–100×. The founder's portfolio holds only euro stocks today, so nothing is wrong yet. | Convert every position value to EUR (`fx.py`, the same ECB rates as everywhere else) at one shared place that the Dashboard, Portfolio, Risk and the drawer all use, and show the total in the display currency. **Blocks release 2.** | EX-W11b, moved before any non-euro exchange goes live |
