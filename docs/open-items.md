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

From the data-licensing review (13 October 2026,
[`legal/data-licensing-review.md`](legal/data-licensing-review.md)). It also
sets L2's trigger: no one beyond personal contacts while prices come from
Yahoo (same trigger as L1).

| # | Item | Risk | Do it before | Who |
| --- | --- | --- | --- | --- |
| L20 | **EODHD in writing:** send the question list (review appendix): display to paying users, derived data, price charts, exchange fees, retention incl. the 12-month signal history, exports, attribution, price per user tier. Then the contract. | Medium–high | Choosing a plan; M2 | Founder |
| L21 | **Benchmark licence:** confirm whether computing beta on EURO STOXX 50 needs a STOXX licence, or switch to an ETF benchmark (methodology update). | Medium | Paid launch | Founder |
| L22 | **French Data Library:** ask permission to use the factor data in a paid service; file the reply (DATA-6). | Low | Paid launch | Founder |
| L23 | **Direct Yahoo call:** the Analysis 1-year price chart calls `yf.Ticker().history` itself; route it through the provider module with C7/S3. | Low | M2 | Dev |

From the tax and business set-up review (13 October 2026,
[`legal/tax-business-review.md`](legal/tax-business-review.md)). Figures in it
must be confirmed by an ITAA accountant.

| # | Item | Risk | Do it before | Who |
| --- | --- | --- | --- | --- |
| L24 | **Employment contract and receipts:** check exclusivity, non-compete and IP clauses (BIZ-10); start keeping business receipts. | Medium | Now | Founder |
| L25 | **Registration and liability shield:** KBO registration in bijberoep (with L4), notarial declaration that the family home can't be seized, quote for professional liability + cyber insurance (BIZ-8). | Medium–high | Inviting anyone you don't know personally | Founder + accountant / notary / broker |
| L26 | **VAT and billing set-up:** Mollie + OSS or a merchant of record; small-business exemption or normal VAT; prices incl. VAT per country; country evidence in the checkout. Consumer-only, or Peppol-ready for business subscribers. | Medium | Building the checkout (L18) | Founder + accountant |
| L27 | **Sole trader vs BV break-even** with the real salary and expected profit; the trigger may come before v3's revenue gate. | Medium | Paid launch | Accountant |
| L28 | **Yearly tax-rate review:** check the dividend withholding rules in the app every January and bump `TAX_RULES_REVIEWED`. | Low | Every January | Founder |

## Valuation model

From the valuation model review (13 October 2026,
[`valuation-model-review.md`](valuation-model-review.md)), on the 13 October
signal snapshot. These move signals: bump `MODEL_VERSION` and respect the
founder's trading blackout.

| # | Item | Do it before |
| --- | --- | --- |
| V1 | **Currency mismatch:** ~40% of rows quote in another currency than they report in (Investor AB on Milan: book value in SEK, price in EUR; 28 of 128 Undervalued). Store the reporting currency, convert per-share fundamentals with `fx.py`; until then flag the rows and keep them out of medians and Undervalued. | Inviting anyone you don't know personally |
| V2 | **Universe:** ~1,000 US secondary listings on Milan/Frankfurt, 179 dormant cross-listings vetoed for zero volume; 43% Screened out. One line per company, no dormant lines, decide on non-European companies. | With V1 |
| V3 | **Normalised EPS** for P/E fair value and Graham; growth tilt from history; flag trailing P/E < 4 (11 Undervalued have P/E < 5). | Paid launch |
| V4 | **Model dispersion:** median max/min 3.3×, 328 stocks > 10×. Range instead of a point and no Undervalued above ~3×; plausibility flag for MoS > 50%. | Paid launch |
| V5 | **Veto calibration** after V1–V2: revenue decline threshold, retained-earnings rule on a sample. | Paid launch |
| V6 | **Methodology page:** the models' conservative level (median MoS −33%), euro rate for non-euro stocks, the universe definition. | With V1–V4 |

## Signal stability, data and risk

From the quant and data review (13 October 2026,
[`quant-review.md`](quant-review.md)), on the signal history of 4–13 October.

| # | Item | Do it before |
| --- | --- | --- |
| Q1 | **Signal flicker:** 805 changes on 242 stocks in 9 days (SRAIL.SW 21× at score 39.9/40.0; vetoes toggling within minutes). Daily build from one snapshot (bring S4 forward), hysteresis at band edges, carry the last known value for missing veto inputs, log which input changed. | Inviting anyone you don't know personally |
| Q2 | **Data-quality monitoring** per build: missing rates per field, rows changed, vetoes added/dropped, alerts on thresholds. | With Q1 |
| Q3 | **Stress scenarios** use S&P 500 drawdowns and dates; use the EURO STOXX 50's own (dot-com and 2008 are never replayed with 10 years of history). | Paid launch |
| Q4 | **Risk-band calibration:** run ~8 reference portfolios, adjust sub-score mappings, publish the reference points. | Paid launch |
| Q5 | **Small-cap betas:** weekly or Dimson-adjusted returns for illiquid holdings. | Paid launch |
| Q6 | **Methodology wording:** VaR window limits, dividend-adjusted prices, the stability rule, no backtests on restated data. | With Q1–Q4 |

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
