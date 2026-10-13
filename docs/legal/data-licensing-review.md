# Data-licensing review

13 Oct 2026 · First-pass review with the legal counsel persona ([`docs/experts/legal-counsel-persona.md`](../experts/legal-counsel-persona.md)), scoped by expert profile [03](../experts/03-data-licensing-specialist.md) and the questions in [briefing pack 03](../experts/briefings/03-data-licensing-brief.md). It does not replace a review by a licensing specialist, or the written confirmations from the vendors.

**Reviewed:**

- The data sources pages: beta 1.0 and paid 1.0 in [`policies/`](policies/).
- Decision B2 and the data items in [`compliance-implementation-plan.md`](compliance-implementation-plan.md).
- What the app shows today, on master (`21a1212`).

**Caveat.** Vendor terms change often, and none were attached. Statements about Yahoo, EODHD, STOXX and the French Data Library describe the usual position. Check each one against the current terms before relying on it.

## Conclusion

- **Beta on Yahoo Finance: medium.** This is a contract and claims risk, not a regulatory one. `yfinance` is not a product Yahoo licenses. It reads Yahoo's web endpoints, so Uvalu has no licence at all for this data, not even a personal one. Showing it to other people is outside anything Yahoo's terms allow. In practice the likely consequence for a small, free, closed group is being blocked or rate-limited, not a claim. The risk grows with every person who isn't a personal contact, and with any income.
- **Paid launch on EODHD: unclear until the vendor confirms in writing.** Market-data contracts decide everything here: display to third parties, values derived from the data, storage, exports, and whether exchange fees are included. A plan bought from the website is usually for personal use. Display to paying users is usually a separate commercial licence. Treat the current "EODHD, end-of-day, display licence" plan as a negotiation still to be done, not a purchase.
- **Smaller sources:**
  - ECB rates via Frankfurter: low risk.
  - French Data Library: low–medium, with no explicit licence.
  - EURO STOXX 50 index data: unclear. Index providers license the use of their data, not only its display.

Each point is marked as settled law, interpretation, or unclear.

## 1. What Uvalu does with vendor data

Facts checked in the code:

| Use | Raw or derived | Where |
|---|---|---|
| Latest price, P&L, margin of safety | Raw price shown; margin of safety derived | Every screen with positions or signals |
| **1-year price chart** against fair value | **Raw price history** | Analysis page, which calls `yf.Ticker(...).history(period="1y")` directly in `uvalu/pages_/analysis.py` |
| Selected ratios | Raw fundamentals | Analysis page, drawer |
| Dividends and splits | Raw; can be auto-imported into the user's own records | Dividends, Portfolio |
| Sector and industry | Raw, with a few corrections by Uvalu | Screener, Portfolio, risk concentration |
| EURO STOXX 50 history | Used only to compute beta; the index is not shown | Risk |
| Fair values, scores, signals, risk figures | Derived | Everywhere |
| 12-month signal history, with the price each signal used | Derived, plus one raw price per signal | `uvalu/compliance/signal_history.py` |
| Delayed price auto-refresh | Raw, intraday delayed | `uvalu/ui.py` `price_autorefresh` |
| User export (Excel) | The user's own records, including sector names and imported dividends | Settings › Export |

Already in place:

- analyst targets switched off (`ANALYST_INPUTS_ENABLED = False`)
- no bulk export of market data, scores or signals
- the source named on the Data sources page
- delayed prices labelled with their time

## 2. Yahoo Finance in the beta (L2, decision B2)

**Settled (contract).** Yahoo's terms allow personal, non-commercial use of what its services show. `yfinance` describes itself as unaffiliated with Yahoo and points users to Yahoo's terms. Nothing in those terms permits showing the data to other people. Part of that data is exchange data that Yahoo itself licenses under display terms.

**Interpretation.** B2's mitigations are sound, and they matter: free access, a closed group of people you know, the source named, no bulk export. They lower the chance of a dispute and the damages if one arises. They don't make the use licensed.

**Recommendation.** Tie the switch to the same trigger as L1: **no one you don't know personally joins while prices come from Yahoo.** If the beta needs to grow before M2, bring only C7 (the EODHD provider) forward, without the daily build. The compliance plan already names that option.

## 3. EODHD for the paid launch

**Settled (contract over database law).** The EU Database Directive gives the database maker rights against extracting or re-using a substantial part of its database. Where a database falls outside the Directive, the contract can restrict use freely (CJEU C-30/14, *Ryanair v PR Aviation*). Either way, **the licence agreement is the deciding text.** Whether fair values and signals count as free "derived data" depends on its wording, not on a general principle.

**Interpretation.** Values computed from many inputs that can't be reverse-engineered into the source data (fair values, scores, signals, VaR) are usually allowed under a display licence, often with attribution. Showing raw prices, a price chart, ratios and dividends is "display" and needs the licence to cover third parties. Keeping data after the contract ends is restricted unless agreed. The compliance plan notes that retention after the contract ends was "already confirmed". Get that in the signed contract, not only in an email.

**Unclear.** Whether EODHD's commercial licence includes the exchange fees for end-of-day display to non-professional users, or whether Uvalu must register with or report to Euronext, Deutsche Börse, Borsa Italiana or SIX. Exchange policies differ, and some charge for end-of-day data too. This goes on the vendor question list (Appendix), and the answer must be in writing.

**The MAR link.** The signal label review concluded that Uvalu probably has to keep a 12-month history of each signal, including the price it used. That history contains vendor data. The contract has to allow keeping it for at least 12 months, including after a change of vendor. Otherwise a vendor change could put Uvalu in breach of MAR.

## 4. Smaller sources

- **ECB reference rates via Frankfurter. Settled, low.** The ECB allows reuse of its statistics with the source acknowledged, and the Data sources page does that. Frankfurter is a free service that relays ECB data. Keep a fallback in case it disappears.
- **Kenneth R. French Data Library. Interpretation, low–medium.** The data is published freely and widely used, but no licence is stated for commercial services. Uvalu shows only derived factor exposures. A short email asking permission for use in a paid service is cheap. Keep the reply with the contracts (DATA-6).
- **EURO STOXX 50. Unclear, medium at paid launch.** STOXX licenses index data, often including uses that don't display it, such as calculations. Two options:
  - Ask STOXX or the vendor whether computing beta against the index is covered.
  - Measure beta against a broad ETF's end-of-day price, which the price licence already covers. The methodology page would then need a small update.

## 5. Recommended changes, in order of value

1. **Trigger for the beta (L2):** no one beyond personal contacts while prices come from Yahoo. Record this next to L1.
2. **Send the EODHD question list (Appendix) and get written answers** before choosing a plan. Get the confirmed points into the contract: display, derived data, retention including the 12-month signal history, exports, attribution and exchange fees.
3. **Keep raw display small.** Show raw prices, ratios and dividends only where the user needs them. Treat the 1-year price chart as a separate item to confirm. It also calls Yahoo directly, so add it to the C7 switch-over: no screen should fetch from the vendor outside the provider module (S3).
4. **Decide the benchmark:** confirm the STOXX position or switch to an ETF benchmark.
5. **Email Kenneth French's team** for permission for a paid service.
6. **Remove the intraday auto-refresh at M2 (C8),** as planned. An end-of-day licence doesn't cover intraday quotes.
7. **Fill in the attribution text** from the signed contract (`[TBD]` in Data sources §2), and keep the paid page unpublished until then. Its header comment already says so.

## Facts the review still needs

- The EODHD plan under consideration, with its current terms saved as a PDF with the date.
- Where "retention after the contract ends" was confirmed, and in what words.
- Expected subscribers for years 1–3, for the licence quote.
- Whether the 1-year price chart is essential, or a nice-to-have that could go if licensing it costs extra.

## Appendix: questions for EODHD, in writing

1. Which plan allows displaying end-of-day prices, fundamentals, dividends and splits to **paying non-professional subscribers** in the EEA, inside a web app, about 1,500 shares on Euronext (BR, AMS, PAR), Borsa Italiana, Xetra and SIX?
2. Are **derived values** (fair values, scores, model signals, risk figures) free to display without restriction? Is attribution required for them?
3. May we show **price charts** of 1 year of daily closes?
4. Are **exchange fees** for that display included? Must we report users, or sign anything with the exchanges?
5. May we **store** data and keep it **after the contract ends**, at least a 12-month history of signals with the price each used?
6. May users **export** their own portfolio records that contain sector names, dividend amounts and prices?
7. Is **EURO STOXX 50** index data covered for computing beta, without displaying the index?
8. What **attribution** text, placement and logo rules apply?
9. How does the **price** scale with the number of subscribers? Is there a fixed fee up to a given number?
10. What **notice** applies if EODHD changes the terms or ends the licence?
