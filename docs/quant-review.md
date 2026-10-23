# Quant and data review

13 Oct 2026 · First-pass review in the role of expert profile [06](experts/06-quant-data-scientist.md): a quant / data scientist reviewing data quality, signal stability, the risk framework and backtest readiness. There is no separate persona file for this role. The review follows the profile's scope: conclusion first, then evidence. It does not replace a real quant's review, especially the risk-band calibration on a population of portfolios.

**Reviewed:**

- [`portfolio_risk_assessment_algorithm.md`](portfolio_risk_assessment_algorithm.md) and `risk.py`.
- The signal history `data/compliance/signal_history.jsonl`: 4,781 records, from 4 to 13 Oct 2026.
- The 10 daily snapshots in `data/compliance/signal_snapshots/`.
- The fundamentals cache, and the 18 cached 10-year price histories in `.cache/history/` (holdings plus the benchmark).

The valuation inputs are covered in the [valuation model review](valuation-model-review.md), so this review doesn't repeat them.

## Conclusion

1. **High: signals flicker.** In 9 days there were **805 signal changes on 242 stocks**. One stock changed 21 times, crossing a score of 40 back and forth by 0.1 point, several times a night. Stocks also drop in and out of "Screened out" within minutes. A signal that changes on noise is hard to present as an objective opinion. It also fills the 12-month history, which the market abuse rules (MAR) may require, with noise (§1).
2. **Medium: the historical stress scenarios use US figures.** The four crisis drawdowns and dates are the S&P 500's. The portfolio beta is regressed on the EURO STOXX 50. Uvalu keeps 10 years of price history, so the dot-com and 2008 windows can't be replayed and always use these figures (§3).
3. **Medium: the risk bands are not calibrated, only defined.** 0–25–50–70–85 is a scale with no reference portfolios. Nobody can yet say whether a typical 20-stock European portfolio lands in Moderate or Elevated (§4).
4. **Backtests: none exist, and none should be built on the current data.** Yahoo's fundamentals are today's restated figures, and the universe is today's ticker list. Any historical backtest would have look-ahead and survivorship bias. The daily snapshots that started on 4 Oct 2026 are the right foundation for a forward track record (§5).
5. **Good: price data and engine design.** The cached price histories are clean. The engine does the right things:
   - converts everything to euros before computing anything
   - regresses betas
   - uses historical VaR and CVaR
   - runs a block-bootstrap Monte Carlo with an explicit CAPM drift and a fixed seed
   - drops the factor slot instead of filling it with 50

## 1. Signal stability (high)

**Evidence.** The signal history from 4 to 13 Oct 2026 holds 3,976 "first" records and **805 changes**:

| Transition | Count |
|---|---|
| Low score ↔ Mid score | 221 + 182 |
| Mid score ↔ Undervalued | 99 + 83 |
| Mid score ↔ Screened out | 86 + 78 |

- **42 stocks changed 5 times or more.**
- SRAIL.SW alternates between score 39.9 (Low score) and 40.0 (Mid score). The overnight changes come about 15–30 minutes apart, 21 changes in total.
- TII.DE goes in and out of "Screened out" for "dividend at risk" within minutes on 10 Oct.

**Causes.**

1. **No hysteresis, and continuous recomputation.** Signals are recomputed whenever the cache changes, and a cache entry refreshes every 24 h ± 4 h per ticker. Each refresh moves the percentile ranks of everyone else slightly. Any stock close to a threshold then flips on noise.
2. **Inputs changing between builds minutes apart.** A veto that toggles within minutes isn't a change at the company. It points at the fetch pipeline:
   - a partial payload where a statement history is missing, so the trend veto can't run and the stock "passes"
   - or two fetch lanes giving slightly different rows

   The rules that drop out most often are revenue decline (42), no trading volume (22), negative FCF (15) and retained-earnings erosion (14). Each depends on a field that is sometimes missing (`ebitHistory` 14%, `fcfHistory` 11% missing in the cache).

**Fix.**

- **Build signals once a day** from one consistent snapshot: S4, the daily build planned for M2. Bring it forward; it is the main fix.
- **Add hysteresis:** a stock leaves a band only when it crosses the threshold by a margin, for example 2 score points or 2 points of margin of safety. Publish the rule on the methodology page.
- **Carry the last known value forward** when a veto's input is missing, instead of treating missing as a pass. Show it with a data flag.
- Log *which input* changed in each `signal_change` record. This review couldn't tell from the record alone.

## 2. Data quality

| Check | Result |
|---|---|
| Price histories (18 cached series, 10 years) | No gaps over 7 days, no zero or negative prices. A handful of daily moves above 25%; the ones checked match real events. |
| Fundamentals freshness | All public rows fetched within the last day. None older than 7 days. |
| Missing fields (public universe) | EPS 6%, book value 4%, beta 8%, sector 10%, shares outstanding 10%, `fcfHistory` 11%, `ebitHistory` 14% |
| Currency and universe | See the valuation review, V1–V2 |

What's missing is **automated monitoring**. Nothing alerts when a field's missing rate jumps, when a fetch returns a partial payload, or when the number of signal changes in a build spikes. Add a per-build data-quality summary to the logs: missing rates per field, rows changed, vetoes added or dropped. Alert on thresholds. The snapshots already hold everything needed.

## 3. Risk framework

**Historical scenarios. Medium.** `HISTORICAL_SCENARIOS` uses −49% (2000–2002), −57% (2007–2009), −34% (2020) and −25% (2022), with S&P 500 peak and trough dates. The EURO STOXX 50 fell further in 2000–2003 and in 2008–2009, and less in 2022, with different dates.

- With 10 years of history (from September 2016), only COVID and 2022 can be replayed.
- The two big crises are **always** beta × these US drawdowns, while the beta is measured against the EURO STOXX 50.
- **Fix:** use the benchmark's own drawdowns and dates, or label the scenarios as US market moves.

**Betas of small caps. Low–medium.** OLS on daily returns understates the beta of thinly traded stocks: their prices react to the market a day late. Uvalu covers many Belgian and French small caps. Consider weekly returns, or a Dimson adjustment that adds one lagged term, for holdings below a volume threshold.

**VaR and CVaR. Good.**

- Historical simulation on 5 years of euro-converted returns, with the parametric formula only as a fallback.
- The disclosure text is right.
- One point: the 5-year window (2021–2026) includes 2022 but no crash like 2008. A 99% one-day VaR from it is optimistic, and the stress scenarios are what cover that. Say so next to the VaR on the methodology page.

**Monte Carlo. Good, and an error in our own documentation.** A block bootstrap with 20-day blocks, re-centred on a CAPM drift and seeded, is a sound design. The "Facts checked" list in [experts/README.md](experts/README.md) said "There is no Monte Carlo". That was wrong, and is corrected in this commit.

**Price series.** The cached closes appear to be dividend-adjusted, which is the usual yfinance default. That is right for volatility, Sharpe and drawdown, but it means "drawdown" includes dividends. Confirm it, and state it on the methodology page.

## 4. Risk-band calibration (medium)

The composite risk score is a weighted sum of six 0–100 sub-scores, and the bands cut it at 25, 50, 70 and 85. The cut-offs are defined, not calibrated. Nobody has checked where real portfolios land.

**Fix: a reference set.** Run `assess_portfolio` on about 8 fixed reference portfolios:

- EURO STOXX 50 equal-weighted
- a 20-stock diversified European portfolio
- a 5-stock portfolio
- a single stock
- a high-dividend portfolio
- a Belgian small-cap portfolio
- a one-sector portfolio
- a high-beta portfolio

Then:

- Check the bands put them in a sensible order and spread.
- Adjust the sub-score mappings, not the band edges, if they don't.
- Publish the reference points on the methodology page ("a diversified 20-stock portfolio scores about X"). That makes the scale explainable without becoming advice.
- Re-run the set at every model version change.

## 5. Backtests and track record

- **No backtest exists,** and the decision is not to publish signal performance (README D-table: "Signal performance: Not published"). Good.
- **Settled method.** A historical backtest needs point-in-time fundamentals, as known on each past date with reporting lags, and a universe that includes delisted stocks. Yahoo has neither. Its statements are today's restated figures, and the ticker list is today's. A backtest on this data would look better than reality, and must not be shown or used to tune thresholds.
- **The right foundation is already being built.** The daily snapshots, from 4 Oct 2026, store every signal with its inputs, model version and settings hash. After 12–24 months they allow an honest forward track record: signal on day *t*, return to *t*+h, by band. Keep them, including after the switch to EODHD. The data-licensing review's retention point (L20) is what makes that possible.
- **Threshold tuning.** Don't tune the 70/40 cut-offs or the composite weights on outcomes until that forward record exists. Any tuning before then fits noise. If thresholds change, log the reason in `settings_audit` as now.

## Recommended changes, in order of value

1. **Stability:** a daily signal build from one snapshot (bring S4 forward), hysteresis at the band edges, last known value carried forward for missing veto inputs, and the changed input logged (Q1).
2. **Data-quality monitoring** per build: missing rates, changed rows, vetoes added or dropped, with alerts (Q2).
3. **Stress scenarios** on EURO STOXX 50 drawdowns and dates (Q3).
4. **Risk-band reference set** of about 8 portfolios, sub-score mappings adjusted, reference points published (Q4).
5. **Small-cap betas:** weekly or Dimson-adjusted for illiquid holdings (Q5).
6. **Methodology wording:** VaR window limits, dividend-adjusted prices, the stability rule (with Q1), no backtests (Q6).

## For the real quant

Give them this review, the valuation review, read access to `data/compliance/` (snapshots and history) and `risk.py`. Ask for:

- the band calibration on the reference set (§4)
- a written protocol for the future forward track record (§5)
- a check of the hysteresis margins chosen for §1

## Re-measure after M2 (23 October 2026, Q1 closed)

Counted on `data/compliance/signal_history.jsonl`. The personal app stopped on 18 October,
so the window is 15–18 October (4 days, 17–18 October a weekend) instead of 14–21 October.
14 October itself is left out: its 133 changes are the one-off M2, M3 and M4 model bumps.

| | Signal changes |
| --- | --- |
| Baseline, 4–13 October | 865 in 10 days, about 87 a day |
| 15–18 October (M4) | 8, 15, 11, 9: about 11 a day |

- About 85–90% fewer changes, against 50% in the replay.
- Repeats are few and all small caps: INFRAC.SW changed 4 times, VACN.SW 3 times.
- The changes come with fair value and margin of safety (`Value Score`, `Sub MoS`,
  `fair_value` in `changed_inputs`), not from price moves alone.
- `data_quality.alert` fired 5 times on 18 October, all from the demo's 7–9 stock
  workspace on its first build (fixed on the demo branch in `a9da530`), none from
  the real universe.

**Decision:** Q1 is closed on these 4 days. The daily build (S4) is not needed before
the EODHD switch; it comes with it, since end-of-day data gives one snapshot a day anyway.
