# Briefing: privacy and consumer-law review for Uvalu

*Prepared 13 Oct 2026 by Sven Claes, founder of Uvalu (uvalu.app). For a Belgian privacy and consumer-law lawyer, or a certified DPO working with one.*

## What we ask

A review of our privacy notice and terms of use against GDPR and EU/Belgian consumer law, the GDPR documents we are still missing, and the rules for the subscription checkout before we build it. Please quote a **fixed fee** for the questions in §4 before starting.

## 1. Uvalu in brief

- An online tool for **private investors** in the EEA. It values listed shares and lets users record and analyse their own portfolio. It doesn't execute orders, hold money or securities, or connect to banks or brokers.
- **Operator and controller:** Sven Claes, a natural person in Belgium (Herentals), trading as Uvalu. Not yet registered with KBO/BCE. The founder is the only administrator.
- **Status today:** a **free, invitation-only beta**, for people the founder knows, resident in the EEA, 18+. Beta privacy notice version 1.3, beta terms version 1.0.
- **Planned:** a paid **monthly** subscription through Mollie with a **30-day free trial**. Paid texts version 1.0, target date 1 January 2027.
- **Languages:** English (reference) plus Dutch, French, German, Spanish and Italian. During the beta the legal texts are in English only.

## 2. Data and processors

**Personal data:**

- Account: email, password hash, language, two-step verification data.
- Portfolio data the user enters: holdings, transactions, dividends, cash, watchlists, notes.
- Settings.
- Security logs, kept 31 days.
- Support messages.
- Invitation data: email and name entered by the founder.
- At paid launch also: country of residence, consent records, billing data and Google sign-in.

**What we don't collect:** no national numbers, no bank or card numbers, no broker logins, no analytics, no advertising trackers, no newsletters.

**Cookies:** all strictly necessary (session, trusted device, XSRF), plus a theme preference in browser storage.

**Rights tools:**

- Self-service **account deletion**: live data removed at once, the account's backups at once, migration snapshots after 30 days.
- Self-service **export** to Excel: portfolio, account details and settings.

| Processor | Role | Location | DPA signed? |
|---|---|---|---|
| Hetzner Online GmbH | Hosting, database, encrypted offsite backups (Storage Box) | Germany | [Sven] |
| Mailbox provider for support@, privacy@, security@ and complaints@ | Email | [Sven: not chosen yet] | No |
| Brevo (paid launch) | Transactional email | France | No |
| Mollie B.V. (paid launch) | Payments; also a controller for its own duties | Netherlands | No |
| External accountant (paid launch) | Bookkeeping | Belgium | No |
| Google (paid launch, optional) | Sign-in; independent controller | — | n/a |

Market-data providers receive ticker symbols only, never personal data. The breached-password check sends a 5-character hash prefix only.

## 3. Where we know we have gaps

Found in an internal first pass on 13 Oct 2026:

- **Paperwork not yet written:**
  - record of processing (art. 30)
  - legitimate-interest notes
  - a DPIA screening
  - a breach procedure and breach register
- **Promises in the beta notice that need building or rewording:**
  - Deleting invitation data 30 days after expiry.
  - A record of each administrator access to a user's data. Today only general event logs exist, kept 31 days.
  - Removal from offsite backups within 30 days. The Storage Box rotation is still to be confirmed.
- **The checkout isn't built yet.** No payment code exists, so its design can still follow your advice.

## 4. Questions

**GDPR**

1. Review the beta and paid privacy notices. What is missing, wrong or promised beyond what we do?
2. Please give us a template for the record of processing and the legitimate-interest assessments, or fill them in from §2.
3. **DPIA:** is one required for portfolio data, which is financial but not a special category, given no profiling? Please check against the APD list (decision 01/2019) and give us the conclusion in writing.
4. **Administrator access:** the founder can generate a password reset link for any account and can download backups holding every user's data. What should we log, how long should we keep it, and what should the notice say (L10)?
5. **Roles:** is our external accountant a processor or an independent controller? And is Mollie correctly described as both?
6. **Mailbox provider:** if we choose a US provider, what transfer mechanism and notice changes do we need? Is an EU provider clearly preferable?
7. **Breach procedure:** please give us a short procedure for the 72-hour notification, plus a register template.

**Consumer law (paid launch)**

8. **Free trial and withdrawal.** We give a 14-day withdrawal right from the first paid day, with a full refund. That is more than *Sofatutor* (C-565/22) requires. Is the wording in Terms §6 right? What must be shown when the trial starts?
9. **Order button.** What exact wording do you advise for the sign-up button that starts a trial which converts to a paid plan (art. 8(2) CRD, *Fuhrmann-2* C-249/21)? Does it matter whether Mollie collects the payment mandate at trial start or at conversion?
10. **Withdrawal function.** What must our "Withdraw from contract" function do under art. 11a CRD (Directive 2023/2673) as transposed in Belgium: label, confirmation step, acknowledgement?
11. **Renewal and cancellation.** Our plan is monthly, cancellable at any time in settings, effective at the end of the month, with a reminder 7 days before the trial ends. Does any Belgian rule on tacit renewal, reminders or online cancellation add requirements?
12. **Unfair terms (WER art. VI.82–VI.84).** Please check the liability clause (Terms §12) and the clause on changes to the terms (Terms §15). Is a cap of the amount paid in 12 months, with a €100 minimum, acceptable? Should the reasons for changes be a closed list?
13. **Language (L7).** Must the Terms be available in Dutch and French for Belgian consumers? Does "the English version is the reference" survive?
14. **Pre-contractual information and confirmation.** Please give us a checklist of what the checkout and the confirmation email must contain.

## 5. Facts to confirm before the meeting

| Fact | Answer |
|---|---|
| Accounts in the beta besides the founder's, and their countries | [Sven] |
| Target countries for the paid launch | [Sven] |
| Mailbox provider candidates and their processing locations | [Sven] |
| Storage Box backup rotation period, and whether Hetzner keeps its own snapshots | [Sven] |
| Planned price per month | [Sven] |
| Mollie mandate at trial start or at conversion | [Sven] |

## 6. What we'd like back

- Marked-up beta and paid privacy notices and terms of use.
- A record of processing, legitimate-interest notes and a DPIA decision.
- A breach procedure and register template.
- A DPA checklist per processor.
- A checkout checklist: button wording, trial information, withdrawal function, confirmation email, renewal and cancellation.

**Not in scope:** MiFID II and MAR, data licensing and tax. Those are covered by separate briefs.

## Attachments

Export to PDF with version and date.

1. Privacy notice: beta 1.3 and paid 1.0 ([`policies/beta/privacy-notice.md`](../../legal/policies/beta/privacy-notice.md), [`policies/privacy-notice.md`](../../legal/policies/privacy-notice.md))
2. Terms of use: beta 1.0 and paid 1.0
3. Complaints page (paid and beta versions)
4. Screenshots: invitation acceptance, Settings › Privacy (export and delete account), Settings › Legal documents
5. A one-page data-flow diagram: what data, where it is stored, which processor ([Sven]: to draw)
6. Optional: our internal first-pass [privacy and consumer-law review](../../legal/privacy-consumer-review.md)
