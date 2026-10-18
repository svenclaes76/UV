<!--
Uvalu public legal page — FREE BETA version (decision B4, docs/legal/compliance-implementation-plan.md §0).
Derived from ../data-sources.md (the paid-launch version, EODHD). During the free beta the data comes from
Yahoo Finance via yfinance, which is not licensed for a commercial service (decision B2: free, invite-only,
with mitigations). Open: Fama-French Data Library terms for display to third parties (DATA-6).
Other requirement IDs: REC-3, REC-4, DATA-3, DATA-5, DATA-6.
Beta-readiness review 5 October 2026: "used for beta" (ambiguous next to "free beta") reworded; no-affiliation
statement extended to data providers. Freshness figures checked against the code (CACHE_TTL_HOURS 24 ± 4,
dividends weekly, PRICE_STALE_HOURS 72).
-->

# Data sources — free beta

**Version:** beta 1.0 · **Last updated:** 5 October 2026

Uvalu's calculations depend on data from third parties. This page lists where the data comes from, how fresh it is, and what to keep in mind.

## 1. Sources

| Data | Provider | Freshness | Coverage |
| --- | --- | --- | --- |
| Share prices | Yahoo Finance (via the yfinance library) | Delayed quotes, not real-time; the time each price was fetched is shown next to the signal that used it | Euronext Brussels, Euronext Amsterdam, Euronext Paris, Borsa Italiana, Deutsche Börse, SIX Swiss Exchange |
| Company financial statements | Yahoo Finance | Uvalu checks for updates about every 24 hours | Same exchanges |
| Dividends and corporate actions (splits, etc.) | Yahoo Finance | Dividend history refreshed weekly | Same exchanges |
| Benchmark index (EURO STOXX 50), used to measure market sensitivity (beta) | Yahoo Finance | Daily | Euro area |
| Sector and industry classification | Yahoo Finance, with a few corrections by Uvalu where the source has none | With the company data | All covered shares |
| Currency rates | European Central Bank reference rates, retrieved through Frankfurter (frankfurter.dev) | Daily, on ECB working days | All currencies of the covered exchanges, converted to EUR |
| Factor data for risk analysis | Kenneth R. French Data Library (Tuck School of Business, Dartmouth): Developed markets five factors plus momentum, with the US factors as a fallback | Daily series, refreshed at most weekly | Developed markets |

The risk-free interest rate (3%) and the equity risk premium (5%) are fixed model assumptions, not data feeds. They are described on the Methodology page.

Uvalu does not use analyst price targets or analyst recommendations.

Uvalu does not offer real-time prices. During the beta, prices are delayed quotes; every model signal is shown with the time of the price it used. Before a paid launch Uvalu will move to a licensed data provider with end-of-day prices, and this page will change.

## 2. Attribution

- Market and company data: Yahoo Finance.
- Currency rates: source European Central Bank.
- Factor data: Kenneth R. French Data Library (Tuck School of Business, Dartmouth).

## 3. Data quality

- Data may be **delayed, incomplete or incorrect**. Providers and Uvalu give no guarantee of accuracy.
- Reported figures can be **restated** by companies after publication.
- Where an input is **missing**, the models that depend on it are skipped, and the stock page shows which models were used and why others were not.
- A price that is **more than 72 hours old** is flagged next to the signal.
- Figures in foreign currencies are converted using the rates listed above; conversion can cause small differences from other sources.
- Before you act on a figure, check it against the company's own reports or your broker.

Found an error? Tell us at uvalu.app@gmail.com with the ticker and the figure concerned.

## 4. What Uvalu calculates itself

Fair values, margins of safety, composite scores, model signals and risk figures are calculated by Uvalu from the data above. They are Uvalu's own model outputs, not data from the providers, and the providers are not responsible for them. See the Methodology page.

## 5. Your own data

Portfolio holdings and transactions are entered by you. Uvalu does not connect to your broker or bank and cannot check your entries.

## 6. Permitted use

Data shown in Uvalu is for your personal use inside the app during the beta. You may export your own portfolio. You may not copy, scrape, redistribute or resell market data, fundamentals, scores or signals. See the Terms of use, section 6.

## 7. Trade marks

Company names and ticker symbols are used only to identify the shares concerned. All trade marks belong to their owners. Uvalu is not affiliated with, sponsored by or endorsed by any company or exchange shown, or by the data providers listed above.
