# Briefing: market-data licensing for Uvalu

*Prepared 13 Oct 2026 by Sven Claes, founder of Uvalu (uvalu.app). For a market-data licensing specialist or an IP/commercial lawyer with a fintech data practice.*

## What we ask

An analysis of whether we may show market data, and values derived from it, to other users. That covers the free beta today and paying subscribers later. We also want advice on which licence to buy and what to ask the vendor in writing. Please quote a **fixed fee** for the questions in §4 before starting.

## 1. Uvalu in brief

- An online tool for **private investors** (non-professional users only) in the EEA. It values listed shares and lets users record and analyse their own portfolio. There is no trading, no broker link and no public API.
- **Operator:** Sven Claes, Belgium, trading as Uvalu. Not yet registered with KBO/BCE.
- **Status today:** a **free, invitation-only beta** for people the founder knows. **Planned:** a paid monthly subscription. Expected subscribers: [Sven: year 1 / year 2 / year 3].

## 2. Data used today and what is shown

| Data | Source today | Used for | Shown to users |
|---|---|---|---|
| Share prices (daily history and latest delayed quote) | Yahoo Finance via the unofficial `yfinance` library | Margin of safety, returns, risk | Yes: the latest price, P&L, price charts in the stock and risk pages |
| Financial statements and key ratios | Yahoo Finance | Fair-value models, scores | Partly: selected ratios on the stock page |
| Dividends and splits | Yahoo Finance | Dividend models; dividends can be auto-imported into the user's own records | Yes |
| Sector and industry | Yahoo Finance, with a few corrections | Peer groups | Yes |
| EURO STOXX 50 index history | Yahoo Finance | Market beta in risk figures | Only as a derived beta |
| Currency rates | ECB reference rates via Frankfurter | Conversion to EUR | Indirectly |
| Factor returns | Kenneth R. French Data Library | Factor exposure in risk figures | Only derived exposures |

**Coverage:** about 1,500 shares on Euronext Brussels, Amsterdam and Paris, Borsa Italiana, Deutsche Börse and SIX Swiss Exchange.

**Derived outputs** shown to every user are fair values, margins of safety, composite scores, model signals and risk figures. Uvalu keeps a **12-month history of signals** and their inputs. Market-abuse rules (MAR) may require that history, so it has to survive a change of vendor.

**Exports:** users can download their own portfolio as Excel. That includes sector names, and dividend entries that may have been auto-imported. There is no bulk export of market data, scores or signals.

**Not used:** analyst price targets and recommendations (switched off until licensed), real-time data, and intraday data. A price auto-refresh exists today and will be removed for end-of-day data.

**Attribution today:** the Data sources page names Yahoo Finance, the ECB and the French Data Library.

## 3. Plan

Move to **EODHD**, end-of-day prices plus fundamentals, with a licence that allows display to subscribers, **before the paid launch** (open item L2). No contract is signed yet. Plan under consideration: [Sven: plan name, price, link to terms].

## 4. Questions

1. **Yahoo Finance in the beta.** How serious is the breach of Yahoo's personal-use terms in a free, invite-only beta of people the founder knows? Should we move to a licensed source before the beta grows, or before it opens at all?
2. **EODHD.** Does the plan under consideration allow display to third parties, and to paying users? If not, which plan or add-on does, and what should we get confirmed in writing?
3. **Derived data.** Under the vendor contract and the EU Database Directive, are fair values, scores, signals and risk figures "derived data" free of redistribution limits? Under what conditions?
4. **Exchanges.** Does showing end-of-day prices from Euronext, Deutsche Börse, Borsa Italiana and SIX to non-professional subscribers trigger exchange licences, fees or user reporting? Is that through the vendor or directly?
5. **Index data.** Do we need a STOXX licence to use EURO STOXX 50 history only for computing beta, without showing the index itself?
6. **Free sources.** May a paid service use and show results from the Kenneth R. French Data Library? And ECB rates via Frankfurter?
7. **Storage and history.** May we keep stored prices, fundamentals and the 12-month signal history after the contract ends, or after a change of vendor? May we use them for internal backtests?
8. **User exports.** May users export their own records that include sector names, dividend amounts or prices?
9. **Attribution and display.** What attribution text, delay labels or logos must we show?
10. **Cost.** How does the licence cost scale with the number of subscribers? Which alternative vendors should we compare if EODHD's terms don't fit?

## 5. What we'd like back

- A written analysis of the current and planned set-up against the terms.
- A table of **permitted / restricted / forbidden** uses: display, charts, exports, history, backtests, derived outputs.
- A recommended EODHD plan, or an alternative, plus a list of questions to put to the vendor in writing.
- The attribution and display rules for the Data sources page and the UI.
- A rough cost model for years 1–3.

**Not in scope:** financial regulation, privacy, consumer law and tax. Those are covered by separate briefs.

## Attachments

Export to PDF with version and date.

1. Data sources page: beta 1.0 and paid ([`policies/beta/data-sources.md`](../../legal/policies/beta/data-sources.md), [`policies/data-sources.md`](../../legal/policies/data-sources.md))
2. Terms of use, the acceptable-use section (paid §8, beta §6)
3. The EODHD plan page and terms under consideration ([Sven]: save as PDF with the date)
4. Screenshots: stock page (price, ratios, chart, signal), Screener, Portfolio, Risk, Excel export
5. Ticker list per exchange (from the screener universe)
