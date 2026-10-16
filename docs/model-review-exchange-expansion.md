# Model review: exchange expansion plan

16 Oct 2026. Written in the roles of expert profiles [05 Valuation expert](experts/05-valuation-expert.md) and [06 Quant / data scientist](experts/06-quant-data-scientist.md). It reviews what the [exchange expansion plan](exchange-expansion-plan.md) does to fair values, scores and signals. Like the other persona reviews, it is a first pass and doesn't replace the real experts. Earlier reviews: [valuation-model-review.md](valuation-model-review.md) (#5), [quant-review.md](quant-review.md) (#6).

**Evidence used:**
- the signal snapshot of 16 Oct (`data/compliance/signal_snapshots/2026-10-16.jsonl.gz`, 1,728 public stocks);
- `.cache/fundamentals.json`;
- Yahoo checks on 16 Oct (BT-A.L, ULVR.L, SHEL.L, MAERSK-B.CO, GLEN.L);
- the code paths named in each finding.

## Verdict

Expanding the universe is sound for the model, because the scoring is relative and a larger peer group is more robust. But three things would produce systematically wrong signals in the new markets, and they must be fixed before those markets are public:

1. **A single euro-area discount rate for all currencies** (M2).
2. **0% tax for offshore-registered companies in EPV** (M3).
3. **A country tilt that already exists and will grow** (M1).

**Recommendation:** don't switch the new markets on all at once (D9). Use a **one-week shadow build** and a **go/no-go per exchange** (M6).

## Findings

| # | Finding | Role | Severity |
|---|---|---|---|
| M1 | A country tilt already exists and will grow | Quant + Valuation | High |
| M2 | One euro-area discount rate for all currencies | Valuation | High |
| M3 | EPV would use 0% tax for offshore-registered companies | Valuation | High |
| M4 | London needs a golden sample before it goes public | Valuation | Medium |
| M5 | The liquidity score counts shares, not money | Quant | Medium |
| M6 | Shadow build and go/no-go per exchange | Quant | Medium |
| M7 | Signal continuity when the chosen line changes | Quant | Medium |
| M8 | Thin markets will be mostly "No signal" | Valuation + Quant | Medium |
| M9 | Index membership isn't point-in-time | Quant | Low |
| M10 | Methodology and published distribution | Valuation | Low |

### M1. A country tilt already exists and will grow (high)

The 16 Oct snapshot, by exchange:

| Exchange | Stocks | Undervalued | Screened out | Median trailing P/E |
|---|---|---|---|---|
| Brussels | 107 | 4% | 42% | 12.2 |
| Paris | 571 | 2% | 54% | 13.5 |
| Frankfurt | 376 | 2% | 48% | 15.3 |
| Amsterdam | 82 | 1% | 51% | 15.4 |
| Milan | 375 | 2% | 41% | 16.9 |
| Zurich | 217 | **0%** | 42% | **20.6** |

The P/E fair value and the percentile ranks use sector medians **pooled across the whole universe**. A market that trades at lower multiples gets more "upside" in every sector, and a market at higher multiples gets less. That's why Zurich has no Undervalued stock and Brussels has twice the average. The new markets widen the spread. The UK, Athens and Warsaw tend to trade at lower multiples, and Stockholm and Copenhagen at higher ones. Without a check, the Undervalued list would fill up with UK, Greek and Polish stocks for reasons that have more to do with the market than with the companies.

This isn't wrong in itself: a cross-country value screen will lean towards cheap markets. But it has to be **measured and shown**, not discovered by users.

**Recommendations:**
- Add the signal mix and median P/E **per exchange** to the build's data-quality summary. Alert when one exchange's Undervalued share is more than 3× the universe's.
- During the shadow build (M6), compare two options: pooled sector medians (today) and **sector × region** medians (4 regions: Western Europe, UK & Ireland, Nordics, Southern & Central Europe, with a minimum group size and pooled as fallback). Choose on the evidence. If the tilt stays within 3×, keep pooled for simplicity.
- Whichever is chosen, the methodology page says in one line that peers are pooled Europe-wide (or by region), and what that means.

### M2. One euro-area discount rate for all currencies (high)

`RISK_FREE_RATE = 0.03` ("euro area approximation") and `EQUITY_RISK_PREMIUM = 0.05` set the discount rate for **every** stock (`_approx_wacc`). Fair values are computed in the quote currency, so a DDM or EPV in ISK, PLN, NOK or GBP is discounted at a euro rate. Where government yields are higher than in the euro area (Iceland and Poland clearly; the UK and Norway somewhat), fair values come out **too high**, and those markets will show systematically more "Undervalued". Switzerland goes the other way (lower yields): the same rule makes Swiss fair values a little too low today, which adds to the tilt in M1.

Two consistent fixes:
- **(a) A risk-free rate per currency:** the 10-year government yield, in the country/currency table, updated quarterly, with the date. The discount rate then matches the currency the cash flows are in.
- (b) Value everything in EUR: convert per-share fundamentals to EUR, discount at the euro rate, and convert the fair value back. That hides currency risk and is harder to explain.

**Recommendation: (a).** Fill the table from official central-bank or ECB statistics, not from memory; this review gives no yields on purpose. Until then, keep ISK and PLN stocks out of Undervalued, the same treatment as `currency_unverified`.

### M3. EPV would use 0% tax for offshore-registered companies (high)

EX-18 adds Jersey, Guernsey, the Isle of Man and Bermuda to `COUNTRY_TAX_RATES`. With their headline rates (0%), EPV's `EBIT × (1 − t) / WACC` rises by about a third against the 25% default. But these companies (Glencore, WPP, the Bermuda shipping companies) are taxed where they earn their profits, not where they are registered. Estonia and Latvia are similar: 0% on retained profits, but tax is due when profits are paid out.

**Recommendations:**
- Use `DEFAULT_TAX_RATE` (25%) for registrations with a 0% or near-0% headline rate.
- Use the distribution rate for Estonia and Latvia (about 20–22%).
- Put the rule in the country table next to the withholding defaults (plan §5b), so both are reviewed together by the tax advisor.
- Longer term: an effective tax rate from the income statement (tax ÷ pre-tax profit, averaged over 3 years) would be better for every company. That's a separate model change, not part of this plan.

### M4. London needs a golden sample (medium)

Pence (EX-14) and mixed reporting currencies (BP, Shell, Glencore and HSBC report in USD; Unilever in EUR) make London the most error-prone market.

**Recommendation:** before London goes public, check a fixed sample of 20 FTSE 100 companies. It should include the USD and EUR reporters, a bank, an insurer, a REIT and a miner, plus Maersk (DKK quote, USD reports) as a non-UK control. Acceptance:
- P/E within 2% of Yahoo's own `trailingPE` (which Yahoo already corrects for pence);
- fair value ÷ price between 0.2 and 5;
- dividend yield within 0.5 points of Yahoo's.

Keep the sample as a regression test (fixtures, no network).

### M5. The liquidity score counts shares, not money (medium)

`_liquidity_score` bands average volume in **shares** (25k / 100k / 500k). Across markets that isn't comparable: one Maersk share costs about DKK 24,000, while many London and Athens stocks cost a few pence or cents. Maersk scores as illiquid, and penny stocks score as very liquid. The risk sub-score and the composite inherit this.

**Recommendation:** band on **average traded value in EUR** (volume × price × FX rate), the same measure EX-4 uses to choose lines. Calibrate the new bands on the current universe so today's scores barely move: take the traded values at today's band edges. Test that the share of each band changes by less than 2 points on today's 1,728 stocks.

### M6. Shadow build and go/no-go per exchange (medium)

The plan enables all new exchanges at once (D9) and marks the first rebuild as `universe_change` (EX-35). That records the shift but doesn't tell you in advance whether it's acceptable.

**Recommendations:**
- Run a **shadow build** for about a week: the expanded universe is scored in the background, not shown, and written to its own snapshot. Compare it daily with the live build:
  - how many existing stocks change signal only because the peer group changed;
  - the per-exchange signal mix (M1);
  - data quality per exchange.
- **Go/no-go per exchange.** An exchange goes public only when:
  - at least 60% of its listings have a fair value;
  - fewer than 5% are `currency_unverified`;
  - its Undervalued share is at most 3× the universe's;
  - for London, the golden sample (M4) passes.
- An exchange that fails stays hidden, with the reason logged, and is checked again after the next fix.
- Start the shadow build after Q1 ends (21 Oct). Its first week then also serves as the post-Q1 flicker check for the expanded universe.

This changes D9 from "all on by default" to "on when it passes". The Admin switch still works as an override.

### M7. Signal continuity when the chosen line changes (medium)

The signal history, the daily snapshots and the hysteresis are keyed by ticker. When a company's chosen line changes (architecture review A3), the new ticker starts without history. The hysteresis then can't hold the previous signal, so a line change can cause a signal change, and the Q1 metrics count it as flicker.

**Recommendation:** when a line changes, carry the previous signal and hysteresis state over to the new ticker, and log `listing.switched` as the changed input. Add a test: a switch alone never changes the signal.

### M8. Thin markets will be mostly "No signal" (medium)

Yahoo's fundamentals are patchy for Athens, the Baltics, Iceland and parts of Warsaw. `GRF-P.MC` (Madrid) came back with no fundamentals at all. These rows will mostly be "No signal" or `fv_basis_thin`, and (architecture review A9) on the 3-hour retry. That isn't a model error, but a market where most rows say "No signal" looks broken (UX review X7).

**Recommendation:** this is what the go/no-go in M6 is for. The 60% fair-value threshold will probably keep the Baltics and Iceland hidden until EODHD's fundamentals arrive. That's better than showing them empty.

### M9. Index membership isn't point-in-time (low)

The index snapshot (plan §5) holds today's members only. That's fine for a filter. **It must never be used for a backtest or a performance claim** ("Euro Stoxx 50 Undervalued stocks returned …"), because it would be survivorship-biased. Add one line to the snapshot file's header and to `docs/data-contracts.md`.

### M10. Methodology and published distribution (low)

The methodology page publishes the signal distribution for the whole universe (REC-10 / MAR art. 4). With 21 markets, add the distribution **per market** (it's already computed for M1). Also describe the peer-group choice and the discount-rate rule (M1, M2) in plain language.

## What should stay

- **The one Europe-wide peer group** as the starting point. A per-country peer group would make Iceland's or Riga's medians meaningless (a handful of stocks per sector).
- **Converting reporting currency to quote currency (M2 model).** It handles Maersk, Equinor, BP and Unilever correctly once the units are right.
- **`currency_unverified` kept out of the peer group and out of Undervalued.** Use the same mechanism for M2's interim rule.
- **Signal hysteresis and carried-forward inputs (Q1).** They will absorb much of the day-to-day noise from the new data.

## Changes proposed to the plan

| # | Change | Finding |
|---|---|---|
| 1 | Per-exchange signal mix and median P/E in the data-quality summary, with an alert at more than 3× | M1 |
| 2 | Compare pooled vs. sector × region medians in the shadow build; choose on the evidence | M1 |
| 3 | Risk-free rate per currency (10-year government yield, from official data); ISK and PLN kept out of Undervalued until it's in | M2 |
| 4 | Offshore and 0% registrations use the 25% default in EPV; Estonia and Latvia use the distribution rate | M3 |
| 5 | London golden sample of 20 + Maersk, kept as a regression test | M4 |
| 6 | Liquidity bands on traded value in EUR, calibrated so today's scores barely move | M5 |
| 7 | One-week shadow build after 21 Oct; go/no-go per exchange (replaces "all on" in D9) | M6 |
| 8 | Carry signal history and hysteresis over when a line changes | M7 |
| 9 | "Not for backtests" note on the index snapshot | M9 |
| 10 | Signal distribution per market and peer/discount-rate text on the methodology page | M10 |
