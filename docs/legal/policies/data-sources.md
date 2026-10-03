<!--
Uvalu public legal page. Status: FINAL TEXT, pending counsel review and the [TBD] items listed in README.md.
DO NOT PUBLISH until the EODHD contract allowing commercial display and derived data is signed (DATA-1, DATA-2).
Copy EODHD's required attribution wording exactly from the contract into section 2 (DATA-4).
Open for counsel / contract: EURO STOXX 50 index data may need a STOXX licence; Fama-French Data Library
terms for display in a paid service (DATA-6).
Other requirement IDs: REC-3, REC-4, DATA-3, DATA-5, DATA-6.
-->

# Data sources

**Version:** 1.0 · **Last updated:** 1 January 2027

Uvalu's calculations depend on data from third parties. This page lists where the data comes from, how fresh it is, and what to keep in mind.

## 1. Sources

| Data | Provider | Freshness | Coverage |
| --- | --- | --- | --- |
| Share prices | EOD Historical Data (EODHD) | End-of-day closing prices, updated once per trading day | Euronext Brussels, Euronext Amsterdam, Euronext Paris, Borsa Italiana, Deutsche Börse, SIX Swiss Exchange |
| Company financial statements | EODHD | Uvalu checks for updates about every 24 hours; new filings appear once the provider has processed them | Same exchanges |
| Dividends and corporate actions (splits, etc.) | EODHD | Dividend history refreshed weekly | Same exchanges |
| Benchmark index (EURO STOXX 50), used for beta | EODHD | End-of-day | Euro area |
| Sector and industry classification | EODHD | With the company data | All covered shares |
| Currency rates | European Central Bank reference rates, retrieved through Frankfurter (frankfurter.dev) | Daily, on ECB working days | All currencies of the covered exchanges, converted to EUR |
| Factor data for risk analysis | Kenneth R. French Data Library (Tuck School of Business, Dartmouth): Developed markets five factors plus momentum, with the US factors as a fallback | Daily series, refreshed at most weekly | Developed markets |

The risk-free interest rate (3%) and the equity risk premium (5%) are fixed model assumptions, not data feeds. They are described on the Methodology page.

Uvalu does not use analyst price targets or analyst recommendations.

Uvalu does not show real-time or intraday prices. Every price shows the date it refers to.

## 2. Attribution

- [TBD: EODHD ATTRIBUTION TEXT, exactly as required by the licence.]
- Currency rates: source European Central Bank.
- Factor data: Kenneth R. French Data Library (Tuck School of Business, Dartmouth).

## 3. Data quality

- Data may be **delayed, incomplete or incorrect**. Providers and Uvalu give no guarantee of accuracy.
- Reported figures can be **restated** by companies after publication.
- Where an input is **missing**, the models that depend on it are skipped, and the stock page shows which models were used and why others were not.
- A price that is **more than 72 hours old** is flagged next to the signal.
- Figures in foreign currencies are converted using the rates listed above; conversion can cause small differences from other sources.
- Before you act on a figure, check it against the company's own reports or your broker.

Found an error? Tell us at support@uvalu.app with the ticker and the figure concerned.

## 4. What Uvalu calculates itself

Fair values, margins of safety, composite scores, model signals and risk figures are calculated by Uvalu from the data above. They are Uvalu's own model outputs, not data from the providers, and the providers are not responsible for them. See the Methodology page.

## 5. Your own data

Portfolio holdings and transactions are entered by you. Uvalu does not connect to your broker or bank and cannot check your entries.

## 6. Permitted use

Data shown in Uvalu is licensed for your personal use inside the app. You may export your own portfolio. You may not copy, scrape, redistribute or resell market data, fundamentals, scores or signals. See the Terms of use, section 8.

## 7. Trade marks

Company names and ticker symbols are used only to identify the shares concerned. All trade marks belong to their owners. Uvalu is not affiliated with, sponsored by or endorsed by any company or exchange shown.
