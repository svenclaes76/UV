# Expert Profile: Security Tester (Penetration Tester)

**Project:** Uvalu — stock screening and portfolio tool for solo retail investors
**Priority:** Critical — before launch, and again after major authentication changes

---

## Why Uvalu needs this expert

Uvalu stores user accounts and personal portfolios, offers role-based access (Admin / Analyst / Viewer) and an administrative portal. A breach would expose financial data, trigger GDPR notification duties and damage trust permanently. As a solo developer, Sven needs an independent tester to find what he cannot see in his own code.

## Required expertise

- Professional penetration-testing experience on web applications, with recognised certification (**OSCP, OSWE, GWAPT, CREST** or equivalent)
- Strong knowledge of **OWASP Top 10 and OWASP ASVS**
- Authentication security: password storage (Argon2/bcrypt), **two-factor authentication (TOTP)**, **passkeys / WebAuthn (FIDO2)**, account recovery, brute-force and credential-stuffing protection
- **Session handling**: cookie flags, session fixation, token expiry, logout and revocation, CSRF
- Experience with **Python / Streamlit** deployments and their specific risks (server-side state, websocket sessions, hosting configuration)
- Cloud and infrastructure review: TLS, secrets management, database exposure, **encryption at rest and in transit**, **backup security and restore testing**
- Ability to write a clear report a solo developer can act on

## Scope of review

1. **Authentication:** signup, login, password reset, 2FA enrolment and recovery codes, passkey registration and login, rate limiting
2. **Authorisation:** RBAC enforcement, horizontal access (user A seeing user B's portfolio), admin portal isolation
3. **Session management:** session lifetime, fixation, concurrent sessions, logout across devices
4. **Input handling:** injection (SQL, formula injection in CSV exports), XSS in custom HTML/CSS rendered through `uvalu/components.py` and `st.markdown(unsafe_allow_html=True)`
5. **Encryption:** TLS configuration, encryption of portfolio data at rest, key management
6. **Secrets:** API keys (market-data provider, Mollie, Brevo) and the app's `AUTH_SECRET` / `ENCRYPTION_KEY`: storage and rotation
7. **Backups:** encryption, access, retention (Hetzner), and an actual restore test
8. **Logging and monitoring:** detection of suspicious logins, audit trail for admin actions
9. **Dependencies:** known vulnerabilities in Python packages

## Expected deliverables

- Pentest report with findings rated by severity (e.g. CVSS) and reproduction steps
- Prioritised remediation list
- Retest after fixes, with confirmation letter (useful for users and partners)
- Short security baseline checklist for future releases

## Material to prepare

- Test environment with representative data (no real user data)
- Test accounts for each role, including admin
- Architecture diagram: hosting, database, third-party services
- Authentication design (libraries, 2FA, passkey implementation)
- Scope and rules-of-engagement agreement

## Questions to ask when selecting

- Have you tested WebAuthn/passkey implementations?
- Have you tested Streamlit or similar Python web apps?
- Is a retest included in the price?

## Red flags

- Delivers only an automated scanner report
- No signed rules of engagement or NDA
- No experience with authentication flows beyond passwords

## Where to find

- Belgian security consultancies offering web-app pentests for start-ups
- Independent certified testers (OSCP/OSWE) via professional networks
- Bug-bounty platforms for later, ongoing testing once the app is live
