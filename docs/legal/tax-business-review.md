# Tax and business set-up review

13 Oct 2026 · First-pass review with the legal counsel persona ([`docs/experts/legal-counsel-persona.md`](../experts/legal-counsel-persona.md)), scoped by expert profile [04](../experts/04-accountant-tax-advisor.md). The persona is a lawyer, not an accountant, so this review covers its priority questions 5–6: company structure, liability and tax features. **Every threshold, rate and contribution figure must be confirmed by an ITAA accountant before you rely on it.** Belgian amounts are indexed every year.

**Reviewed:**

- The business plans: [v2](../strategic-business-plan-v2.md) (current mode: side activity, no company) and [v3](../strategic-business-plan-v3.md) (full-time, a BV at the transition gate).
- The [roadmap](../roadmap-2026-2027.md).
- The external items in [`compliance-implementation-plan.md`](compliance-implementation-plan.md): BIZ-1 to BIZ-11 and B6.
- The paid terms and privacy notice.
- The tax estimates in the app (`uvalu/compliance/disclosures.py`).

## Conclusion

- **Nothing here blocks the free beta.** There is no income, so there is no VAT, no invoicing and no income tax yet.
- **The paid launch: medium.** VAT on cross-border digital services is manageable, but it has to be designed into the checkout (L18), not added afterwards.
- **The structure question carries more risk than the plans assume: medium–high.** As a sole trader in secondary occupation (*bijberoep*), you are liable for Uvalu's obligations with all your private assets. Uvalu's main legal risks are claims over signals, data licences and GDPR, and they land on a natural person. v2 and v3 put off a BV until the full-time transition. The liability side argues for at least the cheap protections now, and for a BV earlier than v3's revenue gate if the claims risk grows (§2).
- **The tax figures in the app: low.** They are labelled as estimates, with the rules, the review date and the cases not handled. That is the right approach. What remains is keeping them current (§6).

Each point is marked as settled law, interpretation, or unclear.

## 1. Registration and social status

**Settled.** Before carrying on a professional activity, a sole trader registers with the Crossroads Bank for Enterprises (KBO) through an enterprise counter, and joins a social insurance fund. *Bijberoep* status requires a main occupation, usually employment of at least half-time. Social contributions are a percentage of net professional income, with no minimum contribution below a yearly income threshold.

**Interpretation.** A free beta without income is a preparatory activity, and most advisers would not require registration for it (question B6 in the compliance plan). Two things argue for registering **before the beta opens to strangers** anyway:

- the MAR producer identity and the CEL information duties (L4)
- the fact that registration is cheap and quick

**Settled, but needs a check.** Your employment contract may contain an exclusivity or non-compete clause, or an IP clause (BIZ-10).

- WER art. XI.296 presumes that the economic rights in software an employee creates **in performing their job** pass to the employer. Software written in free time on your own equipment falls outside that, but it helps to be able to show it.
- Read the contract, and keep evidence the code was written outside working hours and equipment: the git history already shows dates and times.
- Tell your employer if the contract requires it.

## 2. Legal form and liability

| | Sole trader (eenmanszaak, bijberoep) | BV |
|---|---|---|
| Liability | Unlimited, private assets included | Limited to the company, except director liability (fault, serious tax or social debts) |
| Income tax | Personal income tax, **added on top of your salary**, so at your marginal rate | Corporate tax, with a reduced SME rate on the first band of profit, then dividends or salary to you |
| Set-up | KBO registration, small fee | Notarial deed, financial plan, bank account; v3 estimates €1,500–2,500 |
| Running costs | Simple bookkeeping, personal tax return | Double-entry bookkeeping, annual accounts, corporate return; v3 estimates €1,500–3,000 a year for an accountant |
| Contracts | In your name | In the company's name (Mollie, EODHD, Hetzner, Brevo); move them at incorporation |

**Interpretation.** Two points change v3's assumption that a BV comes only at the full-time transition:

- **Tax:** because bijberoep profit is taxed at your *marginal* rate on top of a salary, a BV can pay off at a lower profit than v3's €9,000/month gate. The accountant should calculate the break-even with your actual salary.
- **Liability:** the risks set out in reviews 1–3 (MAR, data licences, GDPR, consumer claims) attach to the operator. A BV doesn't shield you from your own fault as director, or from administrative fines on you personally, but it does keep ordinary contract claims and vendor disputes away from your home.

**Cheap protections that work as a sole trader** (settled):

- A **notarial declaration that your family home cannot be seized** for professional debts (available to every self-employed person since 2017; the notary will cite the current article). It covers debts that arise after the declaration.
- **Professional liability insurance plus cyber insurance** (BIZ-8). Tell the broker exactly what the signals are, or the cover may not apply.
- **The liability caps in the terms** (privacy review §4), and the narrowed clause recommended there.

**IP (BIZ-6).** If a BV comes later, transfer the code, brand and domain to it in writing, at a value the accountant sets. Whether the innovation income deduction helps depends on the structure. Ask the accountant; it is generally a company-tax measure.

## 3. VAT

**Settled (EU rules; Belgian figures to confirm).** Uvalu sells electronically supplied services to consumers.

- **Below €10,000 a year** of cross-border B2C sales to other EU countries (a single EU-wide threshold), Belgian VAT applies to every sale. At 21%.
- **Above that,** the customer's country's VAT applies. You declare it quarterly in Belgium through the **One-Stop-Shop (OSS)** instead of registering in each country.
- **Belgian small-business exemption:** below the annual turnover threshold (€25,000 at the time of writing; confirm) you can opt out of charging VAT. You then can't recover input VAT on EODHD, Hetzner and similar costs.
- **Location evidence:** for these services the seller must record evidence of the customer's country (Implementing Regulation 282/2011, art. 24b). Below €100,000 a year, one item from an independent party, such as the card's issuing country from Mollie, can be enough.

**Interpretation.** For a small subscription base mostly in Belgium:

- The **exemption keeps the admin minimal**, but each foreign-country customer counts toward the €10,000 cross-border threshold. Above it, the exemption stops covering those sales, and you charge their VAT via OSS. Whether an exempt business can then use OSS for only the foreign sales is a question for the accountant.
- Prices: the terms say **consumer prices include VAT**. With per-country VAT above the threshold, either the price stays the same everywhere and your net income varies (simplest), or the price varies by country. Decide before building the checkout.
- Recoverable input VAT is worth more as licence costs grow. EODHD with a display licence may tip the balance toward the normal regime.

**Merchant of record: decide before the checkout (L18).** Mollie is a payment provider, so **you** are the seller and handle VAT, invoices and refunds. A merchant-of-record platform (Paddle, Lemon Squeezy and similar) **becomes the seller**. It handles VAT worldwide, for a higher fee per transaction. It also changes the legal set-up: the platform contracts with the consumer, sets part of the checkout and refund terms, and becomes a controller in the privacy notice. Reviews 2 and 4 then both need a small update. For a few hundred EU subscribers, Mollie plus OSS is usually cheaper. A merchant of record is simpler if you sell outside the EU.

## 4. Invoices and bookkeeping

- **Settled.** Belgian rules don't generally require invoices to consumers. Mollie receipts or simple invoices are still good practice, and the paid privacy notice and README already assume invoices are kept 10 years. Keep a ledger linking every Mollie payment, refund and chargeback to an account and a country.
- **Settled (Belgium, from 1 January 2026).** Invoices **between businesses** must be structured e-invoices, usually sent over Peppol. Uvalu sells to private investors, so make the terms and checkout **consumer-only**, or be ready to send Peppol invoices to a business that subscribes. The terms already address "private investors".
- **Interpretation.**
  - A free trial is not revenue, and no VAT is due until the first payment.
  - A withdrawal refund reverses the sale and its VAT in the period of the refund.
  - Mollie fees are a cost, not a reduction of turnover.
  - **The accountant:** the privacy review's open question, whether the accountant is a processor or an independent controller, goes to them directly.

## 5. Costs and deductions

**Settled principle; amounts are the accountant's call.** Professional costs are deductible against Uvalu's income, either as real costs or as a flat-rate deduction where that is higher. Real costs include:

- EODHD and other data licences, Hetzner, Brevo and the mailbox provider
- the domain, and software subscriptions including AI tools
- legal and accounting fees, insurance
- a share of home office and equipment

Start keeping receipts **now**, even before registration. Costs from the start-up phase can often be deducted once the activity begins.

## 6. Tax figures in the app

**Interpretation, low.** The Dividends screen estimates Belgian withholding tax after foreign withholding. It labels itself "Estimate under Belgian rules", with the rules, the review date (`TAX_RULES_REVIEWED = 2026-10-04`), the cases not handled (the dividend exemption, substantial holdings, non-residents and others) and the user's responsibility. That is informational tooling, not tax advice, and it matches the Terms ("No tax advice").

What to keep doing:

- **Review the rates once a year,** in January and after each budget announcement. Bump `TAX_RULES_REVIEWED`. A stale date is itself a warning to users.
- **Any new tax feature needs its own review first** (TAX-7). A capital-gains tax estimate is an example: Belgium's rules on gains on financial assets changed recently, so check their current status. Don't add one without a review.
- Users outside Belgium see Belgian rules. The screen says so, which is enough while the label is visible.

## Recommended changes, in order of value

1. **Now, at no cost:** read the employment contract for exclusivity and IP clauses, and start a folder of business receipts (L24).
2. **Before strangers join:** register with KBO in bijberoep, which also completes L4. Make the declaration that the family home can't be seized. Get a quote for liability and cyber insurance (L25).
3. **Before building the checkout:** choose between Mollie plus OSS and a merchant of record. Choose the VAT regime (exemption or normal). Decide prices with VAT included per country. Plan how the checkout records country evidence (L26, feeding L18).
4. **With the accountant:** the break-even between sole trader and BV, using your real salary and expected profit. The trigger for incorporating may be earlier than v3's revenue gate (L27).
5. **Every January:** review the tax rates in the app (L28).

## Facts the review still needs

- Employment status: full-time or part-time, and whether the contract has exclusivity, non-compete or IP clauses.
- Expected price and subscribers for years 1–3 (v2 says €5–10 a month; v3 says about €15 average). Also the expected share outside Belgium.
- Whether you own your home (relevant to the declaration that it can't be seized).
- Whether you will sell outside the EU (decides merchant of record or not).
