# Legal compliance implementation plan

Oct 4, 2026 · status: proposal, for review by Sven

This plan takes Uvalu from today's state to a paid public launch that meets *Uvalu — Legal Requirements for Launch* (Oct 2, 2026). It covers four tracks: external work, project structure, the algorithms and data, and the new UI design.

**Free beta first (decision, Oct 4, 2026).** The first goal is a free beta, not the paid launch. The beta needs **M1** (compliant engine and legal UI) and **M3** (accounts and consent), adapted as in §0. **M2** (licensed data, daily build) and **M4** (billing, paid launch) are postponed. §0 says what that means legally; §1–§8 stay the full plan, so the later milestones are ready when they come back.

**Inputs**

| Source | What it contributes |
| --- | --- |
| *Uvalu — Legal Requirements for Launch* (OneDrive `Desktop\legal`) | Requirement IDs (PER, REC, BDG, DIS, SUB, TOU, GDPR, SEC, DATA, TAX, BIZ, INT) |
| [`algorithm-compliance-review.md`](algorithm-compliance-review.md) | Findings 1–25 and the wiring checklist (§4) for the compliant algorithm copies |
| [`policies/`](policies/) | The six public legal pages and their implementation checklist (`policies/README.md`) |
| Design handoff `Uvalu Legal-handoff.zip` (Claude Design, Oct 3, 2026) | `Uvalu.dc.html` = target UI with legal changes; `Uvalu (pre-legal).dc.html` = baseline; `Uvalu (legal v1).dc.html` = superseded iteration. `Admin` and `Language & Region` carry no legal changes. |

**Where we are**

- Done:
  - compliant scoring and risk algorithms, **swapped in place** of `screener.py` and `risk.py` and wired into the app (M1 step 1, Oct 4, 2026; status in [`algorithm-compliance-review.md`](algorithm-compliance-review.md) §4);
  - signal history, settings audit and founder disclosure, in `uvalu/compliance/` and wired into the universe build and the shared-settings save;
  - final text of the six legal pages (pending counsel and `[TBD]` values).
- Not started:
  - most of the legal UI (M1 Track D); step 1 already put the new labels, the BDG-2 tooltip and the provenance line on the badges;
  - public sign-up with consent records;
  - billing (no payment code exists);
  - self-service data export and account deletion;
  - the licensed data provider;
  - every external item (entity, contracts, counsel).

---

## 0. Free beta

### Scope

| In the beta | Postponed |
| --- | --- |
| **M1** in full: compliant engine, legal UI on every screen, Methodology & help, legal pages, guards | **M2**: EODHD, Stage 1 split (S3), daily build job (S4) |
| **M3**, adapted: invite acceptance with stored consent (instead of public sign-up), data export, account deletion, security checks, GDPR paperwork | **M4**: checkout, Mollie, subscription, withdrawal, invoices, billing emails, VAT |
| C8 moved forward from M2: a signal and its price come from the same snapshot (see B3) | Public sign-up page, country gating at sign-up |

### What still applies to a free beta

Being free and invite-only doesn't switch the rules off. Testers are real people entering real portfolio data, and the badges are still recommendations under MAR, so these all apply:

- **Perimeter (PER-1–7).** Investment advice doesn't need payment to be regulated; the design rules apply in full.
- **MAR set (REC, BDG).** Art. 3(1)(34)–(35) covers recommendations "intended for distribution channels or for the public". Whether a small invited group counts as "the public" is interpretation **[Counsel]**, so comply anyway.
- **GDPR, all of it.** This is why M3 comes before the beta.
- **Disclaimers and acknowledgement** (DIS-1–3, DIS-6), and the tax labelling (TAX-1–6) for the dividend withholding figures.
- **Conflicts and the trade register** (REC-8, REC-9).

What does **not** apply while nobody pays: SUB-1–10, BIZ-2 (VAT), BIZ-4 (invoices), BIZ-5 (Mollie), SEC-7.

### Beta-specific items

| # | Item | Why | Req. |
| --- | --- | --- | --- |
| B1 | **Invite-only**, through the existing admin invite (`auth.invite_user`). No public sign-up page, no marketing. Invite people you know, resident in the EEA. | Keeps the group closed and small; strengthens the "not the public" argument; limits data redistribution. | INT-5/6/7, DIS-5 |
| B2 | **Data still comes from Yahoo Finance.** Free and invite-only lowers the risk, but showing Yahoo data to other people is still redistribution under terms that only allow personal use. **Risk: medium.** Mitigations: (1) name the source honestly; (2) no bulk export (M1 already removes it); (3) keep the group small; (4) sign EODHD before the beta grows beyond people you know. Alternative: bring only C7 (the EODHD provider) forward, without the daily build. | Contract law, not regulation, but it's a cut-off and claims risk. | DATA-1/2/5 |
| B3 | **Prices are delayed intraday quotes, not end of day.** Label every price "delayed · as of <time>", not "end-of-day". Remove `apply_live_mos`, so the margin of safety shown next to a badge comes from the same price the badge used. The live price may still appear separately, with its own time. | REC-4 accuracy; DATA-3 allows delayed prices when they are labelled. | REC-4, DATA-3 |
| B4 | **Beta versions of the legal pages.** The six pages describe the paid launch on EODHD. In the beta they must describe what is actually true. | A legal text that doesn't match reality is a misleading practice (WER VI.97) and breaks GDPR art. 13. | TOU-1, GDPR-1, REC-3 |
| B5 | ~~**Languages: EN and NL only for testers.**~~ **Lifted Oct 4 2026: all six languages enabled for testers.** The app strings are translated in FR, DE, IT and ES and were reviewed by the founder alone in Poedit, without the second reviewer this item first asked for (founder's decision). The beta legal pages exist in EN and NL only; the other four languages show the English reference version with a notice. A fluent review of FR, DE, IT and ES is still needed before the paid launch (INT-4, see M4). | INT-1, INT-4 | INT-1/4 |
| B6 | **Producer identity without an entity.** Show the founder's name, address and contact, and "not supervised by the FSMA". The requirements accept a sole trader for a closed free beta. Ask the accountant whether a free beta already needs a KBO registration; until then the enterprise number line reads "registration pending". | REC-1, BIZ-3 | REC-1, BIZ-1 |
| B7 | **Beta banner and terms:** "Free beta: test version. Features and data can change, and the beta can end at any time." | Sets expectations; supports the liability clause. | TOU-2, TOU-4 |

**B4 in detail (beta texts).** Keep the launch versions in `docs/legal/policies/` and add `docs/legal/policies/beta/`:

| Page | Beta changes |
| --- | --- |
| Terms of use | Remove §5 plans and payment, §6 withdrawal, the subscription part of §7, and the withdrawal form annex. Add: free beta, invite-only, no availability promise, can end at any time with notice, data export before it ends. Liability: no payment, so a lower cap is reasonable **[Counsel]**. |
| Privacy notice | Processors actually used in the beta: Hetzner, Brevo (only if invite emails go through it), Google (sign-in, own controller). Remove Mollie, the accountant and billing data. Keep everything else. |
| Data sources | Yahoo Finance via yfinance: delayed quotes, fundamentals refreshed about every 24 h; ECB rates via Frankfurter; Fama-French. Say that the source changes before a paid launch. |
| Methodology | Update frequency as built: fundamentals about every 24 h, delayed prices with their time. No "end-of-day" or "22:00 CET" until M2. List the models that actually run (D3). |
| Conflicts of interest | Unchanged (§5 "Our only income is subscription fees" → "Uvalu has no income during the free beta"). |
| Complaints | Unchanged. The Consumer Mediation Service reference stays. |

### External items needed before the beta

From Track A, only these block the beta:

1. **Counsel, limited round:** perimeter (PER), the MAR set and badge labels (D1), beta Terms. Full Terms and Privacy review can wait for the paid launch.
2. **Accountant:** does a free beta need KBO registration (B6)?
3. **DPAs** with Hetzner, and with Brevo if used; record of processing; breach procedure (GDPR-3, -4, -9).
4. **Fama-French terms** checked for display to third parties (DATA-6).
5. **Trade register** started (REC-9).

### Beta go/no-go

- [ ] M1 shipped: compliant engine wired in, badges with tooltip and provenance, footer, legal pages, Methodology & help, risk page describe-only
- [ ] M3 (beta version) shipped: invite acceptance with the three consent boxes stored, data export, account deletion, MFA for admins, cross-user access test
- [ ] Beta legal pages (B4) published in EN and NL; FR/DE/IT/ES show the English reference version (B5 lifted: all six languages enabled)
- [ ] Prices labelled "delayed" with their time; signal and price from the same snapshot (B3)
- [ ] Beta banner (B7); producer identity (B6)
- [ ] Limited counsel round done; DPAs signed; trade register running
- [ ] Perimeter memo written and reviewed (PER-9)
- [ ] Decision on B2 recorded: Yahoo with mitigations, or EODHD first

---

## 1. Decisions needed before building

The design and the code disagree in several places. Each one must be settled once, then both sides follow it. The recommendation is listed first.

| # | Topic | Design says | Code / policies say | Recommendation |
| --- | --- | --- | --- | --- |
| D1 | **Badge labels** | BDG-1 literal: Undervalued · Near fair value · Overvalued · Fails quality screen | Undervalued · Neutral · Low score · Fails quality screen · No signal | Code's labels, or score-based labels throughout (High / Mid / Low score). "Overvalued" is false for a stock 30% below fair value with a low score (REC-2, WER VI.97). **[Counsel]** to confirm. Update the design to match. |
| D2 | **Who sets model settings** | "Your model settings": discount rate and terminal growth sliders in Settings; sensitivity table on each stock | Shared, admin-only settings (founder decision, Oct 4: no per-user thresholds) | Keep them shared. Users see the settings read-only, and the sliders only show for the admin. The sensitivity table is display-only, computed on the shared model, and never changes a badge. |
| D3 | **Models listed** | Graham, P/E, EPV, DDM, **DCF, EV/EBIT**; "Analyst target replaced by EV/EBIT" | Graham, P/E, EPV, DDM single + multi-stage, P/B and FCF fallbacks; no DCF, no EV/EBIT | The UI and methodology list only the models the code runs (REC-5). Treat DCF and EV/EBIT as a separate future feature. Discount rate and terminal growth are not settings today; RFR + ERP and `DDM_STABLE_GROWTH` are constants. |
| D4 | **History retention** | "Every badge change kept 24 months" | `RETENTION_DAYS = 366` | 24 months kept, 12 shown (REC-7 needs 12 or more) |
| D5 | **Time horizon** | "3–5 years" | `SIGNAL_HORIZON`: "multi-year" | "3–5 years" in both places (REC-6) |
| D6 | **Free trial** | Checkout charges at once; no trial | Terms §5: 30-day free trial with a reminder 7 days before | Decide on one. With a trial: consent at trial start, a reminder email, and "Order and pay" before the trial (SUB-9). Without: remove the trial from the Terms. |
| D7 | **Email domain** | `hello@`, `privacy@uvalu.eu` | `support@`, `privacy@`, `security@`, `complaints@uvalu.app` | One domain everywhere (BIZ-3) |
| D8 | **Deletion from backups** | "within 35 days" | Privacy notice: "plus 30 days" | One figure, set by the actual backup rotation (GDPR-7, GDPR-8) |
| D9 | **Founder positions** | Hard-coded "none held" | Founder holds covered shares; any-size disclosure | Driven by data (`founder_holds`), never fixed text (REC-8) |
| D10 | **Fundamentals source** | "Company filings" | `data-sources.md`: EODHD | Name the real provider (REC-3, DATA-4) |
| D11 | **Legal entity** | `Uvalu [legal form]` | Policies: sole trader (eenmanszaak) | Requirements doc: a sole trader is fine for a closed free beta, a BV is recommended for the paid launch (BIZ). Decide with an accountant. It fills every `[TBD]` in pages, footer and checkout. |
| D12 | **Model version shown** | "Model v2.3" | `MODEL_VERSION = "2.0.1-legal.1"` | A model version independent of the app version (e.g. `M1`, `M2`, …), bumped on any change that moves a score. Shown in the UI, the methodology change log and the signal log. |

### Decided (Oct 4, 2026)

Sven accepted the recommendations. Where the recommendation left a choice, the choice is:

| # | Decision |
| --- | --- |
| D1 | Labels: **Undervalued · Neutral · Low score · Fails quality screen · No signal**. "Undervalued" additionally requires a margin of safety of at least **10%**, enforced in code as a floor the shared setting cannot go below. **[Counsel]** in the limited round. |
| D2 | Model settings stay shared. Non-admins see them read-only; only the admin sees the sliders. No new discount-rate or terminal-growth settings. The sensitivity table is display-only. |
| D3 | The UI and methodology list only the models the code runs. |
| D4 | Signal history kept 24 months; stock pages show 12. |
| D5 | Horizon "3–5 years", in `SIGNAL_HORIZON` and the UI. |
| D6 | Trial: decided with M4. |
| D7 | Email domain **uvalu.app** everywhere (the legal pages already use it). |
| D8 | Backups purged within **30 days** of deletion, matching the privacy notice; the backup rotation must be set to deliver this. |
| D9 | Founder line driven by `founder_holds`. |
| D10 | Beta: **Yahoo Finance** named as the source (B2). EODHD with M2. |
| D11 | Beta: sole trader. BV or not: decided before M4. |
| D12 | Model version independent of the app version, starting at **M1**. |
| B2 | Beta runs on **Yahoo Finance**, with the mitigations in §0. |

---

## 2. Track A: external work (critical path)

These take the longest and gate the paid launch. Start them now, in parallel with the code.

| Item | Req. | Gates |
| --- | --- | --- |
| Entity choice and registration (KBO/BCE), VAT number, One Stop Shop | BIZ-1, BIZ-2, BIZ-11 | M4 (first payment) |
| Assign code, brand and domain to the entity in writing | BIZ-6 | M4 |
| Employment contract check (side activity, IP) | BIZ-10 | M4 |
| EODHD contract in writing: commercial display, derived data, storage, retention after the contract ends (already confirmed), attribution wording | DATA-2, DATA-4, DATA-8 | M2 |
| Fama-French terms of use for display in a paid service | DATA-6 | M2 |
| Counsel review: perimeter (PER), MAR set (REC/BDG), badge labels (D1), position risk ratings, any-size founder disclosure, Terms, Privacy | §13 of the requirements | M4; D1 before M1 if possible |
| Mollie merchant account in the entity's name, described as financial analysis software | BIZ-5 | M4 |
| DPAs with Hetzner, Brevo, Mollie, the accountant; record of processing; breach procedure | GDPR-3, GDPR-4, GDPR-9 | M3 |
| Legal translations FR, DE, IT, ES by fluent reviewers; NL and EN self-review | INT-1, INT-4 | each language's release |
| Professional liability + cyber insurance (tell the broker about the badges) | BIZ-8 | M4 |
| Personal trade register, kept from now on | REC-9 | now |
| Optional: FSMA FinTech contact point; trade mark (BOIP/EUIPO) | PER-10, BIZ-9 | — |

---

## 3. Track B: project structure

### Target layout

```
app.py, run_app.py                 entry points (unchanged)
screener.py                        ← compliant version, swapped in place (stages 2–6 only)
fundamentals.py                    NEW: Stage 1 split out of screener.py, behind a provider interface
risk.py                            ← compliant version, swapped in place
scoring.py, portfolio_enrichment.py, marketdata.py, fx.py, prices.py,
portfolio.py, cash.py, auth.py, crypto.py, backup.py, settings.py   unchanged location
uvalu/
  compliance/                      NEW package
    signal_history.py              moved from the root
    settings_audit.py              moved from the root
    disclosures.py                 founder holdings loader, disclaimer/tooltip/producer texts
    consent.py                     accepted legal-text versions per user (DIS-2, TOU-9)
    policies.py                    loads docs/legal/policies/<lang>/*.md for the in-app legal pages
  billing/                         NEW package (M4)
    mollie.py                      hosted checkout, recurring payments, webhooks, refunds
    subscription.py                state machine: trial → active → cancelled / withdrawn
    vat.py                         EU VAT rates by country, OSS evidence
  jobs/
    daily_build.py                 NEW: scheduled universe build after the EU close
  pages_/
    legal.py                       NEW: Terms, Privacy, Methodology, Data sources, Conflicts, Complaints
    help.py                        renamed in the UI to "Methodology & help"
docs/
  stock_valuation_algorithm.md, portfolio_risk_assessment_algorithm.md   ← compliant specs swapped in
  legal/
    policies/<lang>/*.md           translated legal pages (EN is the reference)
    perimeter-memo.md              NEW (PER-9)
    algorithm-compliance-review.md kept as the review record
  design/                          handoff imported: legal Uvalu.dc.html replaces the current one
  archive/                         superseded plans moved here
data/compliance/                   runtime: signal log, snapshots, settings audit, founder_holdings.json
```

### Steps

**S1 Swap the algorithms (with M1).** The compliant copies replace `screener.py` and `risk.py` in place. There is no switch back to the old labels: a regulator judges what the product can do. The 19 + 11 importers keep their imports.
1. Freeze the copies' output on the synthetic universe in `tests/snapshots/`. The equivalence tests need the originals, so the snapshot replaces them.
2. Move `screener_compliant.py` over `screener.py` (Stage 1 imports become local again).
3. Move `risk_compliant.py` over `risk.py`.
4. Delete the `*_compliant.py` files and the equivalence tests.

**S2 Compliance package (with M1).** Move `signal_history.py` and `settings_audit.py` to `uvalu/compliance/`. Move the founder holdings loader and the legal display texts into `disclosures.py`. Point every log file at `data/compliance/`.

**S3 Split Stage 1 out of `screener.py` (with M2).** Move the yfinance workers, `_Fetcher` lanes and caches to `fundamentals.py` behind a small provider interface (`fetch_row(ticker) -> dict`). Switching to EODHD then touches one module.

**S4 Daily build job (with M2).** The design promises signals "recomputed daily after EU close, about 22:00 CET" on end-of-day prices. Today the Streamlit process fetches and rescores in background threads with a jittered 24 h TTL.
- Move that work to `uvalu/jobs/daily_build.py`, run by a systemd timer on Hetzner. Each run:
  1. fetches EOD data;
  2. scores the public universe once;
  3. writes the scored frame;
  4. calls `record_changes`, `write_daily_snapshot` and `record_model_version`.
- Streamlit only reads the result.
- What this buys:
  - one timestamp for all signals (REC-4);
  - the same signal for every user by construction (PER-2);
  - no intraday prices (DATA-3);
  - a much simpler app process.

**S5 New packages (with M3/M4).** `uvalu/compliance/consent.py`, `policies.py` and `uvalu/billing/`, as each milestone needs them.

**S6 Docs and design housekeeping (with M1).**
- Import the handoff into `docs/design/`: legal `Uvalu.dc.html` replaces the current file; pre-legal goes to `docs/design/archive/`.
- Swap the compliant specs over the originals.
- Archive the superseded plans: business plan v1, cash-management plan, `backend-feature-gaps.md` if stale.

**S7 Backups (with M1).** The per-user backup ZIPs never contain `data/compliance/`, so the server-level backup (Hetzner Storage Box) must include it. It is regulatory evidence.

---

## 4. Track C: algorithms and data

Most of the rules already live in the compliant copies; this is the wiring, plus what the design adds.

| # | Change | Req. | Repo | Milestone |
| --- | --- | --- | --- | --- |
| C1 | Wiring checklist §4 steps 1–16 of the review: peer mask, `user_selected`, `signal_code` everywhere, observations, disclosures, settings audit hook, founder holdings, quality-screen reasons | PER, REC, BDG | `uvalu/data.py`, `components.py`, `drawer.py`, pages, `settings.py`, `tools/valuation_audit.py` | M1 |
| C2 | Remove analyst fields from the Stage 1 field lists and purge both caches; remove the "Analyst Target" row | DATA-6 | `screener.py`/`fundamentals.py`, `uvalu/components.py:320, 392` | M1 |
| C3 | Raise the shared `min_mos` default to 10%; record it with `record_planned_change` first (trading blackout) | REC-2, REC-9 | `settings.py` | M1 |
| C4 | Delete `alert_buy_signal` / `alert_avoid_signal` (risk observations are never alerts, founder decision) | PER-5 | `settings.py` | M1 |
| C5 | Apply D1 (labels), D4 (24-month retention), D5 (horizon), D12 (model version) | BDG-1, REC-6/7/11 | `screener.py`, `uvalu/compliance/` | M1 |
| C6 | Position risk ratings: remove the valuation gap from the rating, neutral band names (pending counsel) | PER-4 | `risk.py` | M1 or after counsel |
| C7 | EODHD provider; `DATA_SOURCE` + attribution; benchmark and sector from EODHD | DATA-1/2/4 | `fundamentals.py`, `marketdata.py` | M2 |
| C8 | Beta (B3): remove `apply_live_mos`; label prices "delayed" with their time. M2: EOD prices only, remove `price_autorefresh` and the price refresh setting | DATA-3, REC-4 | `uvalu/data.py:394`, `uvalu/ui.py:249`, settings page | M1 (beta part); M2 |
| C9 | Sensitivity table data for the stock page: fair value and MoS at discount rate ±1 pp, on the shared model, display-only (D2) | REC-6 | `screener.py` | M1 |
| C10 | Data freshness flag for the stock page from `data_flags` | REC-3 | `components.py` | M1 |
| C11 | `signal_distribution` → coverage line on Screener and Methodology | REC-10 | pages | M1 |

---

## 5. Track D: UI per the design

Only the legal changes in `Uvalu.dc.html` are listed. Build them in Streamlit to match the design. The dashed "§ LEGAL" boxes are handoff notes and are not built.

### Every screen

| Element | Req. | Repo |
| --- | --- | --- |
| Footer: short disclaimer (in the user's language), producer identity, "not supervised by the FSMA", links to the six legal pages, "not directed at UK, US, Switzerland" | DIS-1, REC-1, BIZ-3, TOU-8, INT-5/6 | `uvalu/shell.py` |
| Badge helper: descriptive label (D1) + BDG-2 tooltip + methodology link; badge column widened to 140 px in every table | BDG-1/2 | `uvalu/components.py` |
| Provenance line under each page title that shows badges: "Prices · end-of-day close <date> · Signals computed <time> · Model <version> · Methodology →" | REC-4, DATA-3, REC-5 | Dashboard, Portfolio, Screener, Watchlist, Analysis, drawer |
| "Buy" → "Add position"; drawer actions under "Your records · nothing is executed": "Record purchase", "Record sale", "Edit position"; sell dialog title "Record sale · <ticker>" | PER-7 | `uvalu/dialogs.py`, `uvalu/drawer.py`, pages |

### Per screen

| Screen | Changes | Req. |
| --- | --- | --- |
| **Dashboard / Portfolio** | "Conviction & risk" → "Score & risk"; "Composite conviction" → "Weighted composite score", describing the portfolio; "hard veto" → "fails a quality screen"; "remaining margin of safety" → "model margin of safety", "Fair values are estimates" | REC-2, PER-4 |
| **Screener** | Remove "Export list"; coverage line | DATA-5, REC-10 |
| **Dividends** | Tax box: "Tax figures are estimates", rules, years, country, last review date, cases not handled, user responsibility; subtitle "Estimate under Belgian rules" | TAX-1/2/5/6 |
| **Risk** | DIS-3 banner; observations instead of rebalancing; describe-only wording ("No single name is above 12%…", "fails the leverage quality screen") | DIS-3, PER-4 |
| **Analysis (stock page)** | Under the badge: computed time, price used, models, MoS, methodology link. "Composite fair value · estimate". New panels: badge history (12 months), assumptions & sensitivity (D2), data sources with freshness flag, producer & conflicts (founder line from `founder_holds`, D9). "Value thesis" → "Model summary" | REC-1–8, BDG-3 |
| **Settings** | "Screening & veto rules" → "Model settings & quality screens" (D2: read-only for non-admins); thresholds relabelled for "Undervalued"; "Price refresh interval" → "Market data · EOD" row; new cards: **Subscription & billing** (status, renewal line, Cancel, Withdraw with deadline, Invoices), **Security & privacy** (2FA, Export my data, Delete account, privacy contact), **Legal documents** (Terms / Privacy / no-advice acknowledgement with accepted version and time, binding language) | SUB-4/6/7/8, GDPR-7, SEC-2, TOU-9, INT-2 |
| **Methodology & help** (renamed from Help & docs) | Links to methodology, data sources, conflicts; "Badges · meaning and thresholds" (from `methodology()`); "Reading the badges": horizon, update time, history, coverage, same-for-every-user, risk, sensitivity; data sources; conflicts (data-driven); "About Uvalu" with the full disclaimer; support text: "we can't comment on whether you should buy, hold or sell" | REC-5/6/7/10, DIS-1, PER-6 |
| **Legal pages** (new) | Doc list, table of contents, rendered Markdown from `docs/legal/policies/<lang>/`, reference-language note; `[TBD]` highlighting only outside production | TOU-9, GDPR-1, REC-3/5/8, TOU-8, INT-2 |
| **Sign-in** | Tagline "Calculate fair value with six models" (number per D3); "Daily · model update, EOD prices" instead of "24/7 signal monitoring"; full short disclaimer and identity; "Create account" | DIS-5, DIS-8 |
| **Sign-up** (new) | Email, password, country (EEA only; UK, US, CH blocked); three separate unticked boxes: 18+, Terms + Privacy (with versions), no-advice acknowledgement. Each stored with time and text version | DIS-2, TOU-9, SUB-10, INT-7 |
| **Checkout** (new) | Plan, features, price excl. VAT, VAT at the customer's country rate, total; automatic renewal; 14-day withdrawal with date; provider identity; "no advice, no execution, no custody"; button "Order and pay €x" in every language; note on Mollie hosted checkout | SUB-1/2/3/5/6, SEC-7 |
| **Confirm dialogs** | Cancel subscription / Withdraw from contract / Delete account, with the exact consequences | SUB-7, GDPR-7 |

Streamlit notes (from earlier work): use one `@st.dialog` at a time, call `enter_dialog()` at the top of each dialog, navigate by URL in tests, and expect the fixed-px grid header-wrap issues when widening the badge column.

---

## 6. Track E: accounts, consent, billing, GDPR

| # | Item | Req. | Milestone |
| --- | --- | --- | --- |
| E1 | Consent records: per user, the document, version, language, time and checkbox text version; re-acceptance when Terms change (30 days' notice); existing users (you, current testers) accept at next sign-in | DIS-2, TOU-9, SUB-8 | M3 |
| E2 | **Beta:** invite acceptance page (existing invite token) with the three unticked boxes: 18+, Terms (beta) + Privacy with versions, no-advice acknowledgement; asks country of residence (EEA only). **Paid launch:** public sign-up with country gating and VAT evidence | DIS-2, TOU-9, SUB-10, INT-7, BIZ-2 | M3 (beta form); M4 (public) |
| E3 | Self-service export: JSON + CSV of holdings, transactions, dividends, cash, settings (Excel export exists; add machine-readable) | GDPR-7 (art. 20) | M3 |
| E4 | Self-service account deletion (admin `auth.delete_user` exists); purge from backups within the D8 period; keep invoices | GDPR-7, GDPR-8 | M3 |
| E5 | Mollie: hosted checkout, recurring payments, webhooks, cancel at period end, withdrawal = full refund within 14 days, invoices | SUB-1–9, SEC-7, BIZ-4 | M4 |
| E6 | Service emails (Brevo; no email sending exists in the code today, invite links are handed over manually): order confirmation with terms + withdrawal form, trial reminder (D6), price-change and terms-change notices | SUB-5, SUB-8, SUB-9 | M4 |
| E7 | Verify MFA is mandatory for admins; cross-user access test before launch | SEC-2, SEC-3 | M3 |
| E8 | Privacy: record of processing, DPIA (short), sub-processor list, breach register | GDPR-3, GDPR-9, GDPR-12 | M3 |

---

## 7. Track F: translations

- Every new string goes through `tools/i18n_update.py`; blank its fuzzy guesses (wrong placeholders break the catalog test).
- Legal texts are badge labels, tooltip, disclaimers, signal definitions, risk disclosures, consent boxes, checkout texts and the six pages. They need fluent review for FR, DE, IT and ES before that language is offered to paying users (INT-1, INT-4). Until then, those languages stay off for the paid plan.
- "Order and pay" must stay an explicit pay instruction in each language (SUB-2).
- The legal pages move to `docs/legal/policies/<lang>/`, with EN as the reference version (INT-2).

---

## 8. Track G: tests and guardrails

| Guard | Purpose |
| --- | --- |
| `tests/test_legal_guards.py`: scan `messages.pot` and the legal texts for banned terms ("Strong Buy", "advice", "adviser", "recommended for you", "your personal", "consider selling", "rebalance", "beat the market", "safe stocks") | DIS-5, DIS-6, PER-4 across the whole app |
| Snapshot test of scored output (from S1) | Refactors (S3, S4) don't move scores silently |
| PER-1/PER-2 tests kept from the compliance suite | The signal never depends on the viewer |
| Cross-user access test | SEC-3 |
| Mollie test-mode end-to-end: sign-up → checkout → cancel → withdraw → refund | SUB-1–9 |
| `docs/legal/perimeter-memo.md`, reviewed before each release that touches signals, alerts or the risk screen | PER-9 |

---

## 9. Milestones

Each signal-moving release starts the founder's trading blackout. Record it with `record_planned_change` when it's decided, and don't trade affected shares until 2 trading days after it's live.

| Milestone | Version | Contents | Depends on |
| --- | --- | --- | --- |
**Free beta (now)**

| Milestone | Version | Contents | Depends on |
| --- | --- | --- | --- |
| **M0 Decide and start** | — | Decisions needed for the beta: D1–D5, D7–D9, D12 (D6 trial, D10 provider and D11 entity can wait); B2 (Yahoo or EODHD first); the five external items in §0; trade register | — |
| **M1 Compliant engine and legal UI** | v2.1.0 | S1, S2, S6, S7; C1–C6, C9–C11, **C8 as B3** (same-snapshot price, "delayed" labels); Track D "every screen" + Dashboard, Portfolio, Screener, Dividends, Risk, Analysis, Methodology & help, legal pages (beta texts, B4), sign-in copy, beta banner (B7), producer identity (B6); G guards; EN/NL only for testers (B5) | D1 ideally from counsel; D2–D5, D9, D12 |
| **M3 Accounts and consent (beta version)** | v2.2.0 | S5 (compliance only), E1, E2 (invite acceptance form), E3, E4, E7, E8; Settings: Security & privacy, Legal documents. **Beta opens on this release**, after the go/no-go in §0 | DPAs, D7, D8 |

**Later (postponed)**

| Milestone | Version | Contents | Depends on |
| --- | --- | --- | --- |
| **M2 Licensed data, daily build** | v2.3.0 | S3, S4, C7; data sources panels and legal pages switch from the beta texts to the launch texts for data | EODHD contract |
| **M4 Paid launch** | v3.0.0 (MAJOR: new env keys and accounts migration) | S5 (billing), E2 (public sign-up), E5, E6; checkout, Subscription & billing card; full Terms and Privacy; final translations for every language; counsel sign-off; every `[TBD]` filled; go/no-go checklist (requirements §13) | M2, entity, VAT, Mollie, counsel, insurance |

**Order within M1:** S1 + S2 first (one PR, with C1 so the app keeps working), then the badge helper and footer (they touch every screen), then the screens one by one.

**Not built for the beta** (from Track D): the Settings "Subscription & billing" card, the sign-up page's checkout step, the cancel and withdraw dialogs, "Order and pay", and the "end-of-day" / "daily after EU close" wording, which waits for M2.

---

## 10. Out of scope here

- Tax features beyond the existing dividend withholding display: each needs its own review (TAX-7).
- DCF and EV/EBIT models (D3): a valuation feature, not a compliance one.
- UK, US or Swiss availability (INT-5, INT-6, INT-8).
- Machine learning or LLM features: these would bring in AI Act art. 50.
