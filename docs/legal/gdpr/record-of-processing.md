# Record of processing activities (GDPR art. 30)

**Controller:** Sven Claes, trading as Uvalu, Pol Heynsstraat 7, 2200 Herentals, Belgium. KBO/BCE number: pending (open item L4). Contact: privacy@uvalu.app. No data protection officer (not required: no large-scale processing of special categories, no systematic monitoring).

**Version:** 1.0 · **Kept up to date by:** the founder, whenever the privacy notice changes · **Drafted:** 14 October 2026 (open item L15), for review by the privacy lawyer (expert brief 02).

Art. 30(5) exempts organisations under 250 staff only when processing is occasional. Uvalu's processing is continuous, so this record is required. It describes the **free beta** (beta privacy notice 1.4). The paid launch adds billing (Mollie, accountant) and service email (Brevo); add those rows before it starts.

## Processing activities

| # | Activity | Purpose | Data subjects | Personal data | Legal basis | Recipients / processors | Third-country transfer | Retention | Security measures |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Invitations | Inviting people the founder knows to test the beta | Invitees | Email, name if given, invitation token and expiry, who invited | Art. 6(1)(f) legitimate interest (see [legitimate-interest notes](legitimate-interest.md) §1) | Hetzner (hosting) | None | Until accepted; otherwise deleted 30 days after expiry (`auth.purge_expired_invites`) | Encrypted user store; random 24-byte token, 7-day expiry |
| 2 | Accounts and sign-in | Creating and securing accounts | Users | Email, password hash (bcrypt), language, role, status, two-step verification secret and backup-code hashes, trusted devices, session records, last active | Art. 6(1)(b) contract | Hetzner (hosting, backups) | None | Account lifetime + 30 days (backups) | Encrypted store; bcrypt; TOTP; per-account and per-IP sign-in limits; SameSite/Secure cookies |
| 3 | Consent record | Proof that the user accepted the terms, the privacy notice and the no-advice acknowledgement, is 18+ and lives in the EEA | Users | Country of residence, accepted text versions, timestamps | Art. 6(1)(f) legitimate interest (proof of agreement) and 6(1)(c) where a legal obligation applies | Hetzner | None | Account lifetime + 10 years once paid plans exist; in the beta, account lifetime + 30 days | Encrypted store |
| 4 | Portfolio and risk features | Providing the service the user asked for | Users | Holdings, transactions, dividends, cash entries, watchlists, notes, targets, settings | Art. 6(1)(b) contract | Hetzner | None | Until the user deletes it or the account, + 30 days (backups) | Per-file Fernet encryption at rest; per-user folders; admin access recorded |
| 5 | Security logs | Security, fraud prevention, troubleshooting | Users, visitors of the sign-in page | Pseudonymous user id, sign-in events, device/browser type, IP address (web server log; in memory for 15 minutes for the per-IP sign-in limit) | Art. 6(1)(f) legitimate interest (see notes §2) | Hetzner | None | 31 days (`logkit` retention; Caddy access log 31 days) | Log redaction of secrets; access only by the founder |
| 6 | Admin access record | Accountability for administrator actions on a user's account or data | Users, administrators | Pseudonymous ids of administrator and user, action, time | Art. 6(1)(c) and (f) (accountability, art. 5(2); see notes §3) | Hetzner | None | 24 months (`admin_access.ADMIN_ACCESS_KEEP_DAYS`) | Pseudonymous ids only; append-only file |
| 7 | Support and complaints | Answering questions and complaints | Users, people who write in | Email, message contents | Art. 6(1)(b) contract; (f) legitimate interest for non-users | Mailbox provider (to be chosen, open item L5) | Depends on the provider; none if EU-based | 2 years after the case is closed | Mailbox account with two-step verification |
| 8 | Backups | Restoring service after loss | Users | Copies of activities 2–4 and 6 | Same as the activity copied | Hetzner Storage Box (encrypted, borg) | None | Offsite: 29 days (the offsite backup job (removed with the production server on 24 Oct 2026; git `648559b`)); local migration snapshots: 30 days | Two layers of encryption; keys kept offline |
| 9 | Breach register | Art. 33(5) documentation | People affected by an incident | Description of the incident and its effects | Art. 6(1)(c) legal obligation | None | None | 5 years after the incident is closed | Kept offline, outside the repository |

Market-data providers (Yahoo Finance, Frankfurter/ECB, the French Data Library) receive ticker symbols only, never personal data. The breached-password check sends a 5-character hash prefix that identifies no one.

## Processors

| Processor | Service | Location | Agreement (DPA) |
|---|---|---|---|
| Hetzner Online GmbH | Cloud server, Storage Box | Germany | [Sven: sign in the Hetzner console; date] |
| Mailbox provider | Mailboxes for support@, privacy@, security@, complaints@ | [Sven: open item L5] | [Sven: date] |

## Review

Review this record when the privacy notice changes, when a processor or a new kind of data is added, and at least once a year.
