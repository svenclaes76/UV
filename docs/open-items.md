# Open items

One list of what is still open, so nothing has to be rediscovered. Tick an
item off by deleting it (git history keeps it) and add new ones under the
right heading with a date and a trigger: *when* it has to be done.

Last updated: 17 October 2026.

The items whose trigger is "inviting anyone you don't know personally" are put in order in
[before-strangers-plan.md](before-strangers-plan.md).

## Legal and compliance

From the legal review of `feature/design-reference-v1-3` (10 October 2026).
The wording fixes from that review are done (`d7637f2`); these need more than
wording.

| # | Item | Risk | Do it before | Who |
| --- | --- | --- | --- | --- |
| L1 | **Terms acceptance and EEA country — built** (14 October 2026, `feature/phase5-records`): the invitation starts with a consent step (country of residence, three unticked statements), stored with text versions and times; Settings › Legal documents shows them. Still to do: review the 13 new strings (legal texts) in Poedit, and have the privacy lawyer check the wording. | Medium–high | Inviting anyone you don't know personally | Founder |
| L2 | **Market-data licence.** Prices come from Yahoo Finance, whose terms allow personal, non-commercial use only; showing them to other users is redistribution. Move to the licensed provider (EODHD, display licence) or get written permission. | Medium–high | A wider beta | Founder + provider |
| L3 | **Formal opinion on MAR classification** of the signals (art. 3(1)(35) MAR, "expert" status and Delegated Regulation 2016/958 art. 4). Then, optionally, an informal approach to the FSMA through its fintech contact point. | Medium | Paid launch | Belgian financial-regulation lawyer |
| L4 | **KBO / BCE registration** (CEL art. III.49) and a business or domiciliation address instead of the home address on every page. Then set `PRODUCER_ENTERPRISE_NUMBER` in `uvalu/compliance/disclosures.py`. | Medium | First income or public launch; ideally before inviting strangers | Founder + accountant |
| L5 | **Email-hosting provider** in privacy notice §4 is still `[TBD]`. | Medium | Beta opens to others | Founder |
| L6 | **Translations of the UI disclaimers** (nl/fr/de/it/es) were drafted, not legally reviewed (INT-1 / INT-4). | Low–medium | Anyone relies on a non-English disclaimer | Fluent legal reviewer |
| L7 | **Terms: "English version prevails" clause** — check it is there; translate the Terms into at least Dutch and French. | Low (beta) | Paid launch | Founder / lawyer |
| L8 | **Self-service account deletion** — built on `feature/import-export` (11 October 2026): Settings › Privacy › Delete account, beta privacy notice §8 → beta 1.3. The 30 days now hold by design: `deploy/offsite-backup.sh` prunes offsite archives after 29 days, and the incident procedure and breach register are written (`docs/incident-procedure.md`, 13 October 2026). Still to do: set up the Storage Box with its automatic snapshots off (`docs/deployment.md` step 7). | Low | Server set-up | Founder |
| L9 | **Rebalancing UI** needs its own MiFID II review before it is built: nothing may combine a signal with the user's position into an action ("reduce", "rebalance"). | Medium if built wrongly | Building it | Review |
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
provider changes privacy notice §5) and L8 (the 35/30-day mismatch and the
incident procedure, both done 13 October 2026).

Phase 5 (14 October 2026, `feature/phase5-records`): L15 drafts in `docs/legal/gdpr/` (record of processing, legitimate-interest notes, DPIA screening: no DPIA needed for the beta), L16 admin action record (`uvalu/compliance/admin_access.py`, 24 months), L17 invitation clean-up, L10 (reset-link line) and beta privacy notice 1.4 (effective 28 October 2026) are done; git history keeps their rows. The lawyer still reviews the GDPR drafts.

| # | Item | Risk | Do it before | Who |
| --- | --- | --- | --- | --- |
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
| L29 | **stockanalysis.com as a source** (exchange expansion plan, 17 October 2026): the ticker lists are scraped from it, but it isn't named on the Data sources page. Check its terms of use, and list it as a source or replace it (EODHD's symbol lists). | Medium | Release 2 of the exchange expansion | Founder |
| L30 | **Withholding defaults per country** ([exchange-expansion-plan.md](exchange-expansion-plan.md) §5b, P11): tax advisor checks the statutory rates and the EPV tax rule for offshore registrations; this is the TAX-7 review for the new feature. | Medium | Release 2 of the exchange expansion | Accountant |
| L31 | **Add to the L20 question list:** display of LSE, Nasdaq Nordic & Baltic, BME, Euronext Athens/Dublin/Lisbon/Oslo, Wiener Börse and GPW data; index constituent lists and index names (STOXX, FTSE Russell, Euronext, Nasdaq, Deutsche Börse, SIX, BME, GPW). | Medium–high | Sending L20 | Founder |

## Valuation model

From the valuation model review (13 October 2026,
[`valuation-model-review.md`](valuation-model-review.md)), on the 13 October
signal snapshot. These move signals: bump `MODEL_VERSION` and respect the
founder's trading blackout.

V1 and V2 shipped in model M2 (14 October 2026, `feature/model-m2`); git
history keeps their rows. V3 shipped in model M3 (14 October 2026,
`feature/model-m3`). V4 shipped in model M4 (14 October 2026,
`feature/model-m4`): no Undervalued above a 3× model spread or a 50% margin;
the 3× limit flags 29% of stocks, worth checking with the valuation expert.

| # | Item | Do it before |
| --- | --- | --- |
| V5 | **Veto calibration** after V1–V2: revenue decline threshold, retained-earnings rule on a sample. | Paid launch |
| V6 | **Methodology page:** the models' conservative level (median MoS −33%), euro rate for non-euro stocks, the universe definition. | With V1–V4 |

## Signal stability, data and risk

From the quant and data review (13 October 2026,
[`quant-review.md`](quant-review.md)), on the signal history of 4–13 October. Q2 shipped
in model M2 (14 October 2026).

| # | Item | Do it before |
| --- | --- | --- |
| Q1 | **Re-measure the signal flicker after a week of M2.** Hysteresis (2 points), carried-forward inputs and `changed_inputs` shipped in M2 (merged 14 October 2026); replayed on 4–13 October they halve the changes (842 → 437). How: count `signal_change` records in `data/compliance/signal_history.jsonl` from 14 to 21 October (changes per day, stocks with 3+ changes, the `changed_inputs` that drive them) against the 4–13 October baseline of 805 changes on 242 stocks; check the `data_quality.summary` / `data_quality.alert` log lines. Then decide whether the daily build (S4) is still needed before the EODHD switch. | 21 October 2026 |
| Q4 | **Risk-band calibration:** run ~8 reference portfolios, adjust sub-score mappings, publish the reference points. | Paid launch |
| Q5 | **Small-cap betas:** weekly or Dimson-adjusted returns for illiquid holdings. | Paid launch |
| Q6 | **Methodology wording:** VaR window limits, dividend-adjusted prices, the stability rule, no backtests on restated data. | With Q1–Q4 |

## Security

From the security review (13 October 2026,
[`security-review.md`](security-review.md)). A code review, not a
penetration test. SR1, SR3 and SR5 were fixed on 13 October 2026
(`feature/security-quick-wins`), SR7 on 14 October 2026
(`feature/sr7-small-fixes`); git history keeps their rows.

| # | Item | Do it before |
| --- | --- | --- |
| SR2 | **Production deployment baseline:** written and in the repo (13 October 2026): `deploy/` (Caddyfile with HTTPS and headers, systemd service, offsite backup job), `docs/deployment.md` (firewall, SSH, unprivileged user, `.env` permissions), per-IP sign-in limit in the app. Still to do: create the server and apply it step by step, then switch the CSP from report-only to enforcing. | Inviting anyone you don't know personally |
| SR4 | **Session token, rest:** cookie flags and the escaping test (13 October 2026), and the token in the cookie only, no localStorage copy (15 October 2026, spike result in `docs/security-review.md` #3). Still open: a CSP at the reverse proxy (with SR2). Later, optional: an HttpOnly cookie set by a small endpoint in front of Streamlit. | Inviting anyone you don't know personally |
| SR6 | **Keys and restores:** offline copy of `.env`, the borg passphrase and the exported borg key; written rotation procedures for both secrets; the restore test (procedure and log in `docs/deployment.md` §9) done once and dated. | Restore test: with the server set-up; rotation: paid launch |

## Usability

From the UX walkthrough and research plan (13 October 2026,
[`ux-research-plan.md`](ux-research-plan.md)). The plan for testing with real
users is in the same file. UX2–UX4 done (14 October 2026,
`feature/ux2-ux4`); git history keeps their rows.

| # | Item | Do it before |
| --- | --- | --- |
| UX1 | **Signal next to the user's own position — interim fix done** (14 October 2026, `feature/ux1-signal-position`): the Risk page's last column is now "Position risk" (the position's own rating, no signal), and the stock preview shows the stock's metrics with the signal and the user's shares, value and P&L in a separate "Your position" section below the records divider. Still open: lawyer #1's view on both screens (with L9, L13), then adjust if needed. | Lawyer's answer |
| UX5 | **Run the user study** (6–8 Belgian/Dutch self-directed investors, plan and screener in the doc) after V1, V2 and Q1, on a warmed staging server. | Paid launch |

## Translations

From the financial terminology review (13 October 2026,
[`translation-review.md`](translation-review.md)). Label changes are legal-text
changes: run them through the fuzzy-review loop; L6 stays open. TR1 and TR3
(glossary, "Mid score") done 14 October 2026; git history keeps their rows.
The glossary marks the TR2 decisions as open.

| # | Item | Do it before |
| --- | --- | --- |
| TR2 | **Decisions:** one fair-value concept across languages (nl says intrinsic value, fr/es/it use the IFRS accounting term), with lawyer #1; *vous* instead of *tu* for French legal texts (exception to G-04). | Anyone uses French, Spanish or Italian |
| TR4 | **In-context review** by native financial translators, per language, in the running app. | Paid launch |

## Accessibility

From the accessibility review (13 October 2026,
[`accessibility-review.md`](accessibility-review.md)). Uvalu is exempt from the
EAA as a micro-enterprise; these are for real users and for later. AC1 and AC4
done 14 October 2026 (`feature/ac1-ac4-landmarks`), AC3 and the button
half of AC2 the same day (`feature/ac2-ac3-row-buttons`), the rest of AC2
(tables) on 15 October 2026 (`feature/ac2-table-semantics`), AC5 too
(`feature/ac5-button-contrast`), AC6 on 15 October 2026
(`feature/ac6-chart-summaries`); git history keeps
their rows. The Admin sidebar is a navigation landmark since 15 October 2026.

| # | Item | Do it before |
| --- | --- | --- |
| AC7 | **Specialist audit** with screen readers (NVDA, VoiceOver), keyboard only and 200% zoom. The statement is published (15 October 2026, `docs/legal/policies/accessibility.md`); update its gaps list and date whenever an item here closes. | Paid launch |

## Exchange expansion

Plan: [exchange-expansion-plan.md](exchange-expansion-plan.md) (decisions in §0, order in §7). Reviews: [UX](ux-review-exchange-expansion.md), [architecture](architecture-review-exchange-expansion.md), [model](model-review-exchange-expansion.md). Not started as of 17 October 2026.

| # | Item | Do it before |
| --- | --- | --- |
| EX1 | **Release 1 released as v2026.10.9** (17 October 2026): Swiss prices in CHF, official exchange names, ticker-list cache, fetch back-off, exchange registry. Delete this line once release 2 starts. | Done |
| EX7 | **Holdings are never converted to EUR** (plan §10 P12): Dashboard, Portfolio, Risk and the drawer add native-currency values to the EUR total. No effect on a euro-only portfolio; must be fixed before any non-euro holding is likely. | Release 2 |
| EX2 | **Risk-free rate per currency** (D33): choose the official 10-year yield series per currency and who updates it each quarter. | EX-W5b |
| EX3 | **Shadow build** for a week after 21 October (Q1 done), as a check before release 2: per-market signal mix, data quality, pooled vs. regional medians. | Release 2 |
| EX4 | **Oslo Børs official branding:** confirm the name to show (D10). | EX-W6 |
| EX5 | **Model M5** (rate per currency, liquidity in EUR): bump `MODEL_VERSION`, methodology change log, release-note explanation. | Release 2 |
| EX6 | **Index snapshot refresh** after each quarterly index review (third Friday of March, June, September, December), with `tools/refresh_index_members.py`. | Each quarter after release 2 |

## Design and code

| # | Item |
| --- | --- |
| D3 | Passkeys and two-factor extensions: deferred (decided 9 October 2026). |

## Product backlog

Parked after v2.0.1 (2 October 2026, extended 5 October); not re-checked
since, so verify before starting.

| # | Item |
| --- | --- |
| P2 | Tablet layout (about 640–900px) and phone layout (under 640px): a design project of its own (see `docs/design/visual-review-2026-10-04.md` G13). |
| P3 | First-run tour; texts parked in `uvalu/i18n_planned.py`. |
| P4 | Rebalancing and stress-test texts are translated but not shown anywhere (see L9). |
| P7 | Settings: structured target-allocation editor instead of the text areas; a "View change log" link (needs a change-log page). |
| P11 | Paywall / payments (Q4 2026 roadmap); none exists yet. |
