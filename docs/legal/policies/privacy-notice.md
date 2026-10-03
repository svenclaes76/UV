<!--
Uvalu public legal page. Status: FINAL TEXT, pending counsel review and the [TBD] items listed in README.md.
Only processors, cookies and purposes really in use are listed: this notice must match the implementation.
Decisions: Hetzner (hosting + Storage Box backups), Brevo (service email), Mollie (payments), external accountant,
Google sign-in enabled, no newsletter, no analytics, no error-monitoring service.
Verify the cookie inventory (section 7) in a browser on the production build before publishing.
Requirement IDs: GDPR-1..14, SEC-1..10 of "Uvalu — Legal Requirements for Launch".
-->

# Privacy notice

**Version:** 1.0 · **Effective from:** 1 January 2027

This notice explains which personal data Uvalu collects, why, how long we keep it and what your rights are.

## 1. Who is responsible for your data

The controller is **Sven Claes**, a sole trader (eenmanszaak) trading under the name Uvalu, Pol Heynsstraat 7, 2200 Herentals, Belgium, enterprise number [TBD: ENTERPRISE NUMBER — not yet registered].

Privacy contact: privacy@uvalu.app

We have not appointed a data protection officer, because the law does not require one for our activities.

## 2. What we collect and why

| Data | Purpose | Legal basis (GDPR art. 6) | Kept for |
| --- | --- | --- | --- |
| Email address, password (stored only as a hash), language, country of residence | Creating and securing your account | Contract | Until you delete your account, plus 30 days |
| If you sign in with Google: your name, email address and Google account identifier, as shared by Google | Signing you in without a separate password | Contract | Until you delete your account, plus 30 days |
| Two-step verification data: authenticator secret, backup codes, passkey public keys, trusted devices | Securing your account | Contract | Until you remove them or delete your account |
| Portfolio data you enter: holdings, transactions, dividends, cash entries, watchlists, notes | Providing portfolio and risk features | Contract | Until you delete it or your account, plus 30 days |
| Settings and preferences | Providing the service as you configured it | Contract | Until you delete your account, plus 30 days |
| Subscription plan, payment status, invoices, country evidence for VAT | Billing and accounting | Contract; legal obligation | 10 years after the end of the financial year, as required by Belgian accounting and VAT law |
| Records of your acceptance of the terms and of the no-advice acknowledgement (text version, date, time) | Proof of agreement | Legitimate interest; legal obligation | Duration of the account plus 10 years |
| Security logs: login time, device and browser type, failed logins, administrator access to accounts, and the IP address where our web server records it | Security, fraud prevention, troubleshooting | Legitimate interest | 31 days |
| Support messages and complaints | Answering your questions and complaints | Contract; legitimate interest | 2 years after the case is closed |

We do **not** ask for or store: national register numbers, bank account numbers, payment card numbers, or login details for your broker or bank.

We do not send newsletters or marketing email. We only send emails needed for the service, such as account verification, password resets, trial and billing notices, and notices of changes to these documents.

Your portfolio data shows information about your finances. We treat it as confidential and limit access to it (see section 6).

## 3. No profiling for advice, no automated decisions

Scores, fair values and model signals are calculated from market data and model settings. They are not based on a profile of you. We do not take decisions about you by automated means that have legal or similarly significant effects (GDPR art. 22).

## 4. Who receives your data

We do not sell your data. We share it only with service providers that process it on our instructions, under a written agreement:

| Provider | Role | Location of processing |
| --- | --- | --- |
| Hetzner Online GmbH | Hosting and database | Germany |
| Hetzner Online GmbH (Storage Box) | Encrypted backups | Germany |
| Brevo | Transactional and service email | France |
| Mollie B.V. | Payment processing (also a controller for its own legal obligations) | Netherlands |
| External accountant | Bookkeeping and tax filings (billing data only) | Belgium |

If you choose to sign in with Google, Google (Google Ireland Limited) handles that sign-in as an independent controller under its own privacy policy. We receive only the data listed in section 2.

This list is kept up to date in this notice at [uvalu.app/privacy](https://uvalu.app/privacy). We may also disclose data to authorities where the law requires it.

Market data providers do not receive your personal data or your portfolio.

## 5. Transfers outside the European Economic Area

All data processed by us and our service providers listed above stays within the EEA. If you use Google sign-in, Google may process data outside the EEA under its own responsibility and safeguards.

## 6. How we protect your data

- Encryption in transit and at rest, including backups
- Passwords stored only as salted hashes (bcrypt); two-step verification with an authenticator app and passkeys available
- Access by role: the administrator can open a user's portfolio only when needed for support or security, and each such access is logged
- Payment details are entered on Mollie's pages and never reach our servers
- A documented procedure for security incidents

If a data breach is likely to put you at high risk, we tell you without undue delay.

## 7. Cookies and similar technologies

| Cookie / storage | Purpose | Type | Duration |
| --- | --- | --- | --- |
| `uv_jwt` (cookie and browser storage) | Keeps you logged in | Strictly necessary | 24 hours |
| `uv_td` | Remembers a device you trusted for two-step verification, so you are not asked for a code on it again | Strictly necessary; only set if you tick "Remember this device" | 30 days |
| `_streamlit_xsrf` | Protects forms against misuse | Strictly necessary | Session |
| `_streamlit_user` | Keeps your Google sign-in session | Strictly necessary; only set if you sign in with Google | [TBD: VERIFY DURATION] |
| Browser storage of the app framework | Remembers light or dark mode | Functional | Until you clear your browser data |

Strictly necessary cookies need no consent. We use no other cookies, no analytics and no advertising trackers.

## 8. Your rights

You have the right to:

- **access** your data and receive a copy;
- **correct** data that is wrong;
- **delete** your data. You can delete your account yourself in the settings; live data is removed at once and backups within 35 days. Data we must keep by law, such as invoices, is kept until the legal period ends;
- **export** your portfolio data in a machine-readable format from the settings;
- **object** to processing based on our legitimate interest;
- **restrict** processing in the cases the law provides;
- **withdraw consent** at any time, without affecting earlier processing, where processing is based on consent.

To use these rights, write to privacy@uvalu.app. We answer within one month. We may ask you to confirm your identity through your account email.

## 9. Complaints

If you are not satisfied with our answer, you can complain to the Belgian Data Protection Authority (Gegevensbeschermingsautoriteit / Autorité de protection des données), Drukpersstraat 35, 1000 Brussels, [www.gegevensbeschermingsautoriteit.be](https://www.gegevensbeschermingsautoriteit.be), or to the authority of the EU country where you live.

## 10. Children

Uvalu is for adults. We do not knowingly collect data from anyone under 18.

## 11. Changes to this notice

We may update this notice. For material changes we tell you by email or in the app before they take effect. The version number and date are shown at the top.
