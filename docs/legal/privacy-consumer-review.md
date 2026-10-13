# Privacy and consumer-law review

13 Oct 2026 · First-pass review with the legal counsel persona ([`docs/experts/legal-counsel-persona.md`](../experts/legal-counsel-persona.md)), scoped by expert profile [02](../experts/02-privacy-consumer-law-lawyer.md). It does not replace a review by a licensed Belgian privacy and consumer lawyer.

Texts reviewed: the beta privacy notice (beta 1.3) and beta terms (beta 1.0) in [`policies/beta/`](policies/beta/), and the paid-launch privacy notice and terms (1.0) in [`policies/`](policies/). Checked against the code on master (`62dd178`).

## Conclusion

- **Beta privacy: low–medium.** The design is privacy-friendly. There is no tracking, no analytics, no marketing email and no automated decisions. All processing stays in the EEA, and deletion and export are self-service. The risk is not the design. It is **promises in the notice that the app or the paperwork doesn't keep yet** (§1). A notice that says more than you do is a transparency breach (GDPR art. 5(1)(a), art. 12–13). It also weakens trust in the rest of the notice.
- **Beta terms: low.** The beta is free and by invitation. The Consumer Rights Directive mostly applies only where the consumer pays a price. The Digital Content Directive doesn't apply either, because the personal data is processed only to supply the service (art. 3(1) DCD).
- **Paid launch: medium.** The terms are well above the average draft. The risk is in the **checkout flow, which isn't built yet**. The free trial that converts automatically, the order button and the withdrawal function all have specific rules that changed recently (§3).

Each point below is marked as settled law, interpretation, or unclear.

## 1. Beta privacy notice: promises to make true

| # | Notice says | What exists | Risk |
|---|---|---|---|
| a | §2: invitation data deleted 30 days after the invitation expires | Invites expire after 7 days (`auth._INVITE_TTL_DAYS`). The user record stays in the store, and nothing purges it. | Low–medium |
| b | §6: the administrator "records each such access" to a user's data | Admin actions are logged as events (`logkit.data_mutation`), with 31-day retention. Nothing records "I opened user X's data, why". The admin can also download backups that hold every user's data, and generate a reset link that takes over an account (L10). | Medium |
| c | §6: "a documented procedure for security incidents" | Not in the repo. | Medium |
| d | §8: removed from backups within 30 days | Live data, the account's backups and migration snapshots are handled (`account.delete_account`). The offsite Storage Box rotation is not in the repo and is unconfirmed (L8). [`policies/README.md`](policies/README.md) §4 says **35** days, but both notices say 30. | Medium until confirmed |
| e | §4: mailbox provider `[TBD]` (L5) | Not chosen. | Medium: see below |

**Settled law.** Art. 33 GDPR requires a notification to the Belgian Data Protection Authority (APD) within 72 hours of becoming aware of a breach, unless it is unlikely to result in a risk. Art. 33(5) requires **every** breach to be documented, including ones not notified. A one-page procedure plus a breach register fixes (c).

**Settled law.** The mailbox provider is a processor (art. 28) for support@, privacy@, security@ and complaints@. The choice affects §5: a US provider such as Google Workspace or Microsoft 365 makes "all data stays within the EEA" untrue. Then §5 needs the transfer mechanism (EU–US Data Privacy Framework or standard contractual clauses). An EU provider keeps §5 as it is. The notice can't be published with a `[TBD]` in it.

**Recommendation for (b).** Two options:

- Keep the promise and make it real: an "admin access" event with the user, the reason and the time, kept longer than 31 days (it is accountability evidence, art. 5(2)). A manual register in a file works too while you are the only admin.
- Or reword §6 to what happens: "Access is limited to the founder as the only administrator. Administrator actions on accounts are logged." Rewording is cheaper. Keeping the promise is better evidence if a user ever complains.

## 2. Paperwork the notice doesn't mention but the law requires

- **Record of processing activities (art. 30). Settled in practice.** The exemption for organisations under 250 staff (art. 30(5)) doesn't apply when processing is "not occasional". Uvalu processes account and portfolio data continuously. The record is one table, and the §2 table of the notice is 80% of it.
- **Legitimate-interest assessments. Interpretation.** Three rows rely on legitimate interest: invitations, security logs, support. A short written balancing test per row is expected under art. 5(2). Half a page in total.
- **DPIA (art. 35). Unclear, probably not required.** Portfolio data is financial data, not a special category (art. 9). There is no profiling and no automated decision (§3 of the notice is right), and the beta is not large scale. Check the APD's list of processing that always needs a DPIA (decision 01/2019), write down the conclusion, and repeat the check at paid launch. A written "no DPIA needed, because…" is the deliverable.
- **Processing agreements (art. 28). Settled.** Signed DPAs with Hetzner (available in the Hetzner account console) and the mailbox provider before the beta. Add Brevo and Mollie before the paid launch, plus the accountant (see §4).

## 3. Paid launch: checkout and subscription

The paid terms already choose a 14-day withdrawal right from the first paid day, a full refund, a 7-day trial reminder, cancellation in settings, and 30 days' notice of price changes. Each of these is at or above the legal minimum. What is still open is how the checkout presents it.

**Withdrawal right and the free trial. Settled (CJEU C-565/22, *Sofatutor*, 5 October 2023).** When a free trial converts automatically to a paid subscription, the consumer has a withdrawal right only once, at the start of the trial. That holds if the trader informed them clearly, explicitly and transparently that the trial converts and what it will cost. If not, a new right starts at conversion. Uvalu's choice, a right from the first paid day, is more generous and avoids the question. Keep it. Terms §6 states it correctly.

**The order button. Settled, applied by interpretation.** Art. 8(2) of the Consumer Rights Directive (transposed in WER Book VI) requires the button that places an order with an obligation to pay to say so: "order with obligation to pay" or an equally unambiguous phrase. The CJEU held that the button's own wording must make the obligation clear (C-249/21, *Fuhrmann-2*, 7 April 2022). With a trial that converts automatically, the sign-up click is the order. "Start free trial" alone is the risky wording. "Start 30-day free trial, then €X per month" is safer, with the conversion date and price stated next to the button.

**Withdrawal function. Settled for the directive; check the Belgian transposition.** Directive (EU) 2023/2673 added art. 11a to the Consumer Rights Directive, which applies from 19 June 2026. Contracts concluded through an online interface need a clearly labelled withdrawal function ("withdraw from contract here" or similar), a confirmation step, and an acknowledgement on a durable medium (email) without undue delay. Terms §6 already promises a "Withdraw from contract" function. It is now a legal requirement, not only a nice feature, so build it into the checkout work and not after it.

**Confirmation on a durable medium. Settled (art. 8(7) CRD).** After sign-up, send an email with the terms, the withdrawal information and the model form. Paid launch needs Brevo for this, which the paid privacy notice already lists.

**Tacit renewal and cancellation. Unclear in the details.** A monthly contract of indefinite length that can be cancelled at any time, effective at the end of the month, is the low-risk model. Ask the lawyer whether any recent Belgian rule on renewal reminders or an online cancellation button applies to it. Terms §7 (cancel in settings, without contacting support) probably already meets it.

## 4. Paid-launch texts: wording

**Terms §12, liability. Interpretation; medium–low.** "We are not liable for investment losses … including decisions based on outputs of Uvalu" also covers losses caused by Uvalu's own error, such as a bug in a fair value. That is close to the essential obligation that WER art. VI.83, 13° forbids limiting. A court would set that part aside, not the whole clause. Narrow it: "… unless the loss results from our failure to provide the service as described in these terms." Also restore the qualifier the beta terms already have: third-party data "as long as we have passed it on with reasonable care".

**Terms §15, changes. Interpretation; low–medium.** WER art. VI.83, 1° blacklists unilateral changes without a valid reason *stated in the contract*. "For valid reasons, such as …" is an open list. Make it closed: changes in the law, in our providers' terms, security, or a new or changed feature, always with notice and a right to cancel.

**Paid privacy notice: alignment with the beta notice.** Low risk, but these are inconsistencies a reviewer will spot:

- §7 says `uv_jwt` lasts 24 hours. The beta notice correctly adds the browser storage, which can hold a sign-in for up to 7 days.
- §8 export covers "portfolio data". Since beta 1.3 the export also carries account details and settings.
- §11 says "before they take effect". Terms §15 promises 30 days. Use 30 days in both.
- The accountant is listed as a processor. A Belgian certified accountant usually acts as an independent controller, because of their own professional duties. Confirm it with the accountant (expert #4) and move the row if so.

**Brevo. Settled direction (EDPB guidelines 2/2023 on art. 5(3) ePrivacy).** Open and click tracking in emails is a tracking technology that needs consent. Transactional email doesn't need it. Switch tracking off in the Brevo account before the first email goes out. The notice then stays true ("no analytics").

## 5. What is already right

These need no change and shouldn't be reworked:

- The data table in §2 with purpose, legal basis and retention per row, and the art. 13(2)(e) statement on which data is required.
- No profiling and no automated decisions (§3). This also supports the MiFID II position (rules PER-1 to PER-5).
- The Have I Been Pwned check: a 5-character hash prefix is not personal data.
- The cookie table: all strictly necessary, plus a theme preference the user sets. A user-interface preference falls under the consent exemption (WP29 Opinion 04/2012), so no banner is needed.
- Self-service deletion and export (art. 17, 20), the right to complain to the APD or the user's own authority, and 18+ only.
- Beta terms §2: a beta account never turns into a paid plan without express agreement. This keeps the beta outside the subscription rules.

## Recommended changes, in order of value

1. **Before inviting anyone else:**
   - Choose the mailbox provider and sign its DPA, and the Hetzner DPA (L5).
   - Confirm the Storage Box rotation and fix the 30/35-day mismatch (L8).
   - Write the incident procedure and breach register.
   - Make the admin-access promise true, or reword it (L16).
2. **Also before the beta, paperwork only:** the record of processing, the legitimate-interest notes and the DPIA screening (L15).
3. **Before the beta notice is next republished:** purge invite records 30 days after expiry, or change the promise (L17). Add L10 in the same update.
4. **Paid-launch checkout design:** button wording, trial disclosure, the art. 11a withdrawal function, the confirmation email, Brevo tracking off (L18).
5. **Paid-launch text edits:** liability and changes clauses, and the alignment points in §4 (L19).

## Facts the review still needs

- How many accounts exist besides the founder's, and in which countries. The beta is EEA-only. Is anyone outside Belgium?
- The mailbox provider candidates and where they process data.
- Whether the Storage Box sync copies the already-encrypted files, and how long Hetzner keeps its own snapshots of it.
- Whether Mollie will collect a payment mandate when the trial starts or when it converts. That decides which click is the order button.
