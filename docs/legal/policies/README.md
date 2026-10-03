# Uvalu public legal pages

Final texts of the six public legal pages, kept as the reference for building them into the app. Finalised Oct 3, 2026 from the drafts in `OneDrive\Desktop\legal` (written against *Uvalu — Legal Requirements for Launch*, Oct 2, 2026). The drafts themselves are left unchanged.

**Status:** content complete, **not yet publishable**. Remaining blockers: the `[TBD: …]` items (§3), counsel review, translations, and the implementation requirements (§4).

| Page | File | In-app route (proposed) | Requirement IDs |
| --- | --- | --- | --- |
| Terms of use | [terms-of-use.md](terms-of-use.md) | `/terms` | TOU-1..10, SUB-1..10 |
| Privacy notice | [privacy-notice.md](privacy-notice.md) | `/privacy` | GDPR-1..14, SEC-1..10 |
| Methodology | [methodology.md](methodology.md) | `/methodology` | REC-2..7, REC-10, DIS-3, DIS-4 |
| Data sources | [data-sources.md](data-sources.md) | `/data-sources` | REC-3, REC-4, DATA-1..6 |
| Conflicts of interest | [conflicts-of-interest.md](conflicts-of-interest.md) | `/conflicts` | REC-1, REC-8, REC-9, PER-7 |
| Complaints | [complaints.md](complaints.md) | `/complaints` | TOU-8 |

Each file starts with an HTML comment holding its status and its counsel points. Strip the comment when rendering.

## 1. Decisions (Oct 3, 2026)

| Topic | Decision |
| --- | --- |
| Operator | Sven Claes, sole trader (eenmanszaak), trading as Uvalu, Pol Heynsstraat 7, 2200 Herentals |
| Competent court (non-consumers) | Judicial district of Antwerp |
| Domain / site | uvalu.app (pricing at `/pricing`, sub-processor list kept in the Privacy notice at `/privacy`) |
| Effective date of version 1.0 | 1 January 2027 |
| Countries | EU/EEA residents only, age 18+ |
| Payments | Mollie B.V. (supersedes "Stripe" in `docs/roadmap-2026-2027.md`) |
| Billing | Monthly only; cancel any time, effective end of the current month |
| Free trial | 30 days; reminder email at least 7 days before it ends *(7 days chosen by default; confirm)* |
| Withdrawal | 14 days from the first paid day, **full refund** (draft option A) |
| Liability cap | Amount paid in the last 12 months, minimum EUR 100 |
| Reference language | English |
| Price change / terms change / termination notice | 30 days each (draft defaults) |
| Own positions | Threshold disclosure: positions above 0.5% of an issuer's capital (draft option A) |
| Marketing | Individual shares may be mentioned, always with a statement of whether the founder holds them |
| Signal performance | Not published (draft option A) |
| Minimum margin of safety for "Undervalued" | **10%** (code default is still 0%, see §4) |
| Signal labels | Undervalued / Neutral / Low score / Fails quality screen / No signal (from `screener_compliant.py`; not BDG-1's "Near fair value"/"Overvalued") |
| Market data | EODHD, **end-of-day prices only**, contract not yet signed |
| Analyst data | Not used (`ANALYST_INPUTS_ENABLED = False`) |
| Hosting / backups | Hetzner, Germany / Hetzner Storage Box, Germany |
| Service email | Brevo, France |
| Bookkeeping | External accountant, Belgium |
| Error monitoring / analytics | None, so no consent banner is needed |
| Google sign-in | Enabled at launch |
| Newsletter / marketing email | None |
| Mailboxes | `support@uvalu.app`, `security@uvalu.app`, `privacy@uvalu.app`, `complaints@uvalu.app` (create these aliases) |
| Complaint timelines | Draft defaults, confirmed: acknowledge in 2 working days, answer in 14 days, 30 days at most |

**Methodology** was rewritten from the code, not just filled in. The draft listed DCF and EV/EBITDA models, which do not exist, a composite score with other components, and labels the code does not use. Sources: `screener_compliant.methodology()`, `settings._SCORE_STYLES`, `risk_compliant` (`REF_*`, `RISK_BANDS`, `RISK_DISCLOSURES`, Monte Carlo constants), and the two `*_compliant.md` specs in `docs/legal/`. **Data sources** now describes the risk-free rate as a fixed model assumption rather than a data feed, and adds the EURO STOXX 50 benchmark.

## 2. Counsel review points

1. Withdrawal period counted from the first paid day after a trial that converts automatically. This is more generous than the minimum; confirm the wording.
2. Signal labels "Neutral" and "Low score" deviate from BDG-1 on purpose (`../algorithm-compliance-review.md` §2). Also: does "Undervalued" still count as Uvalu's own "opinion" under MAR?
3. Position risk ratings (High/Critical) computed from the user's own weights: still descriptive under PER-4?
4. Licensing: EODHD terms for commercial display and derived data (DATA-1/2); a STOXX licence for EURO STOXX 50 index data; Fama-French Data Library terms for a paid service (DATA-6).
5. Consumer Mediation Service contact details: verify on consumentenombudsdienst.be.

## 3. Open placeholders

Find them with `grep -rn "\[TBD" docs/legal/policies`.

| Placeholder | Where | Notes |
| --- | --- | --- |
| `ENTERPRISE NUMBER`, `VAT NUMBER` (not yet registered) | Terms §1, Privacy §1, Conflicts §1, Methodology §11 | Register the eenmanszaak at an enterprise counter (ondernemingsloket) and activate VAT before 1 January 2027; legally required on the site |
| `MODEL_VERSION AT LAUNCH` | Methodology header + change log | Bump `screener_compliant.MODEL_VERSION` with the 10% minimum |
| `EODHD ATTRIBUTION TEXT` | Data sources §2 | Copy verbatim from the contract |
| `_streamlit_user` duration | Privacy §7 | Check in the browser on the production build |

## 4. Implementation requirements

These pages promise behaviour. Each item below must be true in the app before the matching page goes live.

**Linking and display**
- A footer on every screen and on the sign-in/sign-up screens, linking all six pages. The Methodology page is also linked from every signal badge (BDG-2).
- The pages render in all six app languages. They are legal texts: a fluent reviewer translates them (INT-1, INT-4). English stays the reference version (Terms §17).
- Each page shows its version and date. Keep earlier versions retrievable (Terms §15).
- The Methodology page is rendered from `screener_compliant.methodology()` and the `risk_compliant.REF_*` constants, so the numbers can't drift. This file is the reference text and layout. It also shows the live signal distribution (`signal_distribution()`) and the weighting in force.

**Account and subscription (Terms, Privacy)**
- Sign-up limited to EEA countries and age 18+. Store the country of residence.
- Record acceptance of the terms and of the no-advice acknowledgement: text version, date, time.
- Mollie monthly subscription with a 30-day trial. Trial reminder email at least 7 days before the end. Cancel in settings without contacting support, effective end of the month.
- A "Withdraw from contract" function in account settings, with a full refund within 14 days of the first paid day.
- Price-change and terms-change emails 30 days in advance.
- Self-service account deletion: live data removed at once, removed from backups within 35 days (backup rotation must guarantee this), invoices kept 10 years. Data export of the portfolio in a machine-readable format (`backup.export_zip` / Excel export are candidates).

**Security and privacy**
- Log every administrator access to a user's portfolio (Privacy §6).
- Log retention 31 days (`uvalu/logkit/config.py` `retention_days`). If the audit log is stored elsewhere, align its retention.
- Encryption at rest, including Hetzner Storage Box backups.
- Verify the cookie table against the production build. Add nothing non-essential without adding a consent mechanism and updating Privacy §7.

**Data and models**
- Replace yfinance with EODHD and set `DATA_SOURCE` plus the attribution text (wiring checklist §4.9 in `../algorithm-compliance-review.md`).
- **End-of-day prices only:** remove or disable the intraday price auto-refresh (`price_autorefresh`), and show the price date next to every price.
- Raise the shared `min_mos` default from 0% to 10% and bump `MODEL_VERSION`.
- Wire the `*_compliant` modules in (checklist in `../algorithm-compliance-review.md` §4): signal history on the stock page (12 months), timestamps, data flags and model list next to every signal, no analyst-target display.
- Show a holdings notice on a stock page when the founder holds more than 0.5% of the issuer's capital. Today the only content is "none", but the field must exist.

**Offline commitments (no code)**
- Keep the personal trade register for covered shares (Conflicts §4).
- No trading in affected shares from the decision on a model change until 2 trading days after it is live.
- Signed processing agreements (DPAs) with Hetzner, Brevo, Mollie and the accountant.
- A written security-incident procedure (Privacy §6).

## 5. Keeping the pages true

- Change the Methodology page in the same release as any model or threshold change, and add a change-log row.
- Adding a processor, cookie, data source or marketing email requires updating the Privacy notice or Data sources page **before** it goes live.
- Bump the page version and date on every change. Material changes to the Terms or Privacy notice are notified to users 30 days ahead (Terms §15, Privacy §11).
