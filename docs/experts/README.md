# Expert profiles

One profile per outside expert Uvalu needs: why, required expertise, scope, deliverables, material to prepare, selection questions, red flags and where to find them. The ranking and suggested order are in [../expert-review.md](../expert-review.md).

| # | Expert | Main expertise | Priority |
|---|--------|----------------|----------|
| 01 | [Financial-regulation lawyer](01-financial-regulation-lawyer.md) | MiFID II / MAR: advice vs. information, licensing, conflict-of-interest disclosures | Critical |
| 02 | [Privacy and consumer-law lawyer](02-privacy-consumer-law-lawyer.md) | GDPR, processor agreements, subscription terms, withdrawal right, auto-renewal | Critical |
| 03 | [Data-licensing specialist](03-data-licensing-specialist.md) | EODHD and exchange redistribution rights, derived data, exports | Critical |
| 04 | [Accountant / tax advisor](04-accountant-tax-advisor.md) | EU VAT (OSS), legal form, subscription revenue | High |
| 05 | [Valuation expert](05-valuation-expert.md) | Fair-value models, vetoes, peer scoring, methodology page | High |
| 06 | [Quant / data scientist](06-quant-data-scientist.md) | Backtest bias, data quality, risk models and bands | High |
| 07 | [Security tester](07-security-tester.md) | Auth, 2FA, passkeys, sessions, encryption, backups | Critical |
| 08 | [UX researcher](08-ux-researcher.md) | Usability and comprehension testing with real retail investors | High |
| 09 | [Financial translators](09-financial-translators.md) | Native-speaker financial terminology in all six languages | Medium–High |
| 10 | [Accessibility specialist](10-accessibility-specialist.md) | WCAG 2.2 AA, EN 301 549, European Accessibility Act | Medium–High |

## AI expert personas

These are prompts that ask Claude to act as an expert. They are not profiles for hiring someone, and their answers don't replace a licensed professional.

| Persona | Use for | Hiring counterpart |
|---------|---------|--------------------|
| [Legal counsel, financial services](legal-counsel-persona.md) | First-pass legal questions: MiFID II / MAR, FSMA licensing, disclaimers, data licensing, GDPR, liability, tax features | 01, 02, 03 |

## Facts checked

On 12 Oct 2026 the profiles and the persona were checked against the repo and corrected:

- **Models:** Graham Number, sector-median P/E, EPV, and single- and multi-stage dividend discount models, with book-value and FCF fallbacks. The analyst-target model stays off until it is licensed. There is no DCF, and EV/EBITDA is shown but not used in the valuation (`docs/stock_valuation_algorithm.md`).
- **Signals:** Undervalued / Mid score / Low score / Screened out / No signal. These replaced BUY / MONITOR / AVOID / VETO.
- **Risk:** HHI, VaR, CVaR, maximum drawdown, Sharpe/Sortino, Fama-French factors and stress scenarios. There is no Monte Carlo. The bands are Low / Moderate / Elevated / High / Critical (`docs/portfolio_risk_assessment_algorithm.md`).
- **Data:** Yahoo Finance today, which allows personal use only (open item L2). A move to EODHD is planned.
- **Billing:** Mollie, monthly only, with a 30-day free trial. A free beta runs first.
- **Roles:** Admin / Analyst / Viewer.
- **Languages:** English (source) plus Dutch, French, German, Spanish and Italian.
- **Brand:** guidelines v1.5 (`docs/uvalu-brand-guidelines.md`).

If any of these change, update the profiles before you send one out.
