# Security incident procedure

What to do when something goes wrong with security or personal data. Privacy notice §6 promises "a documented procedure for security incidents"; this is it (open item L8, [privacy and consumer-law review](legal/privacy-consumer-review.md) §1).

**Who:** Sven Claes, as controller and the only administrator. **Keep this page short enough to follow under stress.**

## What counts

- **Personal data breach** (GDPR art. 4(12)): personal data lost, changed, disclosed or accessed without authorisation, by accident or on purpose. Examples:
  - someone signs in to another person's account
  - a backup or `.env` leaks
  - the server is compromised
  - a bug shows one user's portfolio to another
  - data is deleted with no backup
- **Other security incident:** no personal data involved. Examples: the site is defaced, the server runs a cryptominer, or the domain is hijacked. Follow the same steps; the notification duties don't apply.

## Steps

The 72-hour clock starts when you are **reasonably certain** a breach happened, not when it started.

### 1. Contain (first hour)

- **Stop the leak:**
  - take the app offline: `sudo systemctl stop uvalu`, or stop Caddy
  - revoke access: suspend the affected accounts in Admin › Users
  - rotate exposed credentials
- **If `.env` or the server is compromised,** treat every session and every encrypted file as exposed:
  - stop the app
  - set up a new server from [deployment.md](deployment.md)
  - plan the secret rotation (SR6) before restarting
- **Keep the evidence:**
  - don't wipe the server before copying the logs: `logs/`, `/var/log/caddy/`, `journalctl -u uvalu`
  - write down what you see, with times

### 2. Assess (within 24 hours)

Answer these and write them in the register:

- What happened, and when (start, discovery)?
- Which data: accounts, portfolios, settings, security logs? Was it encrypted, and was the key exposed too?
- How many people, and in which countries?
- What could it lead to for them: financial loss, identity fraud, embarrassment, phishing?

Then rate the **risk to the people affected**:

| Risk | Typical case | Notify the APD? | Notify the people? |
|---|---|---|---|
| Unlikely | Encrypted data leaked, key safe; a bug fixed before anyone saw data | No, but record it | No |
| Risk | Portfolio data or emails seen by someone else | **Yes, within 72 h** | Not required |
| High risk | Many accounts exposed; passwords or two-factor secrets with the key; data used for fraud | **Yes, within 72 h** | **Yes, without undue delay** |

### 3. Notify (within 72 hours of becoming aware)

- **Belgian Data Protection Authority (APD/GBA):**
  - use the online breach notification form on gegevensbeschermingsautoriteit.be
  - if not everything is known yet, notify what you know and complete it later (art. 33(4))
  - a late notification must say why it's late
- **The people affected,** if high risk (art. 34):
  - email them personally from the support mailbox
  - in plain language, say what happened, what data, the likely consequences, what you've done, what they should do (for example, change a reused password), and who to contact
- **Others, where relevant:**
  - the professional liability / cyber insurer (L25), as the policy requires
  - Hetzner, if their infrastructure is involved
  - the police, for a crime
  - the lawyer, if unsure about any of this

### 4. Recover and learn (within 2 weeks)

- Fix the cause, and add a test or check so it can't recur unnoticed.
- Restore from backups if needed ([deployment.md](deployment.md) §9 explains how).
- Add an open item for anything that needs more work, and update the register entry with the outcome.

## Register

Art. 33(5) GDPR: **every** personal data breach is recorded, including the ones not notified, with the facts, the effects and the measures taken.

**Keep the filled-in register outside this repository**, with the offline secrets (it can itself hold personal data). Use this layout:

| Field | Entry |
|---|---|
| Number | 2026-01 |
| Discovered (date, time) | |
| Happened (from–to, if known) | |
| What happened | |
| Data concerned | |
| People concerned (number, countries) | |
| Likely consequences | |
| Risk rating and why | unlikely / risk / high |
| Containment and fix | |
| APD notified | no / yes: date, reference |
| People notified | no / yes: date, how |
| Follow-up items | |
| Closed | date |

## Contacts

| Who | How |
|---|---|
| Belgian Data Protection Authority | gegevensbeschermingsautoriteit.be: breach notification form; Drukpersstraat 35, 1000 Brussels |
| Hetzner support | Hetzner Cloud Console › Support; abuse reports per their website |
| Insurer | [Sven: policy number and claims contact, once L25 is done] |
| Lawyer | [Sven: once engaged, from the briefing packs] |

Review this page once a year, and after every incident.
