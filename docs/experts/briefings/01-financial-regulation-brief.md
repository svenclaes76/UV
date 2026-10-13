# Briefing: financial-regulation opinion for Uvalu

*Prepared 13 Oct 2026 by Sven Claes, founder of Uvalu (uvalu.app). For a Belgian lawyer with a MiFID II / MAR practice.*

## What we ask

A **written opinion** on whether Uvalu's outputs are investment recommendations (MAR) or investment advice (MiFID II), whether any licence, registration or FSMA notification is needed, and which changes would lower the risk. Please quote a **fixed fee** for the questions in §4 before starting.

## 1. Uvalu in brief

- An online tool for **private investors** in the EEA. It values listed shares and lets users record and analyse their own portfolio. It doesn't execute orders, hold money or securities, link to brokers, or take commissions, referral fees or advertising.
- **Operator:** Sven Claes, a natural person in Belgium (Herentals), trading as Uvalu. **Not yet registered** with the Crossroads Bank for Enterprises (KBO/BCE). Planned as a sole trader (eenmanszaak).
- **Universe:** about 1,500 shares on Euronext Brussels, Amsterdam and Paris, Borsa Italiana, Deutsche Börse and SIX Swiss Exchange.
- **Status today:** a **free, invitation-only beta** for people the founder knows, resident in the EEA, 18+. **Planned:** a paid monthly subscription (Mollie, 30-day free trial), with a 1 January 2027 target for the paid legal texts.
- **Languages:** English (reference) plus Dutch, French, German, Spanish and Italian.

## 2. What the user sees

**Per share, the same for every user:**

- A **fair value** from several models: Graham Number, sector-median P/E, Earnings Power Value, single- and multi-stage dividend discount models, with book-value and free-cash-flow fallbacks. There is no DCF, and analyst targets are off.
- The **margin of safety** against the price, and a **composite score**.
- A **model signal**: Undervalued / Mid score / Low score / Screened out / No signal. Until October 2026 these were BUY / MONITOR / AVOID / VETO.
  - "Undervalued" requires a score ≥ 70, a margin of safety ≥ 10% and at least two models.
  - "Screened out" names the rule that failed.
  - Every signal label carries a visible "Model signal" qualifier, enforced by an automated test. Each shows its time horizon (3–5 years), timestamp, the models used and a link to the methodology page.
- A 12-month **signal history** and the **distribution** of signals across the universe.

**Per user, from their own portfolio:**

- Holdings, P&L, dividends and cash.
- Portfolio risk figures: concentration (HHI), VaR, CVaR, maximum drawdown, Sharpe/Sortino, factor exposures and stress scenarios.
- Risk bands (Low / Moderate / Elevated / High / Critical) per portfolio and per position, computed from the user's own weights.
- On the Dashboard, a "Model signal" column next to the user's positions. The column header and tooltip state the signal is the same for every user.

**Never shown:** an action addressed to the user ("buy", "sell", "reduce", "rebalance"), alerts that combine a signal with the user's position, or suitability questions.

## 3. Decisions already made

These follow from an earlier internal review. Please challenge them if the law requires it.

- **Same output for everyone:** no profiling and no personalisation of signals (internal rules PER-1 to PER-5).
- **Methodology published in full.** Disclaimers on every screen. Users acknowledge a "no personal advice" notice.
- **Founder's holdings:** the founder holds some covered shares.
  - Any position, of any size, is disclosed next to the signal within 2 business days of a trade.
  - There is a trading blackout from deciding a model change until 2 trading days after it goes live, and a dated personal trade register.
  - Settings and model-version changes are logged with timestamps.
- **No published signal performance or backtests.** No third-party advertising.
- **A rebalancing feature is parked.** It will not be built without its own review.

## 4. Questions

1. **MAR classification (open item L3).** Do the fair values and model signals fall under art. 3(1)(35) MAR as investment recommendations? Is Uvalu an "expert" under art. 3(1)(34)(i), with the duties of Delegated Regulation 2016/958 art. 4? How does MAR apply to signals produced entirely by an algorithm, with no analyst per share?
2. **The beta.** Does an invitation-only group of people the founder knows count as "the public" or a "distribution channel"? Do the MAR duties apply before the paid launch?
3. **MiFID II advice.** Do any of the per-user outputs (risk bands per position computed from the user's weights, the "Model signal" column next to their holdings) amount to a personal recommendation under art. 4(1)(4) MiFID II and art. 9 of Delegated Regulation 2017/565?
4. **Licence or registration.** Is any FSMA authorisation, registration or notification needed for the beta or the paid service? Does a publisher-style exemption apply? Would you recommend an informal pre-consultation through the FSMA fintech contact point, and what should go in it?
5. **Producer identity (L4).** Delegated Regulation 2016/958 art. 2 requires the producer to be identified. Is a KBO number plus a business or domiciliation address enough, instead of the founder's home address? Does the legal form (sole trader or company) matter for the MAR or liability position?
6. **Conflicts of interest.** Is the disclosure and trading policy in §3 adequate under art. 20 MAR and art. 5–6 of Delegated Regulation 2016/958? Please give us a short personal-trading policy we can adopt.
7. **Labels and disclaimers.** Are the labels and the "Model signal" qualifier objective presentation? Does the Dutch and French wording ("Ondergewaardeerd", "Sous-évalué") carry extra risk (L6)? Please correct the methodology and conflicts pages and the disclaimers where needed.
8. **Marketing.** What rules apply if individual shares or signals appear in social media, emails or ads? What about claims of model performance, if we ever publish any?
9. **Cross-border.** Marketing to other EEA countries: do other national regulators' rules on recommendations or advice come into play?

## 5. Facts to confirm before the meeting

| Fact | Answer |
|---|---|
| Target countries for the paid launch | [Sven] |
| Accounts in the beta besides the founder's, and their countries | [Sven] |
| Will signals appear in marketing, social media or emails? | [Sven] |
| Will any part of Uvalu be free and public, without a login? | [Sven] |
| Planned price per month | [Sven] |
| Planned legal form (sole trader or BV) | [Sven] |

## 6. What we'd like back

- A written opinion on questions 1–4, separating settled law from interpretation.
- A marked-up version of the methodology, conflicts-of-interest and disclaimer texts.
- A personal-trading policy (question 6).
- A list of required changes to screens or labels, if any.
- A recommendation on whether, and how, to approach the FSMA.

**Not in scope:** privacy, consumer law, data licensing and tax. Those are covered by separate briefs.

## Attachments

Export to PDF with version and date.

1. Methodology page ([`policies/methodology.md`](../../legal/policies/methodology.md), and the beta version in `beta/`)
2. Conflicts of interest page (paid and beta versions)
3. Terms of use, §3 "What Uvalu is not" (paid and beta versions)
4. [`docs/stock_valuation_algorithm.md`](../../stock_valuation_algorithm.md) and [`docs/portfolio_risk_assessment_algorithm.md`](../../portfolio_risk_assessment_algorithm.md)
5. Screenshots: Dashboard (Holdings with the Model signal column), Screener, Analysis (stock page with signal, provenance and founder notice), Portfolio, Risk
6. Optional: our internal first-pass [signal label review](../../legal/signal-label-review.md)
