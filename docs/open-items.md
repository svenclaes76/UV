# Open items

One list of what is still open, so nothing has to be rediscovered. Tick an
item off by deleting it (git history keeps it) and add new ones under the
right heading with a date and a trigger: *when* it has to be done.

Last updated: 13 October 2026.

## Legal and compliance

From the legal review of `feature/design-reference-v1-3` (10 October 2026).
The wording fixes from that review are done (`d7637f2`); these need more than
wording.

| # | Item | Risk | Do it before | Who |
| --- | --- | --- | --- | --- |
| L1 | **Record terms acceptance and EEA country** (AU-09 / G30: country, three unticked boxes, text version + timestamp). Until then, keep a manual record per invite: country + an email confirming the invitee read the terms and the no-advice notice. When built, put the country and acceptance rows back in the privacy notice §2 and the admin "Account creation" text. Then show the acceptance dates in Settings › Legal documents (terms, privacy notice) and give the no-personal-advice row its View link back — it is marked "Not available" until then (11 October 2026). | Medium–high | Inviting anyone you don't know personally | Dev |
| L2 | **Market-data licence.** Prices come from Yahoo Finance, whose terms allow personal, non-commercial use only; showing them to other users is redistribution. Move to the licensed provider (EODHD, display licence) or get written permission. | Medium–high | A wider beta | Founder + provider |
| L3 | **Formal opinion on MAR classification** of the signals (art. 3(1)(35) MAR, "expert" status and Delegated Regulation 2016/958 art. 4). Then, optionally, an informal approach to the FSMA through its fintech contact point. | Medium | Paid launch | Belgian financial-regulation lawyer |
| L4 | **KBO / BCE registration** (CEL art. III.49) and a business or domiciliation address instead of the home address on every page. Then set `PRODUCER_ENTERPRISE_NUMBER` in `uvalu/compliance/disclosures.py`. | Medium | First income or public launch; ideally before inviting strangers | Founder + accountant |
| L5 | **Email-hosting provider** in privacy notice §4 is still `[TBD]`. | Medium | Beta opens to others | Founder |
| L6 | **Translations of the UI disclaimers** (nl/fr/de/it/es) were drafted, not legally reviewed (INT-1 / INT-4). | Low–medium | Anyone relies on a non-English disclaimer | Fluent legal reviewer |
| L7 | **Terms: "English version prevails" clause** — check it is there; translate the Terms into at least Dutch and French. | Low (beta) | Paid launch | Founder / lawyer |
| L8 | **Self-service account deletion** — built on `feature/import-export` (11 October 2026): Settings › Privacy › Delete account, beta privacy notice §8 → beta 1.3. Still to confirm: the offsite Storage Box backups rotate within 30 days (the notice promises it). | Low | Publishing beta 1.3 | Founder |
| L9 | **Rebalancing UI** needs its own MiFID II review before it is built: nothing may combine a signal with the user's position into an action ("reduce", "rebalance"). | Medium if built wrongly | Building it | Review |
| L10 | **Privacy notice §6**: one line that the admin can hand out a reset link (and so could take over an account). | Low | Next notice update | Founder |
| L11 | **Paywall launch checklist**: drop the "no income during the free beta" lines (already tied to `BETA`), re-check the conflicts policy, and switch to the paid-launch legal pages. | — | Paid launch | Dev + founder |

Facts the review still needs: how many production accounts exist besides the
founder's and in which countries.

The signal label review also makes L4 more urgent: without a registered
producer identity the MAR disclosures are incomplete. Its L12 ("Neutral" →
"Mid score", "Fails quality screen" → "Screened out"), L13 (Dashboard "Model
signal" column) and L14 (`tests/test_signal_qualifier.py`) are done on
`feature/signal-labels`; the newest translations still need review in Poedit.
Facts the review still needs: target markets (Belgium only or other EU
countries), whether signals will appear in marketing, social media or
emails, and whether any part of Uvalu will be free and public.

From the privacy and consumer-law review (13 October 2026,
[`legal/privacy-consumer-review.md`](legal/privacy-consumer-review.md)). It
also adds to L5 (sign the mailbox provider's DPA and the Hetzner DPA; a US
provider changes privacy notice §5) and L8 (`policies/README.md` §4 says 35
days, the notices say 30; also write the incident procedure and breach
register that privacy notice §6 promises).

| # | Item | Risk | Do it before | Who |
| --- | --- | --- | --- | --- |
| L15 | **GDPR paperwork:** record of processing (art. 30), a short legitimate-interest note per row that relies on it, and a written DPIA screening against the APD list. | Low–medium | Inviting anyone you don't know personally | Founder |
| L16 | **Admin access record:** privacy notice §6 promises each admin access to a user's data is recorded; nothing does that (events only, 31-day retention). Add an access record kept longer, or reword §6. | Medium | Beta opens to others | Dev / founder |
| L17 | **Invite purge:** privacy notice §2 promises invitation data is deleted 30 days after expiry; expired invites stay in the user store. | Low–medium | Next beta notice update | Dev |
| L18 | **Paid checkout:** order-button wording with the price after the trial, conversion date and price shown at sign-up, the art. 11a withdrawal function with confirmation and email acknowledgement, a confirmation email with terms and withdrawal form, Brevo open/click tracking off. | Medium | Paid launch | Dev + lawyer |
| L19 | **Paid-launch text edits:** Terms §12 liability (not for our own errors; restore the "reasonable care" qualifier), Terms §15 closed list of reasons for changes, privacy notice §7/§8/§11 aligned with the beta notice, accountant as controller or processor. | Low–medium | Paid launch | Founder / lawyer |

## Design and code

| # | Item |
| --- | --- |
| D3 | Passkeys and two-factor extensions: deferred (decided 9 October 2026). |

## Product backlog

Parked after v2.0.1 (2 October 2026, extended 5 October); not re-checked
since, so verify before starting.

| # | Item |
| --- | --- |
| P1 | Wide tables at 1024px: values wrap in de/es; idea: horizontal scroll below a per-table minimum width. |
| P2 | Tablet layout (about 640–900px) and phone layout (under 640px): a design project of its own (see `docs/design/visual-review-2026-10-04.md` G13). |
| P3 | First-run tour; texts parked in `uvalu/i18n_planned.py`. |
| P4 | Rebalancing and stress-test texts are translated but not shown anywhere (see L9). |
| P7 | Settings: structured target-allocation editor instead of the text areas; a "View change log" link (needs a change-log page). |
| P9 | Watchlist: empty bordered box while loading (not reproduced; re-check after a cold start). |
| P11 | Paywall / payments (Q4 2026 roadmap); none exists yet. |
