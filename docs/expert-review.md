# Expert review — who Uvalu needs

*Drafted 12 Oct 2026.* A full profile for each expert is in [experts/](experts/README.md).

Uvalu is a paid stock screener for European retail investors. It shows fair values and descriptive model signals (Undervalued / Mid score / Low score / Screened out), has a portfolio manager with risk scores, and runs on Hetzner, Brevo and Mollie. Market data comes from Yahoo Finance today, with a move to EODHD planned. The experts below are ranked by how badly a problem in their area could hurt Uvalu.

## Must have before the paywall goes live

### 1. Financial-regulation lawyer

This is the one that could stop the launch.

- **Key question:** do the scores, fair values and model signals count as investment advice or an investment recommendation under MiFID II and the Market Abuse Regulation (MAR)? If they do, a licence may be needed, or they have to be worded and disclosed in a specific way.
- **Conflict of interest:** the founder holds some of the stocks Uvalu covers. That usually means mandatory disclosures.
- **Hand over:** `docs/legal/policies/`, legal items L1–L11 in `docs/open-items.md`, and the compliant model M1.
- **Who:** a firm in the country Uvalu operates from that knows the local financial regulator.

### 2. Privacy and consumer-law lawyer

Often the same firm as #1.

- **GDPR:** privacy policy, data processing agreements with Hetzner, Brevo and Mollie, how long data and backups are kept (the 30-day Hetzner rotation is still unconfirmed), export and account deletion.
- **Consumer law for subscriptions:** the 14-day withdrawal right combined with the 30-day trial, whether the terms are fair, and auto-renewal rules.

### 3. Data-licensing check

This can be a short review by the lawyer, or a direct question to EODHD.

- Yahoo Finance, the current source, allows personal use only (open item L2). Does the planned EODHD plan allow its data to be shown to paying subscribers? Most market-data plans are for personal use only and need a separate redistribution licence. This is easy to miss and expensive to fix later.

### 4. Accountant or tax advisor

- VAT on digital services sold across the EU (the One-Stop-Shop scheme).
- The legal form of the business.
- How to treat Mollie income.

## Strongly recommended

### 5. Valuation expert

Ideally a CFA or a working equity analyst.

- Is the fair-value ladder sound (dividend model, earnings-power value, book value, free cash flow), along with the vetoes, the peer-group scoring and the sector rules?
- Would an expert put their name to the methodology page?

### 6. Quant or data scientist

- Any track record shown must be free of look-ahead and survivorship bias.
- Check data quality and the thresholds behind the risk bands.

### 7. Security tester

- Login, two-factor and passkeys, encryption, backups, and session handling.
- Two severe issues were already found and fixed internally (session revocation, backup secret exposure), so an outside check is worth the money.

## Nice to have

8. **Usability testing with 5–8 real target users** (retail value investors). This will teach more than another expert would.
9. **Native-speaker finance review of the six translations.** General translators often get financial terms wrong.
10. **Accessibility review.** This becomes more relevant under the European Accessibility Act.

## Suggested order

1. **Lawyers #1–#3 together.** They block selling subscriptions.
2. **Accountant (#4)** before the first invoice.
3. **Valuation expert and quant (#5, #6)**, then the **security test (#7)**.
4. **User testing (#8)**, which can run alongside any of the above.

## Next step

Briefing packs for #1–#3 are in [experts/briefings/](experts/briefings/README.md) (13 Oct 2026). Fill in the [Sven] placeholders before sending. Packs for #4–#10 follow when those reviews come up.
