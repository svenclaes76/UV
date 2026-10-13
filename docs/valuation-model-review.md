# Valuation model review

13 Oct 2026 · First-pass review in the role of expert profile [05](experts/05-valuation-expert.md): an equity analyst / CFA reviewing a rules-based valuation tool. There is no separate persona file for this role. The review follows the profile's scope and its "how you advise" style: conclusion first, then the evidence. It does not replace the review by a real valuation expert, especially the sample check against professional estimates (scope item 7).

**Reviewed:**

- [`stock_valuation_algorithm.md`](stock_valuation_algorithm.md) and the constants in `screener.py` (model `M1`).
- The public universe's daily signal snapshot of **13 Oct 2026**: 3,562 stocks (`data/compliance/signal_snapshots/2026-10-13.jsonl.gz`).
- The fundamentals cache it was built from (`.cache/fundamentals.json`).

All figures below come from that snapshot.

## Conclusion

The design is careful. Specific strengths:

- the model set matches the sectors (Graham, P/E and EPV skipped for banks and REITs)
- the dividend models' growth is clamped below the discount rate
- EPV uses a robust multi-year EBIT
- vetoes are named, and signals are reproducible

An expert would put their name to the *structure*. The problems are in the **inputs and the universe**, and two of them are serious enough to fix before more people rely on the signals:

1. **High: currency mismatch on cross-listings.** For about 40% of the universe, the quote currency differs from the currency the fundamentals are reported in. The fair value is then in one currency and the price in another (§1).
2. **High: the universe isn't the "European" universe the product describes.** About 1,000 rows are secondary listings of US companies on Milan and Frankfurt, many of them dormant. They distort the medians, the ranks and the published signal distribution (§2).
3. **Medium–high: trailing EPS drives the most generous model.** P/E fair value is the highest model for 54% of stocks. A one-off gain inflates it twice (§3).
4. **Medium: model disagreement is averaged away.** The median stock's highest and lowest model differ by 3.3×, and 328 stocks by more than 10×. The composite still shows one number (§4).

The other points are calibration and wording (§5–§7).

## 1. Currency mismatch on cross-listings (high)

**Evidence.** Yahoo reports per-share fundamentals (EPS, book value, dividends) in the company's **reporting** currency, but the price in the listing's **quote** currency. The snapshot doesn't store the reporting currency, so a heuristic stands in for it: quote currency EUR with a non-euro-area country, or CHF with a non-Swiss country. By that measure **1,440 of 3,562 rows** (40%) are affected.

- **Investor AB, `1INVEB.MI`:** price €36.24, book value per share **293.6**, which is the Swedish krona figure. Yahoo's own P/B comes out at 0.12. Uvalu's book-value fair value is €465 and its composite €261, so the margin of safety is 86%: **Undervalued, score 91.**
- **Apple, `APC.DE`:** price €304, EPS 7.43, which is in dollars. The trailing P/E of 40.9 that feeds the sector median mixes euros and dollars.
- **28 of the 128 "Undervalued" signals** are rows like these.

**Why it matters.**

- The error equals the exchange rate: about 15% for USD, but about 11× for SEK, 7.5× for DKK and 160× for JPY.
- It also leaks into **every other stock**. The mismatched P/E and P/B values enter the sector medians that set the P/E and book-value fair values, and the percentile ranks behind every score.
- `PTB_SANITY_FLOOR` (0.02) catches only the most extreme cases, like the Swiss National Bank.
- Under the market abuse rules (MAR), a fair value that is wrong by a factor of 8 is a presentation problem, not only a quality problem.

**Fix.**

- Store the provider's reporting currency per ticker (yfinance exposes `financialCurrency`; EODHD gives it with the fundamentals).
- Convert per-share fundamentals to the quote currency with the ECB rates Uvalu already uses (`fx.py`).
- Until that is done, give these rows a data flag such as `currency_unverified`, and keep them out of the medians and out of Undervalued.

## 2. Universe composition (high)

**Evidence.**

| | |
|---|---|
| Rows with country = United States | 580 on `.MI`, 423 on `.DE` |
| Milan tickers starting with "1" (the international cross-listing segment) | 908 of 1,263 |
| "Screened out" signals | 1,542, which is **43%** of the universe |
| "No trading volume" vetoes | 257, of which 179 are cross-listings |

**Why it matters.**

- The product, the Data sources page and the methodology describe a European screener of six exchanges. In practice about a third of it is second lines of non-European companies, many of which don't trade.
- These rows move everyone's scores, because the peer universe is the whole public universe.
- They inflate the share of "Screened out" in the signal distribution that the methodology page publishes (and that MAR's art. 4 may require).
- A dormant line that is vetoed for zero volume is not a quality judgement on the company. It is a listing that shouldn't be covered.

**Fix.** Cover one line per company, its primary or most liquid listing. Drop dormant lines from the coverage list (`fetch_tickers.py`) instead of vetoing them. Decide explicitly whether non-European companies belong in a European product. If they do, list them on the methodology page. This also shrinks what the data licence (#3) has to cover.

## 3. P/E fair value and one-off earnings (medium–high)

**Evidence.**

- P/E fair value = trailing EPS × the sector-median P/E (capped at 30×) × a PEG tilt (up to 1.5×), so up to **45× trailing EPS**.
- It is the highest of the models for **1,559 of 2,884** stocks that have at least two models.
- Trailing EPS is not normalised, unlike EBIT in EPV. A one-off gain raises EPS, *and* raises `earningsGrowth`, which raises the tilt. The gain counts twice.
- **11 "Undervalued" stocks have a trailing P/E below 5.** Two examples:
  - WE.CONNECT, `ALWEC.PA`: P/E 1.8. The P/E model gives 572 against Graham's 97 and EPV's 52, so the composite comes out at 213 against a price of 22.70.
  - Newprinces, `NWL.MI`: P/E 2.8, after a large disposal.

**Fix**, in order of effect:

1. Base P/E fair value and Graham on **normalised EPS**: the median or trimmed mean of `netIncomeHistory` per share, the same rule as EPV's EBIT.
2. Take the growth tilt from multi-year history, not the trailing `earningsGrowth`, or leave it out when trailing growth exceeds about 50%.
3. Flag a trailing P/E under 4 as `eps_one_off_suspect`, and keep the row out of Undervalued.

## 4. Model disagreement (medium)

**Evidence.**

- The ratio between the highest and lowest model has a median of **3.3×** (p90 11×), and is above 10× for 328 stocks.
- Only 52 rows carry `fair_value_clamped`.
- 23 of the 128 Undervalued stocks show a margin of safety **above 50%**. On a liquid European stock, a professional's first explanation for that is a data error, not a bargain.

**Why it matters.** A weighted average of values 10× apart is not an estimate of anything. Showing it to two decimals overstates the precision, which conflicts with the methodology page's own sensitivity note.

**Fix.**

- Compute a dispersion figure per stock, for example max/min or the coefficient of variation of the model values.
- Above a threshold (about 3×), treat the fair value like `fv_basis_thin`: show it as a range, not a point, and keep the stock out of Undervalued. This is the "Consensus" idea from the brand work: say where the models agree.
- Add a plausibility flag for a margin of safety above 50%.

## 5. Calibration (medium)

- **Level.** Across the universe, the median margin of safety is **−33%**: the models put the typical stock a third *below* its price. That is the expected result of Graham-style models (the Graham Number assumes P/E 15 × P/B 1.5, EPV assumes no growth), and it is a defensible value-investing stance. But it should be said plainly on the methodology page. Otherwise "Low score" and the negative margins read as a market call. It also means the P/E model, the most generous one, decides most Undervalued signals (§3).
- **Discount rate.** 3% risk-free plus a Blume-adjusted beta × 5% is reasonable for euro-area equities. Swiss and Nordic stocks are discounted at the euro rate. That's minor, but worth a sentence on the methodology page.
- **Vetoes.** 43% screened out is blunt. Most of it is the universe (§2), but two rules deserve a second look once currency is fixed:
  - **"Revenue decline", 619 rows:** three straight years of decline in *reported currency*, which picks up exchange-rate effects and cyclical troughs. Consider requiring a minimum cumulative decline, such as 10%.
  - **"Retained-earnings erosion", 330 rows:** it fires on companies that pay large special dividends. Check a sample.
- **Thin basis.** 529 stocks (15%) rest on one model, and 156 have none. That handling (no Undervalued, flag shown) is right.

## 6. What is right and should stay

- Skipping Graham, P/E and EPV for banks, insurers and REITs, and valuing them on P/B, DDM and (for banks) P/E.
- Clamping the dividend models (g ≤ WACC − 3 pp), and the continuous payout ramp instead of a cliff.
- EPV on a median or trimmed mean of multi-year EBIT, and subtracting net debt directly.
- Blume-adjusted beta, the 10% minimum margin of safety, and keeping thin-basis fair values out of Undervalued.
- Named veto rules, the `signal_reason` texts, model versioning, and the snapshots that made this review possible.

## 7. Documentation

- [`stock_valuation_algorithm.md`](stock_valuation_algorithm.md) Stage 3 said the `min_mos` default was 0% and recommended raising it. The code default has been 10%, with a 10% floor, since decision D1. Fixed in this commit.
- After §1–§4, bump `MODEL_VERSION` (M1 → M2) and add a methodology change-log row. These changes move signals, so the founder's trading blackout applies (Conflicts §4).

## Recommended changes, in order of value

1. **Currency:** store the reporting currency and convert per-share fundamentals. Until then, flag the affected rows and keep them out of medians and out of Undervalued (V1).
2. **Universe:** one line per company, no dormant lines, and an explicit decision on non-European companies (V2).
3. **Normalised EPS** for P/E and Graham; growth tilt from history; one-off flag (V3).
4. **Dispersion:** a range plus "no Undervalued" above about 3× disagreement; plausibility flag above 50% margin of safety (V4).
5. **Veto calibration** after 1–2: revenue decline threshold, retained-earnings rule checked on a sample (V5).
6. **Methodology page:** the conservative level, the euro rate for non-euro stocks, the universe definition (V6).

## For the real expert

Give them this review plus a **sample of 25–30 tickers** to check against professional estimates. Include:

- Large euro-area stocks: ASML, Nestlé, a utility, a bank, an insurer, a REIT.
- Belgian small caps: EVS, Econocom.
- The extremes above: Investor AB on Milan, WE.CONNECT, Newprinces, Cofidur.
- A few "Screened out" for revenue decline.

Their judgement on §3 and §4 (normalisation and dispersion thresholds) is the part this review can't replace.
