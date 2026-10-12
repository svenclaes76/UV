# Expert Profile: Valuation Expert (CFA / Equity Analyst)

**Project:** Uvalu — stock screening and portfolio tool for solo retail investors
**Priority:** High — credibility of the core product depends on it

---

## Why Uvalu needs this expert

Uvalu's core is a multi-model fair-value engine (Graham Number, sector-median P/E, Earnings Power Value, single- and multi-stage dividend discount models, with book-value and FCF fallbacks; an analyst-target model stays off until licensed, and there is no DCF). It feeds a composite score with margin of safety, a quality screen (hard vetoes) and a descriptive model signal (Undervalued / Mid score / Low score / Fails quality screen / No signal). EV/EBITDA is shown but not used in the valuation. Users will trust and act on these numbers. An experienced valuation professional should check that the models are correctly specified, applied to the right companies, combined sensibly, and explained honestly.

## Required expertise

- **CFA charterholder** or equivalent experience as a sell-side / buy-side equity analyst (ideally 7+ years)
- Deep practical knowledge of DCF (WACC, terminal value, growth assumptions), multiples, EPV, dividend discount models and Graham-style value investing
- Sector awareness: where standard models break (banks, insurers, REITs, utilities, cyclicals, loss-making growth companies)
- Peer-group construction and relative valuation (industry classification, size and region adjustments)
- Experience writing or reviewing **methodology documentation** for retail or institutional audiences
- Bonus: familiarity with European small and mid caps, and with accounting differences (IFRS vs. US GAAP)

## Scope of review

1. **Model specification:** inputs, formulas, default assumptions (fixed 3% risk-free rate and 5% equity risk premium, growth caps, terminal growth, normalisation of earnings), and whether a DCF or comparable multiples are worth adding
2. **Model applicability:** which models should be excluded per sector or company type; handling of negative earnings, buybacks, one-offs
3. **Aggregation:** weighting of models into one fair value, treatment of model disagreement (the "Consensus" idea — where models agree)
4. **Vetoes:** which red flags should override a positive valuation (leverage, dilution, negative FCF, accounting quality, going-concern risk)
5. **Peer-group scoring:** peer selection, sample size, outlier handling, ranking method
6. **Margin of safety and signal thresholds:** reasonableness of the signal cut-offs (Undervalued needs score ≥ 70 and margin of safety ≥ 10%; both configurable, the margin never below 10%)
7. **Sanity checks:** review of a sample of 20–30 real companies across sectors against professional estimates
8. **Methodology page:** clarity, honesty about limitations, no overstated precision

## Expected deliverables

- Written review of the valuation pipeline document with prioritised issues
- Recommended defaults and sector exclusions / adjustments
- Recommended veto rules
- Annotated sample results (where Uvalu is plausible vs. clearly off)
- Edited methodology page text suitable for retail investors

## Material to prepare

- `docs/stock_valuation_algorithm.md` and `screener.py`
- Data fields used (Yahoo Finance today, EODHD planned) and how missing data is handled
- Sample output for a diverse set of tickers
- Methodology page (`docs/legal/policies/methodology.md`)

## Questions to ask when selecting

- Which sectors have you covered, and how did you value financials?
- Have you reviewed quantitative or rules-based valuation tools before?
- How would you explain margin of safety and model uncertainty to a retail investor?

## Red flags

- Pure theory, no hands-on company coverage
- Wants to add many more models instead of fixing the existing ones
- Dismisses all automated valuation without engaging with the design

## Where to find

- CFA Society Belgium
- Former analysts from Belgian/Dutch brokers and asset managers working freelance
- Value-investing communities and newsletter writers with a professional background
