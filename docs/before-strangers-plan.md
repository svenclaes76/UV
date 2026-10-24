# Plan: before inviting anyone you don't know personally

*13 Oct 2026.* One ordered plan for every open item whose trigger is "inviting anyone you don't know personally" or "beta opens to others". It covers items from the ten first-pass expert reviews and the legal items, all listed in [open-items.md](open-items.md). Tick items off there; this file only sets the order.

**Today:** the beta has the founder's account only. Everything below is about being ready before the first invitation to someone outside your own circle.

## How the order was chosen

1. **Start the long waits first.** Registration, notary, insurance, the vendor's written answers and the lawyer's opinion take weeks and need almost no development time. Starting them on day one overlaps them with the code work.
2. **Small security fixes before the server faces the internet.** They're hours of work each, and the deployment baseline only makes sense once they're in.
3. **Fix the data before the build that snapshots it.** The universe (V2) shrinks the currency problem (V1). Both should be right before the daily build (Q1) starts writing the signal history that MAR may require. All three move signals, so they ship together as **one model version (M2)** with **one trading blackout**.
4. **Design changes wait for the lawyer's answer,** so they're done once.
5. **One privacy notice update at the end** collects every notice change, so users get one notice instead of four.

## Phase 0: Start the long waits (week 1, founder, no code)

| Step | Item | What | Lead time |
|---|---|---|---|
| 0.1 | L24 | Read the employment contract: exclusivity, non-compete, IP. Start a folder of business receipts. | 1 hour |
| 0.2 | L25, L4 | Register with KBO in bijberoep (enterprise counter + social insurance fund). Choose a business or domiciliation address. Book the notary for the declaration that the family home can't be seized. Request a professional liability + cyber insurance quote, telling the broker exactly what the signals are. | 1–3 weeks |
| 0.3 | L5 | Choose the mailbox provider, preferably processing data in the EU. Sign its processing agreement and Hetzner's. | 1 week |
| 0.4 | L2, L20 | Send EODHD the question list from the [data-licensing review](legal/data-licensing-review.md). Until a licence is signed, the rule stands: **no one beyond personal contacts while prices come from Yahoo.** That makes L2 a gate for the whole plan, not a step. | 2–6 weeks |
| 0.5 | UX1, L3 | Send [briefing pack 01](experts/briefings/01-financial-regulation-brief.md) to a Belgian financial-regulation lawyer. Add UX1 (signal next to own position, in the drawer and the Risk "Flag" column) to its questions. | 3–6 weeks |

## Phase 1: Security quick wins (week 1–2, dev, ~2–3 days)

Each fix gets its own test.

| Step | Item | What |
|---|---|---|
| 1.1 | SR1 | Two-factor attempt limit: lock after about 5 bad codes, don't reset on a correct password while a challenge is pending, reject reuse of an accepted time step. The same for backup codes. |
| 1.2 | SR3 | One message for every login failure, and a dummy bcrypt check for unknown emails. |
| 1.3 | SR5 | Remove the `.env` export from Admin and document the SSH copy instead. Take an offline copy of `.env` now (part of SR6). |
| 1.4 | SR4 (part) | `Secure; SameSite=Strict` on `uv_jwt` and `uv_td`. Add an XSS regression test that feeds `<img onerror>` through company names, notes and display names. |

## Phase 2: Production baseline (week 2–3, dev + founder, ~2 days)

**Parked on 24 October 2026:** no beta is planned soon, so the Hetzner setup was removed from the repo (git history, commit `648559b`). The steps below wait until a beta is planned; see open-items.md, "Parked: production server".

| Step | Item | What |
|---|---|---|
| 2.1 | SR2 | Reverse proxy with a public certificate, HTTP→HTTPS + HSTS, CSP and `frame-ancestors 'none'` (completes SR4), Streamlit on localhost only, firewall (443 + SSH keys), unprivileged user, `.env` permissions, per-IP login rate limit, automatic security updates. Write it down in `docs/deployment.md`. |
| 2.2 | L8 | Confirm the Storage Box rotation is 30 days or less, and fix the 30/35-day mismatch in `policies/README.md`. Write the one-page incident procedure and breach register that privacy notice §6 promises. |
| 2.3 | SR6 (part) | One dated restore of an offsite backup onto a fresh machine. It proves the backups and the `.env` copy work together. |

## Phase 3: Data correctness and signal stability (week 3–6, dev, the biggest block)

Ship as **model version M2** in one release:

- Record the decision with `settings_audit.record_planned_change()`, which starts the founder's trading blackout.
- Add a methodology change-log row.
- The blackout ends 2 trading days after M2 is live.

| Step | Item | What | Why in this order |
|---|---|---|---|
| 3.1 | V2 | One line per company (primary or most liquid listing). Drop dormant lines from `fetch_tickers.py`. Decide whether non-European companies stay in, and if so say so on the methodology page. | Removes ~1,000 cross-listings, so V1 has less to fix, Q1 less to stabilise, and the data licence less to cover |
| 3.2 | V1 | Store the reporting currency per ticker and convert per-share fundamentals with `fx.py`. Flag and exclude what can't be converted. | The fair values, medians and ranks behind every signal depend on it |
| 3.3 | Q1 | A daily signal build from one snapshot (S4, brought forward). Hysteresis at band edges. Carry the last known value forward for missing veto inputs. Log which input changed. | Starts the signal history on correct, stable data |
| 3.4 | Q2 | Per-build data-quality summary with alerts: missing rates, rows changed, vetoes added or dropped. | Catches regressions in 3.1–3.3 from the first build |
| 3.5 | Check | Re-run the snapshot checks from the [valuation review](valuation-model-review.md) and the [quant review](quant-review.md). Targets: no currency-mismatched rows in Undervalued; Screened out well below 43%; signal changes per day down by an order of magnitude. | Proof before inviting anyone |

## Phase 4: Signal next to own position (after the lawyer answers)

| Step | Item | What |
|---|---|---|
| 4.1 | UX1 | Apply the lawyer's answer: separate "Your position" from the model signal in the stock drawer, and rename or clean the Risk page "Flag" column. Extend `tests/test_signal_qualifier.py` to cover both. |

If the lawyer is slow, the safe interim step is to remove the signal from the Risk "Flag" column and move the drawer's position block below a "Your position" heading. That costs a few hours.

## Phase 5: Records, paperwork and one notice update (week 5–7)

| Step | Item | What |
|---|---|---|
| 5.1 | L1 | Build the invitation consent step: country (EEA), three unticked boxes, text version and timestamp stored. Then show acceptance dates in Settings › Legal documents. Until it's built, keep the manual record per invite. |
| 5.2 | L16 | Admin access record kept longer than 31 days, or reword privacy notice §6 to what happens. |
| 5.3 | L17 | Purge invitation records 30 days after expiry. |
| 5.4 | L15 | Record of processing, legitimate-interest notes and a DPIA screening. Paperwork, half a day. |
| 5.5 | L5, L10, L16, L17 | **One beta privacy notice update (beta 1.4)** with the mailbox provider, the reset-link line, the admin-access wording and the invitation data handling. Effective at once where it only corrects or removes; otherwise with 14 days' notice. |
| 5.6 | L4 | Once KBO registration is through: enterprise number and business address on every page (`PRODUCER_ENTERPRISE_NUMBER`). |

## Phase 6: Go / no-go

Invite someone you don't know personally only when every line is true:

- [ ] **L2:** an EODHD licence covering display to other users is signed and live. *Or* the invitee is a personal contact. *(Gate.)*
- [ ] L4/L25: KBO number and business address on every page. The home declaration is signed. The insurance is in force.
- [ ] L5/L8: the mailbox provider is chosen and the processing agreements are signed. Backup rotation is confirmed and the incident procedure is written.
- [ ] SR1–SR5 are merged, and the deployment baseline is applied and documented.
- [ ] M2 is live (V1, V2, Q1, Q2) and the snapshot checks pass.
- [ ] UX1 is resolved per the lawyer, or the interim step is in place.
- [ ] L1 consent flow is live. L15 paperwork is done. Beta privacy notice 1.4 is published.
- [ ] A release is tagged with all of the above, with public release notes.

## Rough effort

| Phase | Dev time | Founder time | Calendar |
|---|---|---|---|
| 0 | — | ~1 day spread out | Weeks 1–6 (waiting) |
| 1 | 2–3 days | — | Weeks 1–2 |
| 2 | 2 days | ½ day | Weeks 2–3 |
| 3 | 1–2 weeks | decisions on V2 | Weeks 3–6 |
| 4 | ½ day | — | When the lawyer answers |
| 5 | 2–3 days | ½ day | Weeks 5–7 |

That's about **6–8 weeks of calendar time** at the v2 side-project pace. The pace is set by the EODHD answer and the lawyer, not by the code.
