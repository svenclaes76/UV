<!--
Uvalu public legal page — DEMO version (demo-mode plan DM-5). Shown instead of the beta page when
UVALU_DATA_MODE=demo. Draft 18 October 2026 for the DM-7 legal-persona review (DM-D21).
Facts checked against the code: tools/demo_refresh.py (weekdays 21:00 UTC, dividends weekly),
uvalu/demo/rows.py (beta on one year of daily returns against EURO STOXX 50),
demo-data/reference/sector_multiples.json (Damodaran, as of 5 January 2026, clipped to the engine's bands).
Open: EODHD's written answer on showing free-plan data in a demo (DM-D2, L20); STOXX licence for the
benchmark index (L21); Damodaran's terms for commercial use (noted in the reference file).
-->

# Data sources — demo

**Version:** demo 1.0 · **Last updated:** 18 October 2026

The demo shows 9 European stocks and one ETF from a fixed snapshot. Nothing is fetched while you use it: the snapshot is refreshed by a scheduled job.

## 1. Sources

| Data | Provider | Freshness |
| --- | --- | --- |
| End-of-day share prices and the EURO STOXX 50 benchmark | EODHD (eodhd.com) | Refreshed each weekday evening; the date of the newest close is shown in the demo notice. No intraday prices |
| Dividends | EODHD | Refreshed weekly |
| Company financial statements | The companies' own annual reports and results releases, entered by hand by Uvalu, each figure with its source document and page | Fiscal years 2023–2025; updated once a year after the annual reports |
| Sector valuation multiples (P/E, P/B) | Aswath Damodaran, NYU Stern, European industry averages | As of January 2026 |
| Currency rates | European Central Bank reference rates, retrieved through Frankfurter (frankfurter.dev) | Daily, on ECB working days |

Market sensitivity (beta) is measured on one year of daily prices against the EURO STOXX 50. Factor analysis, which needs the Kenneth R. French Data Library and longer price history, is not part of the demo.

The risk-free interest rate and the equity risk premium are fixed model assumptions, described on the Methodology page. Uvalu does not use analyst price targets or recommendations.

## 2. Attribution

- End-of-day prices and dividends: EODHD.
- Company figures: the companies' published reports.
- Industry multiples: Aswath Damodaran, NYU Stern (damodaran.com).
- Currency rates: source European Central Bank.

## 3. Data quality

- Data may be **incomplete or incorrect**, and companies can restate reported figures. The demo's figures were entered by hand and checked against the reports, but errors are possible.
- The fundamentals are annual figures, so between annual reports they are up to a year old.
- Where an input is missing, the models that depend on it are skipped; the stock page shows which models were used.

Found an error? Tell us at uvalu.app@gmail.com with the ticker and the figure concerned.

## 4. What Uvalu calculates itself

Fair values, margins of safety, composite scores, model signals and risk figures are Uvalu's own model outputs, calculated from the data above. The providers are not responsible for them. See the Methodology page.

## 5. Permitted use

The demo is for trying Uvalu. You may not copy, scrape, redistribute or resell its data, scores or signals.

## 6. Trade marks

Company names and ticker symbols are used only to identify the shares concerned. All trade marks belong to their owners. Uvalu is not affiliated with, sponsored by or endorsed by any company or exchange shown, or by the providers listed above.
