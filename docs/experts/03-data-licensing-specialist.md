# Expert Profile: Data-Licensing Specialist

**Project:** Uvalu — stock screening and portfolio tool for solo retail investors
**Priority:** Critical — the business cannot charge subscribers if data rights are missing

---

## Why Uvalu needs this expert

Uvalu's prices, fundamentals and derived scores currently come from **Yahoo Finance via yfinance**, whose terms allow personal, non-commercial use only (open item L2). The plan is to move to **EODHD** (EOD Historical Data) with a display licence. Analyst price targets are switched off until a licence covers them. Most market-data plans distinguish personal use from commercial redistribution, and the underlying exchanges often impose their own fees and rules for showing data to third parties. Showing that data — or values derived from it — to paying subscribers may require a different plan, an exchange licence, or display restrictions.

## Required expertise

- Market-data licensing: vendor terms, exchange policies, display vs. non-display use, derived data
- Experience negotiating with market-data vendors (EODHD, or comparable: Polygon, Financial Modeling Prep, Refinitiv/LSEG, ICE, Morningstar)
- Knowledge of **exchange redistribution policies** (e.g. Euronext, NYSE, Nasdaq, Deutsche Börse): professional vs. non-professional subscriber classifications, real-time vs. delayed vs. end-of-day
- Understanding of the **EU Database Directive** (sui generis database right) and copyright in data compilations
- Ideally a legal background (IP / commercial contracts) or many years in a fintech or exchange data-sales role

## Scope of review

1. **Yahoo Finance today:** confirm it can't be used for a paid or multi-user service, and what that means for the free beta
2. **Planned EODHD plan:** does it permit display to third parties at all, and to paying users specifically?
3. **What exactly is shown:** raw prices, raw fundamentals, charts, or only derived outputs (fair values, scores, signals)? Does "derived data" escape redistribution rules under the contract?
4. **Exchange-level obligations:** which exchanges are covered, whether end-of-day data still triggers exchange fees, user-classification and reporting duties
5. **Attribution and display requirements:** source labels, delays, logos
6. **Caching, storage and historical data:** may Uvalu store data indefinitely, use it for backtests, keep it after the contract ends?
7. **Exports:** may users download CSV/Excel containing vendor data?
8. **Cost scaling:** how licence cost grows with user count; break-even impact on pricing
9. **Alternatives / fallback vendors** if EODHD terms are unworkable

## Expected deliverables

- Written analysis of the EODHD terms against Uvalu's actual use
- List of permitted / restricted / forbidden features (display, export, API, backtest)
- Recommended plan or negotiation strategy with EODHD, including draft questions or a request for written confirmation
- Attribution text and display rules for the UI
- Cost model per user tier

## Material to prepare

- How yfinance is used today (`screener.DATA_SOURCE`, `marketdata.py`) and the data-sources page in `docs/legal/policies/`
- The EODHD plan under consideration and its current terms
- List of endpoints used and exchanges/tickers covered
- Screens and exports showing data, marked as raw vs. derived
- Expected subscriber numbers for years 1–3

## Questions to ask when selecting

- Have you negotiated a redistribution licence for a retail-facing app?
- How do you handle derived-data questions with vendors?
- Do you know EODHD's commercial plans specifically?

## Red flags

- Assumes "end-of-day data is free to show"
- Has only worked with institutional terminals, never with retail apps
- Cannot explain professional vs. non-professional user classifications

## Where to find

- Former data-sales / data-licensing staff from exchanges or vendors (freelance consultants)
- IP/commercial lawyers with a fintech data practice
- Fintech founder communities where vendor-licensing experiences are shared
