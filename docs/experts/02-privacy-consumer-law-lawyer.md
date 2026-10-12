# Expert Profile: Privacy and Consumer-Law Lawyer

**Project:** Uvalu — stock screening and portfolio tool for solo retail investors
**Priority:** Critical — needed before collecting user data or taking payments

---

## Why Uvalu needs this expert

Uvalu stores accounts, login data and users' portfolios (holdings, purchase prices, possibly linked financial information), and will sell subscriptions to consumers. That brings two bodies of law into play: data protection (GDPR) and EU/Belgian consumer law for online subscriptions, including withdrawal rights and automatic renewal.

## Required expertise

- **GDPR** practice: lawful bases, records of processing, DPIAs, data-subject rights, international transfers (SCCs, EU–US Data Privacy Framework)
- Drafting and negotiating **Data Processing Agreements** (Art. 28 GDPR) with SaaS vendors: hosting, email, payments, analytics, data APIs
- **EU consumer law:** Consumer Rights Directive (14-day withdrawal, digital-content exceptions), Unfair Contract Terms Directive, Digital Content Directive, Omnibus Directive
- **Belgian Code of Economic Law** (Wetboek Economisch Recht), including rules on tacit renewal and cancellation of consumer contracts
- Experience with the Belgian Data Protection Authority (Gegevensbeschermingsautoriteit / APD)
- Bonus: ePrivacy / cookie consent, Digital Services Act basics

## Scope of review

1. **Privacy notice and records of processing** for all data Uvalu collects (account, portfolio, usage, payment, logs)
2. **Is portfolio data sensitive?** Not a special category under Art. 9, but financial data raises the risk level — is a DPIA required?
3. **Processor inventory and DPAs:** Hetzner (hosting and backups), Brevo (email), Mollie (payments), the mailbox provider (still to choose), the market-data provider, and any analytics or error monitoring
4. **International transfers** to US-based processors
5. **Subscription terms (Terms of Service):** liability limits, disclaimer interplay with the financial-regulation opinion, governing law, price changes
6. **Withdrawal right:** 14-day right, the express-consent-and-acknowledgement mechanism for immediate access to digital content, how the right works when the 30-day free trial converts automatically (billing is monthly only)
7. **Auto-renewal and cancellation:** Belgian rules on tacit renewal, reminders before renewal, easy online cancellation
8. **Cookie banner** and analytics configuration
9. **Account deletion and data export** flows (right to erasure, portability)

## Expected deliverables

- Review of the existing privacy notice (`docs/legal/policies/`), plus a cookie notice if one is needed
- Record of processing activities (template filled in)
- DPA checklist per vendor, and a DPIA decision (with a DPIA if needed)
- Corrections to the existing terms of use so they are consumer-compliant
- Checkout wording: withdrawal-right waiver, renewal notice, cancellation flow requirements
- Data-breach response procedure (72-hour notification)

## Material to prepare

- Data-flow diagram: what data, where stored, which vendor
- List of all third-party services and their locations
- User-management module requirements (auth, RBAC, GDPR items already scoped)
- Pricing: Mollie, monthly only, 30-day free trial; a free beta runs first
- The existing privacy notice and terms of use in `docs/legal/policies/` and their open items in `docs/legal/policies/README.md`
- Countries targeted

## Questions to ask when selecting

- Have you drafted subscription terms for a B2C SaaS selling in Belgium and the EU?
- Do you provide templates in Dutch, French and English?
- Can you combine GDPR and consumer-law work in one fixed-price package?

## Red flags

- Offers only generic, copy-paste templates without reviewing the data flows
- Unfamiliar with Belgian specifics on tacit renewal
- Treats B2C as if it were B2B (consumer rights cannot be waived by contract)

## Where to find

- Belgian IT/IP and privacy law boutiques
- Certified DPOs (CIPP/E) who work with a lawyer for the contractual part
- Start-up legal packages offered by incubators and accelerators
