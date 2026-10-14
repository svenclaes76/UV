# Legitimate-interest notes (GDPR art. 6(1)(f), art. 5(2))

*Drafted 14 October 2026 (open item L15), for review by the privacy lawyer.* One short balancing test per processing activity that relies on legitimate interest ([record of processing](record-of-processing.md)). Each answers three questions: is the interest legitimate, is the processing necessary for it, and do the person's interests override it.

## 1. Invitations (record activity 1)

- **Interest:** inviting a small group of people the founder knows to test the beta before it opens. Legitimate: testing a service with people who agreed to be approached is an ordinary business interest.
- **Necessity:** an invitation can't be sent without an email address. The name is optional. Nothing else is stored.
- **Balance:** the people are known to the founder and expect the invitation. The data is minimal and not used for anything else. Unaccepted invitations are deleted 30 days after they expire. **The interest prevails.**

## 2. Security logs (record activity 5)

- **Interest:** keeping accounts and data secure, detecting attacks (password guessing, account takeover) and fixing faults. Legitimate, and also part of the security duty in art. 32.
- **Necessity:** sign-in events, device type and IP address are what an investigation needs. Users appear under a pseudonymous id. IP addresses for the per-IP sign-in limit live in memory for 15 minutes only.
- **Balance:** users reasonably expect a service to log sign-ins for security. Retention is short (31 days), and only the founder has access. Logs aren't used for profiling or marketing. **The interest prevails.**

## 3. Admin access record (record activity 6)

- **Interest:** being able to show which administrator action touched which account and when. That is accountability (art. 5(2)), it answers a user who asks, and privacy notice §6 promises it.
- **Necessity:** only pseudonymous ids, the action and the time are stored, with no data content.
- **Balance:** the record protects users more than it affects them. Retention is 24 months, long enough to answer a complaint or an inquiry from the data protection authority. **The interest prevails.**

## 4. Consent record (record activity 3)

- **Interest:** proving what a user accepted (terms, privacy notice, no-advice acknowledgement, age, EEA residence) in case of a dispute or an inquiry from the financial regulator.
- **Necessity:** the country, the text versions and the times are the minimum proof.
- **Balance:** expected by every user who ticks the boxes, and stored with the account. **The interest prevails.** Once paid plans exist, the 10-year retention also rests on accounting and consumer-law obligations (art. 6(1)(c)).

## 5. Support and complaints from people without an account (record activity 7)

- **Interest:** answering a question or complaint someone sent.
- **Necessity:** the email and the message are needed to answer.
- **Balance:** the person wrote in to get an answer. Kept 2 years after the case is closed, to handle a follow-up or a dispute. **The interest prevails.**
