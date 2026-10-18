<!--
Uvalu public legal page — FREE BETA version (decision B4, docs/legal/compliance-implementation-plan.md §0).
Derived from ../privacy-notice.md (the paid-launch version). Only the processing really in use during the beta:
no payments (no Mollie, no billing data, no accountant), no email sending (no Brevo).
Verify the cookie inventory (section 7) in a browser on the beta build before publishing.
Beta-readiness review 5 October 2026: invitation data, mailbox provider ([TBD] in section 4), personal emails
from our own mailbox, contractual-requirement statement (art. 13(2)(e)), market-data requests, uv_jwt browser
storage and the admin-access wording.
9 October 2026 (beta 1.1): password sign-in only in the beta (design reference v1.3) — the Google sign-in
data row, controller paragraph, transfer sentence and `_streamlit_user` cookies removed; the breached-password
check by hash prefix added to section 6 (G36). Passkey wording unchanged (passkeys deferred, not yet live).
10 October 2026 (beta 1.2, legal review): only what the beta really does — passkeys, country of residence and
the acceptance-record row removed (they return with invitation consent, AU-09/G30); account deletion on
request (no self-service control yet); change notices by personal email; the breached-password check
sends no personal data. Effective at once: the changes only correct or remove processing (section 11).
11 October 2026 (beta 1.3): self-service account deletion in Settings › Privacy (open item L8) — live data
removed at once, the account's backups at once, migration snapshots after 30 days; section 8 updated. The
export in Settings now also carries account details and settings. Effective at once: the change only adds a
way to use a right (section 11). Before publishing, confirm the offsite Storage Box backups rotate within
30 days.
14 October 2026 (beta 1.4): the consent step (country of residence and acceptance records, L1), the admin
action record kept 24 months (L16), the per-IP sign-in limit (IP in memory 15 minutes), the reset-link line
(L10). Invite records are now deleted 30 days after expiry (L17), as section 2 already said. Adds processing,
so effective 14 days after notice (section 11): 28 October 2026. Still blocked from publishing to anyone new
until the mailbox provider (section 4, open item L5) is filled in.
Requirement IDs: GDPR-1..14, SEC-1..10 of "Uvalu — Legal Requirements for Launch".
15 October 2026 (still beta 1.4, before it takes effect): `uv_jwt` is kept in the cookie only (SR4); the
browser-storage copy, which nothing read, is no longer written and is removed from browsers that hold one.
Only removes processing (section 11), so no new notice; the section 7 row was narrowed accordingly.
18 October 2026 (beta 1.5, draft): the uvalu.app domain isn't held, so every contact is uvalu.app@gmail.com; that makes Google (Gmail, USA) the mailbox provider (open item L5) — section 4 row, section 5 transfer via the EU–US Data Privacy Framework, and the list's location (no uvalu.app/privacy page). Adds a recipient and a transfer, so effective 14 days after users are told (section 11). Check Google's current DPF listing and sign Google's data processing terms for the mailbox.
-->

# Privacy notice — free beta

**Version:** beta 1.5 · **Effective from:** [14 days after users are told]

This notice explains which personal data Uvalu collects, why, how long we keep it and what your rights are.

## 1. Who is responsible for your data

The controller is **Sven Claes**, trading under the name Uvalu, Pol Heynsstraat 7, 2200 Herentals, Belgium. Registration with the Crossroads Bank for Enterprises: pending.

Privacy contact: uvalu.app@gmail.com

We have not appointed a data protection officer, because the law does not require one for our activities.

## 2. What we collect and why

| Data | Purpose | Legal basis (GDPR art. 6) | Kept for |
| --- | --- | --- | --- |
| Your email address and, if given, your name, entered by the founder to invite you | Sending you an invitation to the beta | Legitimate interest (inviting people we know to test Uvalu) | Until you accept; if you do not, deleted 30 days after the invitation expires |
| Email address, password (stored only as a hash), language | Creating and securing your account | Contract | Until you delete your account, plus 30 days |
| Your country of residence, and the record of what you confirmed when you joined (that you are 18 or older, that you read the terms of use and this notice, and the no-personal-advice acknowledgement), each with the version of the text and the time | Proof of agreement; checking that you may use Uvalu (residents of the European Economic Area, 18 or older) | Legitimate interest | Until you delete your account, plus 30 days |
| Two-step verification data: authenticator secret, backup codes, trusted devices | Securing your account | Contract | Until you remove them or delete your account |
| Portfolio data you enter: holdings, transactions, dividends, cash entries, watchlists, notes | Providing portfolio and risk features | Contract | Until you delete it or your account, plus 30 days |
| Settings and preferences | Providing the service as you configured it | Contract | Until you delete your account, plus 30 days |
| Security logs: login time, device and browser type, failed logins, and the IP address where our web server records it | Security, fraud prevention, troubleshooting | Legitimate interest | 31 days. The IP address of a failed sign-in is also kept in memory for 15 minutes, to limit repeated attempts from one address |
| A record of each administrator action on your account (for example a password reset link, a two-step verification reset, a change of role or status, a deletion or a backup restore), under a pseudonymous identifier, with the time | Accountability for how your account is handled | Legitimate interest; legal obligation | 24 months |
| Support messages and complaints | Answering your questions and complaints | Contract; legitimate interest | 2 years after the case is closed |

We do **not** ask for or store: national register numbers, bank account numbers, payment card numbers, or login details for your broker or bank.

You need to give an email address and a password to have an account. Portfolio data is optional, but the portfolio and risk features need it.

During the beta we send no automated emails: invitations are shared with you directly, and notices appear in the app. We may write to you personally from our own mailbox about your account, for example to announce a change to these documents or the end of the beta. We never send newsletters or marketing email.

Your portfolio data shows information about your finances. We treat it as confidential and limit access to it (see section 6).

## 3. No profiling for advice, no automated decisions

Scores, fair values and model signals are calculated from market data and model settings. They are not based on a profile of you. We do not take decisions about you by automated means that have legal or similarly significant effects (GDPR art. 22).

## 4. Who receives your data

We do not sell your data. We share it only with service providers that process it on our instructions, under a written agreement:

| Provider | Role | Location of processing |
| --- | --- | --- |
| Hetzner Online GmbH | Hosting and database | Germany |
| Hetzner Online GmbH (Storage Box) | Encrypted backups | Germany |
| Google LLC (Gmail) | The mailbox uvalu.app@gmail.com, for support, privacy, security and complaints | United States and other countries (see section 5) |

This list is kept up to date in this notice, in the app under Legal › Privacy notice. We may also disclose data to authorities where the law requires it.

Market data providers (Yahoo Finance, Frankfurter, the Kenneth R. French Data Library) do not receive your personal data. Our server asks them for data on ticker symbols, including those you add yourself, without any link to you or to the size of your positions.

## 5. Transfers outside the European Economic Area

All data processed by us and by Hetzner stays within the EEA. Emails you send to uvalu.app@gmail.com, and our replies, are processed by Google, including in the United States. That transfer relies on Google LLC's certification under the EU–US Data Privacy Framework. Your account and portfolio data are never sent to the mailbox.

## 6. How we protect your data

- Encryption in transit and at rest, including backups
- Passwords stored only as salted hashes (bcrypt); two-step verification with an authenticator app available
- New passwords checked against a public list of breached passwords (Have I Been Pwned): only the first five characters of the password's hash are sent, never the password itself, your email address or anything else that identifies you
- Access by role: the founder, as the only administrator, accesses a user's data only when needed for support, security or a legal obligation. Each administrator action on an account is recorded and kept for 24 months (see section 2)
- If you can't sign in, the administrator can give you a password reset link. Whoever holds such a link can set a new password, so it could be used to take over the account: a link is shown once, works for 30 minutes and is recorded
- A documented procedure for security incidents

If a data breach is likely to put you at high risk, we tell you without undue delay.

## 7. Cookies and similar technologies

| Cookie / storage | Purpose | Type | Duration |
| --- | --- | --- | --- |
| `uv_jwt` | Keeps you logged in | Strictly necessary | 24 hours |
| `uv_td` | Remembers a device you trusted for two-step verification, so you are not asked for a code on it again | Strictly necessary; only set if you tick "Remember this device" | 30 days |
| `_streamlit_xsrf` | Protects forms against misuse | Strictly necessary | Session |
| Browser storage of the app framework | Remembers light or dark mode | Functional | Until you clear your browser data |

Strictly necessary cookies need no consent. We use no other cookies, no analytics and no advertising trackers.

## 8. Your rights

You have the right to:

- **access** your data and receive a copy;
- **correct** data that is wrong;
- **delete** your data. You can delete your account yourself in the settings: your account and data are removed from live systems at once and from backups within 30 days. You can also write to uvalu.app@gmail.com;
- **export** your portfolio data, account details and settings in a machine-readable format (an Excel workbook) from the settings;
- **object** to processing based on our legitimate interest;
- **restrict** processing in the cases the law provides;
- **withdraw consent** at any time, without affecting earlier processing, where processing is based on consent.

To use these rights, write to uvalu.app@gmail.com. We answer within one month. We may ask you to confirm your identity through your account email.

## 9. Complaints

If you are not satisfied with our answer, you can complain to the Belgian Data Protection Authority (Gegevensbeschermingsautoriteit / Autorité de protection des données), Drukpersstraat 35, 1000 Brussels, [www.gegevensbeschermingsautoriteit.be](https://www.gegevensbeschermingsautoriteit.be), or to the authority of the EU country where you live.

## 10. Children

Uvalu is for adults. We do not knowingly collect data from anyone under 18.

## 11. Changes to this notice

We may update this notice. For material changes we tell you in the app and write to you personally at your account address at least 14 days before they take effect, unless the change only corrects this notice, removes processing or is required by law. The version number and date are shown at the top.
