# DPIA screening (GDPR art. 35)

*Drafted 14 October 2026 (open item L15), for review by the privacy lawyer.* This screening decides whether a full data protection impact assessment (DPIA) is required for the free beta. Repeat it before the paid launch and whenever a new kind of processing is added.

## Conclusion

**No DPIA is required for the free beta.** None of the art. 35(3) cases applies, and at most one criterion from the EDPB guidelines (WP248 rev.01) is met, where two usually trigger a DPIA. The reasons are below. Revisit at the paid launch: more users, payment data and service email may change the count.

## Art. 35(3) cases

| Case | Applies? | Why |
|---|---|---|
| (a) Systematic, extensive evaluation of personal aspects, by automated processing including profiling, with legal or similarly significant effects | No | Scores and signals concern listed shares, not people. They are the same for every user (rules PER-1 to PER-5), and no decision about a user is automated (privacy notice §3). |
| (b) Large-scale processing of special categories (art. 9) or criminal data (art. 10) | No | No special-category or criminal data. Portfolio data is financial, which isn't an art. 9 category. |
| (c) Systematic monitoring of a publicly accessible area on a large scale | No | Nothing of the kind. |

## EDPB criteria (WP248 rev.01)

| # | Criterion | Met? | Notes |
|---|---|---|---|
| 1 | Evaluation or scoring | No | The scoring is of shares, not of people. |
| 2 | Automated decision with legal or similar effect | No | None. |
| 3 | Systematic monitoring | No | Security logs only, 31 days. |
| 4 | Sensitive data or data of a highly personal nature | **Partly** | Portfolio holdings reveal something about a person's finances. Counted as met, to be careful. |
| 5 | Large scale | No | An invitation-only beta with a handful of users. |
| 6 | Matching or combining datasets | No | Portfolio data isn't combined with other sources about the person. |
| 7 | Vulnerable data subjects | No | Adults (18+) who chose to use an investing tool. |
| 8 | Innovative use of new technology | No | A conventional web application. |
| 9 | Processing that prevents people from exercising a right or using a service | No | Self-service export and deletion exist. |

One criterion (4) out of nine is met.

## Belgian list

The Belgian Data Protection Authority keeps its own list of processing that always needs a DPIA (decision 01/2019). **[Lawyer: confirm against the current list.]** None of the categories known to us (large-scale health, biometric, location or monitoring data; large-scale data about vulnerable people; systematic evaluation with significant effects) applies.

## Measures that keep the risk low

- Encryption at rest per file and in backups, with keys kept offline.
- Bcrypt passwords, two-step verification, per-account and per-IP sign-in limits.
- No profiling, no marketing, no analytics, no third-party trackers.
- Data minimisation: no bank, card, national or broker data.
- Self-service export and deletion, and a 24-month admin access record.
- A written incident procedure (`docs/incident-procedure.md`).
