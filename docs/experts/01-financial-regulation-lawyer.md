# Expert Profile: Financial-Regulation Lawyer

**Project:** Uvalu — stock screening and portfolio tool for solo retail investors
**Priority:** Critical — must be resolved before public launch or paid subscriptions

---

## Why Uvalu needs this expert

Uvalu shows fair-value estimates, margin-of-safety figures, composite scores and model signals (Undervalued / Mid score / Low score / Screened out / No signal, renamed from the original BUY / MONITOR / AVOID / VETO) for individual stocks. Depending on how these are presented and to whom, they could be classified as *investment advice* or *investment recommendations* under EU law. That classification decides whether Uvalu needs a licence, what disclaimers and disclosures are mandatory, and whether the current signal wording is acceptable.

## Required expertise

- EU financial-services regulation, with hands-on work on **MiFID II** (Directive 2014/65/EU) and its Belgian transposition
- **Market Abuse Regulation** (MAR, Regulation 596/2014) and Delegated Regulation 2016/958 on the objective presentation of investment recommendations and disclosure of conflicts of interest
- Practical experience with the Belgian regulator **FSMA** (licensing, registration, informal pre-consultation)
- Familiarity with fintech / robo-advice / screener products, ideally having advised a comparable SaaS or research publisher
- Knowledge of EU passporting, in case Uvalu is sold outside Belgium

## Scope of review

1. **Advice vs. information:** Do Uvalu's scores and signals constitute a *personal recommendation* (MiFID II investment advice) or general, non-personalised information? Does the portfolio and risk module, which uses the user's own holdings, change that answer?
2. **Investment recommendations under MAR:** Do the model signals and fair values qualify as "recommendations"? If so, which presentation and disclosure duties apply (identity of producer, methodology, date, conflicts)?
3. **Licensing:** Is any FSMA licence or registration needed (investment firm, investment advisor, independent financial planner)? Are there exemptions for publishers / generic tools?
4. **Conflicts of interest:** What must be disclosed if Sven personally holds stocks Uvalu scores? Policy for trading around signal changes.
5. **Wording and UX:** Are the renamed labels (Undervalued / Mid score / Low score / Screened out) defensible, or should they be more neutral still? `docs/stock_valuation_algorithm.md` marks this **[Counsel] to confirm**. Placement and wording of disclaimers.
6. **Marketing:** Rules on performance claims, backtest results and testimonials in advertising.

## Expected deliverables

- Written legal opinion on the classification of Uvalu's features (advice / recommendation / information)
- List of required changes to labels, screens and onboarding
- Review of the existing disclaimer, methodology and conflicts-of-interest pages in `docs/legal/policies/`, with corrected wording
- Personal-trading policy for the founder
- Guidance on marketing claims involving backtests

## Material to prepare for the engagement

- Screenshots of the Dashboard, Screener, Analysis (stock detail), Portfolio and Risk screens
- `docs/stock_valuation_algorithm.md` and `docs/portfolio_risk_assessment_algorithm.md`
- The six legal pages in `docs/legal/policies/` (methodology, conflicts of interest, data sources, terms, privacy, complaints)
- Open legal items L1–L11 in `docs/open-items.md`
- Planned pricing tiers and target markets (countries)
- Draft marketing copy

## Questions to ask when selecting

- Have you advised a stock screener, research publisher or robo-advisor on MiFID II scope?
- Have you dealt with the FSMA on a scope question, formally or informally?
- Can you give a fixed-fee opinion for this specific question?

## Red flags

- Generalist corporate lawyer with no financial-services practice
- Answers "just add a disclaimer" without analysing the features
- No knowledge of MAR Delegated Regulation 2016/958

## Where to find

- Belgian law firms with a banking & finance or fintech practice
- Fintech associations (e.g. Febelfin network, Belgian fintech communities)
- Referrals from other Belgian fintech founders
