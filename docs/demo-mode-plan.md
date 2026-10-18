# Demo mode plan (draft)

18 October 2026 · Sven Claes · status: **all decisions DM-D1–D21 taken 18 Oct 2026 (§2)**

**Progress (18 Oct 2026, `feature/demo-mode`, not merged):** DM-1 core (`uvalu/datamode.py`, demo universe) and DM-3 (EODHD client, budget, snapshot store, `tools/demo_refresh.py`, `demo-data` workflow) built and tested. All 10 EODHD codes confirmed with a live backfill (10 calls on 18 Oct; 248–254 bars each, last bar 16 Oct; London in pence). DM-4 started: template + validator (`uvalu/demo/fundamentals.py`, `tools/demo_fundamentals.py check|template`); All 9 stocks entered for FY2023–FY2025 from results releases, annual reports and 20-Fs (SEC copies where they exist; company PDFs for KBC, LVMH and Nestlé), every figure with source and page; KBC uses the bank statement type. The six SEC filers were cross-checked against their 20-F XBRL facts (SAP's FY2025 moved to the audited 20-F figures as a result). Awaiting Sven's spot-check.

**DM-5 first pass (18 Oct 2026):** the demo runs locally (`.claude/launch.json` → `uvalu-demo`, port 8530). How it works, in place of the cache-feeding sketch in §4b:
- `uvalu/demo/workspace.py` builds a temporary workspace per process and redirects every data path the app writes (`data/…`, `.cache/…`) into it, runs the migrations there, and seeds each browser session with the sample portfolio (D15) and watchlist; "Reset sample portfolio" puts it back. Your personal data is never touched; throwaway secrets, no sign-in.
- `uvalu/demo/yfshim.py` answers `yfinance` from the snapshot (prices, history, dividends, lookups), `fx` answers from the snapshot's ECB rates, the Ken French download is off. Missed requests log `demo.offline_request` (only `^GSPC` today).
- `uvalu/demo/rows.py` turns the reports into Yahoo-style rows (reporting-currency figures plus `financialCurrency`, converted by the engine); beta against EURO STOXX 50 (`STOXX50E.INDX`, D16).
- Screener: demo universe of 9 (planned exchanges Copenhagen and London included), scored with the Damodaran sector multiples (`demo-data/reference/sector_multiples.json`, as of 5 Jan 2026) through a new `sector_multiples` option of `compute_scores`; fetching off in demo mode.
- Two existing bugs fixed on the way (they affect personal mode too): the value-history backfill summed pence and foreign-currency prices as euros; the Risk page's cash note added native values as euros.

**DM-5 second pass (18 Oct 2026):** demo notice redesigned (design A: one line, ending in "Terms →" and "Reset sample", no layout shift); Settings shows only Language & region in demo mode (no password, sessions, export or delete, D6); "X isn't in the demo" on the Watchlist add field and the Buy dialog (F-10); data-source rows, the screener's provenance label and two Methodology answers per mode; Risk shows "Factor analysis isn't part of the demo… available in the full version"; prices labelled "end-of-day prices of <date>"; demo privacy notice and data-sources page (`docs/legal/policies/demo/`, drafts for the DM-7 legal review); "Give feedback →" appears in the notice once `UVALU_FEEDBACK_URL` is set (D10); 18 new texts drafted in five languages, fuzzy, for review in Poedit (D21).

**Still open before testers:** Poedit review of the drafts; feedback form chosen and its URL set; dividends for Nestlé, Novo and Shell (next refresh); terms of use: the beta text still applies to the demo (check in the DM-7 legal review).

Source: *Uvalu Demo – Requirements Spec* (18 Oct 2026). This plan turns that spec into work packages for this repo. It also adds the things the spec doesn't cover yet: data modes, Streamlit Community Cloud, licensing and privacy.

## 1. Goal: three data modes, one codebase

| Mode | Data sources | Who sees it | Where it runs | When |
| --- | --- | --- | --- | --- |
| **personal** | Yahoo Finance (yfinance), stockanalysis.com lists, frankfurter/ECB FX | Only you (Yahoo terms: personal use, L2) | Your PC / Hetzner | Today's app, unchanged |
| **demo** | EODHD free plan (EOD prices), hand-entered fundamentals from annual reports, ECB FX | Testers and crowdfunding backers | Streamlit Community Cloud | This plan |
| **commercial** | EODHD under a written commercial licence (L20), or another licensed vendor | Paying users | Hetzner (deployment.md) | Later: M2 / C7 / S3 / S4 |

One setting picks the mode: `UVALU_DATA_MODE = personal | demo | commercial` (environment variable or Streamlit secret; default `personal`). Each mode is a **profile**: data provider, ticker universe, sign-in on/off, writes allowed or not, data-source texts, banner, which pages show.

**Key design choice: the demo app never calls a data API.** A scheduled GitHub Action calls EODHD and ECB once a day and commits a small snapshot to the repo. The app on Community Cloud only reads that snapshot. This solves several things at once:

- Community Cloud's disk is wiped on every restart or sleep, so an in-app cache and API-call counter would reset, and the 20-calls/day budget couldn't be enforced. The counter lives in the repo instead.
- The EODHD key lives only in GitHub Actions secrets. The deployed app doesn't need it at all (N-04; the acceptance test "app runs without the key" passes by design).
- A push of new data makes Community Cloud redeploy, so the app shows the new day without its own scheduler.
- Commercial mode later swaps the snapshot reader for a live provider behind the same interface (N-05), which is the S3/C7 work already in the compliance plan.

## 2. Decisions to take

Recommendation first. These change the work below. DM-D11–D21 added 18 Oct 2026 after a second read of the plan and what building DM-1/3/4 turned up.

**All decided 18 Oct 2026.** As recommended: D1 invite-only first, D2 demo question added to the L20 list and sent now, D3 hand-made sector reference, D4 per-session edits with reset, D5 compliant labels, D7 all six languages, D8 yearly update with audited figures winning, D9 Hetzner stays personal (testers move to the demo), D11 none of the 9 stocks held (no disclosure needed), D12 accept repo access for the invite-only phase, D13 Damodaran Europe (terms to check), D14 FY2025 annual only, D17 M4 now and M5 with R2, D18 release v2026.10.11 right after the merge, D19 21:00 UTC, D20 `uvalu-demo.streamlit.app`, D21 Poedit plus legal review.

Different from the recommendation, and what follows from it:

- **D6: Watchlist is shown,** kept per browser session like the sample portfolio (starred stocks reset when the session ends). Hidden: Admin, import/export, account pages; Settings only for language and region.
- **D10: feedback form plus basic analytics.** Tool decided 18 Oct 2026:
  - **Invite-only phase: Community Cloud's built-in app analytics** (total viewers, the last 20 viewers with their last visit; named for a private app). Nothing added to the page, no cookies, no consent banner. Every invited viewer can also open these analytics and see the other testers' names, so the demo privacy note says so.
  - **Before people you don't know get access: Uvalu's own anonymous page events**: page, language, session length, features used; no names or IP addresses; sent from the existing `logkit` render events to an EU-hosted store (e.g. Supabase, Frankfurt), key in Streamlit secrets; one line in the privacy note. Not Google Analytics; no third-party tracking script.
- **D15: €25,000, a realistic mix:** uneven weights in 6 of the 9 stocks, still including the CHF, DKK and GBX lines and at least one dividend payer, so the spec's currency and dividend checks keep working (F-02, F-03, F-04, F-06).
- **D16: benchmark matches the app (EURO STOXX 50).** One extra EODHD series, so 11 calls on weekdays (still under the stop at 18). The index code is checked with one call when built. L21 (STOXX licence) now applies to the demo too; VWCE stays in the universe as the ETF example.

| ID | Question | Recommendation | Why it matters |
| --- | --- | --- | --- |
| DM-D1 | **Who sees the demo, and how?** Invite-only (viewers sign in with Google/GitHub email) or a public link? | **Invite-only first** (testers), public link only after DM-D2 is answered in writing | The free EODHD plan is personal / non-commercial. Showing it to crowdfunding backers is promotion of a commercial product. |
| DM-D2 | **Data licence for the demo.** | Send EODHD one question now (add it to the L20 list): "May we show free-plan or EOD-plan data for 10 tickers in a private, non-paying demo to prospective testers and crowdfunding backers?" Get the answer in writing before backers see it. | Same risk as L2 with Yahoo, just a different vendor. Also check whether LSE/SIX/Copenhagen exchange fees apply to display. |
| DM-D3 | **Peer reference for scoring.** The engine scores against a universe-wide reference (`ScoreReference`: sector P/E, P/B, ranks). With 9 stocks, five sectors, mostly one stock per sector, that reference is meaningless. | Ship a **hand-made reference file** (sector medians from a public, citable source, with as-of date), not one derived from Yahoo data. Fall back to "rank within the demo" only if no source is found. | Without it, scores and signals in the demo are noise. A reference built from Yahoo data would bring Yahoo-derived data into the demo. |
| DM-D4 | **Can viewers change the sample portfolio?** | **Yes, per browser session only**, with a "Reset sample" button. Nothing is written to disk. | Many viewers share one app process. A shared, writable portfolio would let one visitor wreck it for the next. |
| DM-D5 | **Signal labels.** The spec says BUY / MONITOR / AVOID / VETO. The app has used the compliant labels since L12–L14 (e.g. "Mid score", "Screened out", with the "Model signal" qualifier, enforced by `tests/test_signal_qualifier.py`), and the brand rules say no buy-voice. | **Keep the current compliant labels.** Correct the spec. | A public demo on named stocks is exactly where the old labels would hurt most (investment-recommendation rules). |
| DM-D6 | **Pages in the demo.** The spec names Dashboard, Screener, Portfolio, Risk, "Stock Detail". In the app that's the Analysis page plus the drawer. | Show Dashboard, Screener, Portfolio, Risk, Analysis, Help/Methodology, Legal, About. Hide Watchlist (or session-only), Cash, Settings (except language/region), Admin, import/export, account pages. | Fewer surfaces to make demo-safe. |
| DM-D7 | **Languages.** | Keep all six; they work already and are a good demo point. | Translated strings for the new demo texts are needed (i18n review flow). |
| DM-D8 | **Fundamentals snapshot refresh.** | Once at setup, then after each annual report (March–April); every field carries the report and page it came from. | Hand entry is work: about 15–25 fields × 9 stocks. |
| DM-D9 | **What happens to today's Hetzner beta?** | It stays in **personal** mode for you only. Beta testers you know move to the demo. | Today's beta shows Yahoo data to other people (L2). The demo is the clean way to keep showing the product. |
| DM-D10 | **Feedback from viewers.** | A "Give feedback" link to a form (e.g. Tally, EU-hosted) and no analytics in the app. | You want to learn from backers, but Community Cloud already runs in the US (see §3); keep the app itself free of personal data. |
| DM-D11 | **Do you hold any of the 9 demo stocks?** | Name them; then disclose them the way the app already does, or swap the stock for another in the same sector and currency. | §3 "Conflicts": signals on a stock the publisher holds need a disclosure. |
| DM-D12 | **Repo access.** Community Cloud reads the whole private repo (business plans, legal drafts, expert reviews). | Accept it for the invite-only phase; decide on a separate small demo repo before the demo goes public. | It's a third party reading confidential documents. |
| DM-D13 | **Source of the sector reference file** (DM-D3). | Damodaran's European industry multiples (January 2026), after checking his terms of use; dated and cited in the file. | DM-D3 chose a hand-made file but not where its numbers come from. |
| DM-D14 | **How fresh the fundamentals are.** FY2025 is about 10 months old; H1 2026 interim results exist. | FY2025 audited annual figures only, shown as "as of 31 Dec 2025". | Interim figures are unaudited, differ per company and double the entry work. |
| DM-D15 | **Sample portfolio contents.** | About €50,000, roughly equal weights in the 9 stocks, bought on different dates inside the 1-year history; fictional, round numbers. | The spec only says "pre-filled"; gains, losses and dividends should all show. |
| DM-D16 | **Benchmark for beta and risk.** The app uses EURO STOXX 50 (licence question L21); the demo has VWCE. | VWCE in the demo, said on the Methodology page. | Methodology differs between modes; VWCE also sidesteps L21. |
| DM-D17 | **Which model the demo runs.** | Deploy on M4 now; move to M5 with the R2 release (re-run the snapshot → cache step then). | M5 changes scores; waiting for it delays the demo by weeks. |
| DM-D18 | **First deploy.** The workflow builds `deploy/demo` from the latest release tag. | Cut a small release right after the merge (v2026.10.11), so `deploy/demo` starts from a tag. | Before that, no tag contains the demo code. |
| DM-D19 | **Refresh time.** The spec says 18:30 CET; built as 21:00 UTC. | Keep 21:00 UTC weekdays; record it as a spec change. | EODHD's European end-of-day prices aren't final right after the close; the job re-asks for the full year anyway. |
| DM-D20 | **App address** on Community Cloud. | `uvalu-demo.streamlit.app`. | It's the link you share. |
| DM-D21 | **New demo texts** (banner, privacy note, "full version" placeholders, "not in the demo"). | Draft them, review in Poedit as usual (six languages), and include them in the DM-7 legal-persona review. | New user-facing and legal-ish wording. |

Answered already, by the spec or the existing code:

- **FX source:** ECB reference rates via frankfurter, as today (`fx.py`). Zero EODHD calls. ECB allows reuse with attribution.
- **GBX → GBP and currency display:** already in the app since v2026.10.10 (`marketdata.price_divisor`, holdings in EUR, currency codes). The demo reuses it.

## 3. Things the spec doesn't mention yet

**Streamlit Community Cloud**

- **The repo is private.** Community Cloud can deploy from a private repo, but you give Streamlit read access to the whole repo: business plans, legal drafts, expert reviews in `docs/`. Options: accept that, or deploy from a separate small demo repo that a CI job fills (more work). **Limits (checked 18 Oct 2026): 1 private app, unlimited public apps, 2.7 GB per app.** The invite-only demo (DM-D1) takes the one private slot, so there's no second private app for a staging copy. Test demo mode locally (`UVALU_DATA_MODE=demo`) before pushing to the `deploy/demo` branch. Going public later (after DM-D2) frees the slot.
- **Servers are in the US** (Snowflake). The privacy notice promises EU hosting at Hetzner. The demo needs its own short privacy note: no account, no personal data stored by Uvalu, Streamlit's own logs and cookies apply. No sign-in in demo mode keeps this simple.
- **Sleep.** An app with no traffic for about 12 hours goes to sleep; the next visitor sees a "wake up" button and waits 30–60 s. A daily data push redeploys it, which helps but doesn't guarantee it's awake. Tell backers, or open it yourself before a presentation.
- **`.streamlit/config.toml` forces a local SSL certificate** (`.ssl/cert.pem`). On Community Cloud that file doesn't exist and the app won't start. Move the SSL lines out of the committed config (into `run_app.py` / `_dev_entry.py` flags, or the Hetzner service file).
- **Secrets.** `AUTH_SECRET` and `ENCRYPTION_KEY` are required at start-up today. In demo mode either skip what needs them or set throwaway values in Streamlit secrets, never the production ones.
- **Python 3.12** must be chosen in the deploy settings (the app needs ≥ 3.12). Dependencies come from `requirements.txt`; check it installs cleanly without dev extras.
- **Memory:** 2.7 GB per app. Plenty for 10 tickers; demo mode still loads only `demo-data/`, never the full 3,900-listing caches.
- **Branch.** Community Cloud deploys from a **`deploy/demo` branch**, never from `master`. The daily Action checks out `deploy/demo`, merges the latest release tag into it, adds the new data under `demo-data/` and pushes. So `master` gets no daily bot commits (no pull-before-push, no data in release diffs, no clash with `tools/release.py`), and the demo moves to new code only when a release is tagged. Data commits carry `[skip ci]` so `tests.yml` doesn't run every weekday on private-repo minutes.

**Data and model**

- **History is 1 year.** Risk stress tests use 10 years (`risk.STRESS_HISTORY_PERIOD`), Monte Carlo and factor analytics want more too. In demo mode these show "available in the full version" instead of a result built on too little data.
- **Dividends.** The spec has no dividend feed, but AB InBev and TotalEnergies are there to show dividends. Options: EODHD dividends endpoint (1 call per ticker; weekly, on a Sunday, fits the budget) or enter them by hand with the fundamentals. Recommendation: weekly EODHD call.
- **"Day change"** in demo mode is close-to-close of the last two EOD bars, labelled as such; no intraday refresh (`price_autorefresh` and market-hours polling off).
- **Analyst targets and dispersion** (M4) come from Yahoo today. There's no equivalent in the demo, so the models that need them stay dark, with a reason shown.
- **Ticker keys.** The app stores Yahoo-format tickers (D12). The registry converts to EODHD codes (`SAP.XETRA`, `SHEL.LSE`, …) for the refresh job only; the app keeps its keys. Validate all 10 codes with the welcome-bonus calls.
- **Corporate actions.** Use EODHD's adjusted close and store the raw close too; never overwrite history with an empty or shorter response (spec step 3).

**Legal and trust**

- **Named stocks, public audience.** Signals on real, named stocks shown to the public are closer to an "investment recommendation" than a private beta. Keep the M1 legal UI (disclaimer, Methodology, "Model signal") on every demo screen, and run the demo past the legal-counsel persona before backers see it.
- **Conflicts.** You hold some covered stocks. If any of the 9 demo stocks are among them, the demo needs the same disclosure the app uses, or pick other stocks.
- **Sample portfolio** is fictional, round numbers, not your own holdings.
- **Data-sources texts** (`uvalu/compliance/disclosures.DATA_SOURCE_ROWS`, `screener.DATA_SOURCE`) must come from the mode profile. Today they say "Yahoo Finance".
- **stockanalysis.com (L29)** stays in personal mode only. In demo mode the universe is a fixed list, so no scraping.

## 4. Work packages

| WP | What | Done when |
| --- | --- | --- |
| **DM-0 Decide and check** | Answer §2. Send the EODHD question (DM-D2). Validate the 10 EODHD codes and the 1-year backfill with the bonus calls. Correct the spec (labels, screen names, design tokens are in `uvalu/styles.py` + `.streamlit/config.toml`, not `utils.py`). | Decisions recorded here and in `open-items.md`; 10 codes confirmed. |
| **DM-1 Data mode switch** | `uvalu/datamode.py`: reads `UVALU_DATA_MODE`, returns a frozen profile (provider, universe, auth, writable, sources texts, hidden pages, banner). Personal mode behaves exactly as today. | Tests: default is personal; each profile is complete; no page reads the env var directly. |
| **DM-2 Provider interface** | A small `Provider` protocol: `price_history`, `latest_prices`, `dividends`, `fundamentals_rows`, `fx_rates`, `universe`. `YahooProvider` wraps today's `marketdata.py` / `prices.py` / screener fetch; `SnapshotProvider` reads `demo-data/`. Route the existing yfinance call sites through it (a slim version of compliance-plan S3). | In demo mode, a test with sockets blocked runs all pages; `yfinance` is never called. |
| **DM-3 Refresh job** | `tools/demo_refresh.py` + `.github/workflows/demo-data.yml` (weekdays ~17:00 UTC, plus manual run). Backfill, daily EOD bar per ticker, weekly dividends, ECB FX. Call counter in `demo-data/budget.json` (stop at 18/day, N-01). Never shrink history. Logs calls used, tickers updated and errors (N-06) through `logkit`. Commits only when data changed. | Dry run against a stub; one real run on the free plan uses ≤ 10 calls; a failed fetch leaves yesterday's data in place. |
| **DM-4 Fundamentals snapshot** | `demo-data/fundamentals/<ticker>.json` with the fields the engine needs, each with source (report, page) and an as-of date; plus the reference file (DM-D3). A validator checks units, currency and completeness. | All 9 stocks score; Analysis shows "Fundamentals as of …" (F-09). |
| **DM-5 Demo behaviour** | No sign-in; session-only sample portfolio with reset (DM-D4); universe lock with a "not in the demo" message (F-10); hidden pages (DM-D6); demo banner with source and last refresh date on every screen (F-01); "full version" placeholders for 10-year risk analytics; demo privacy note; feedback link. Translations for new strings. | AppTest per page in demo mode; banner and as-of dates on every screen. |
| **DM-6 Community Cloud** | Move SSL out of `config.toml`; demo secrets; Python 3.12; check `requirements.txt`; deploy; set viewers (DM-D1). Update `docs/deployment.md` with a Community Cloud section. | App starts on Community Cloud from a cold boot; every screen < 2 s from cache (N-02). |
| **DM-7 Acceptance and release** | Walk the spec's acceptance list; legal-persona review; release notes (public + internal). | All acceptance boxes ticked; release tagged. |

Order: DM-0 → DM-1 → DM-2 → (DM-3 ∥ DM-4) → DM-5 → DM-6 → DM-7. DM-3 and DM-4 can run in parallel. DM-4 (hand entry) is the long pole in calendar time.

## 4b. Fit with ongoing work (checked 18 Oct 2026)

No open branches, worktrees or running sessions. The work in flight is the exchange expansion release 2 (from 21 Oct) and the EODHD question list (L20). How the demo fits:

| Ongoing work | Overlap | Rule |
| --- | --- | --- |
| **Q1 flicker measurement** (14–21 Oct) | Any change to fetching or scoring on your running instance spoils it. | Nothing from this plan merges into `master` before 21 Oct. DM-0 (decisions, EODHD, hand entry of fundamentals) can start now. |
| **Exchange expansion R2**: EX-W4 primary listing, EX-W5 units, EX-W5b yields, EX-W6–W8 exchanges, EX-W10 Index filter | DM-2 reroutes the yfinance calls in `screener.py` (`_Fetcher`), `prices.py` and `marketdata.py`: the same files as EX-W4/W5. Run both at once and they conflict. | **Do DM-2 after R2 ships** (or between two R2 packages, never in parallel). DM-1 (the mode switch) touches other files and can go first. |
| **Model M5** (risk-free rate per currency, `MODEL_VERSION` bump) | The demo scores with the same engine. The M5 yield snapshot (OECD, Bund for EUR, dated, never fetched at run time) is exactly the kind of committed snapshot the demo needs. | Build DM-4's fundamentals and sector reference against **M5**, not M4, or the hand-entered fields change. The demo uses the M5 yield snapshot as-is. |
| **Registry and ticker formats** (EX-W2, D12, EX-40) | The refresh job needs EODHD codes. | Add the EODHD conversion rule to the registry (`uvalu/exchanges.py`), as EX-40 already foresees. No separate mapping in the demo code. |
| **L20 EODHD question list** (13 questions, not sent yet) | DM-D2 is one more question. | Add the demo question before you send the list; one email. |
| **Compliance plan M2: S3 / C7 / S4** | DM-2 is a slim S3 (provider interface). | Design DM-2 as S3, so the commercial switch reuses it instead of redoing it. |
| **Before-strangers plan** (L3 MAR opinion, L4 KBO + business address on every page) | Crowdfunding backers you don't know are "strangers"; that rule isn't only about accounts. | Testers you know: fine after DM-7. Backers: after L3 and L4 too (DM-D2 already gates them). |
| **UX5 user study** ("on a warmed staging server") | The demo isn't a substitute: 9 stocks, no real screening. | Keep them separate. |
| **`.streamlit/config.toml` SSL lines** | Used by `run_app.py` locally and by the run-uvalu skill; Hetzner runs `run_app.py` behind Caddy. | Moving SSL to launch flags (DM-6) must keep `run_app.py`, `_dev_entry.py` and the Hetzner service working. Check all three. |

The design reference round 3 and the colour/logo work are shipped (v2026.10.4) and have nothing pending, so there's no overlap there.

**Resulting order:** now: DM-0 (+ the L20 email) · after 21 Oct: DM-1 · after R2: DM-2 → DM-3 ∥ DM-4 (against M5) → DM-5 → DM-6 → DM-7.

### Start-now track (18 Oct 2026)

Building can start now on a branch `feature/demo-mode`; only the **merge** waits for Q1 (21 Oct). Most of the demo can avoid the R2 files if it **feeds the caches the app already reads** instead of rewiring the fetch code first:

- The app already paints from disk: fundamentals from `.cache/fundamentals.json` / `.cache/portfolio_fundamentals.json` (`screener._Fetcher`), price history from `.cache/history/<ticker>.csv` (`marketdata`), live prices through one facade (`uvalu/data._fetch_prices_batch`).
- The demo job writes those same files (from EODHD prices, the hand-entered fundamentals and ECB FX) into `demo-data/`. In demo mode the app points its cache paths there and **switches fetching off**: no `_Fetcher` start, and `_fetch_prices_batch` returns the last EOD close from history.
- That's a few guarded lines in `screener.py` and `uvalu/data.py` instead of a rewrite, so the overlap with R2 shrinks to almost nothing. The full provider interface (DM-2 / S3) moves to commercial mode, where it's needed anyway.
- Risk: R2 may change the fundamentals row format (units, reporting currency, M5). The snapshot → cache step is one script, so it gets re-run after R2, and a test checks that the demo rows still score.

| Now (no R2 overlap) | After 21 Oct (merge) | After R2 |
| --- | --- | --- |
| DM-0 decisions; EODHD question added to L20 and sent | Merge `feature/demo-mode` | Re-run snapshot → cache for the R2/M5 row format |
| DM-1 `uvalu/datamode.py` + profiles (new file) | First Community Cloud deploy from the `deploy/demo` branch | Hand-entered fields checked against M5 |
| DM-3 refresh job, budget counter, workflow, tests (new files) | | DM-7 acceptance, release |
| DM-4 fundamentals template + validator; you start entering data | | |
| Demo banner, sample portfolio, universe lock, privacy note, hidden pages (DM-5, mostly new code) | | |
| Offline switch: the guarded lines in `screener.py` / `uvalu/data.py` | | |
| SSL lines out of `config.toml`, checked with `run_app.py`, `_dev_entry.py` and the Hetzner service (DM-6) | | |

**What you do yourself** (I can't create accounts): sign up for the EODHD free plan and put the key in a GitHub Actions secret (`EODHD_API_KEY`); create the Streamlit Community Cloud account and give it access to the repo.

### API budget during development (18 Oct 2026)

Calls come from **one place only**: `tools/demo_refresh.py` with an explicit `--live` flag. The app (locally and on Community Cloud), the tests and CI never call EODHD. They read `demo-data/` or recorded fixtures.

| Stage | Live calls | How |
| --- | --- | --- |
| Building the client and parser | **0** | EODHD's public `demo` token (works for a few US tickers such as AAPL.US) for the request/response shape, then recorded JSON fixtures in `tests/fixtures/eodhd/`. |
| First live check | **1** | One ticker (ABI.BR), 1-year backfill: proves the key, the code format and the parser on a European stock. |
| Setup for the rest | **9** | Backfill of the other 9 tickers. A wrong code fails on its own call, so no separate symbol-list calls (saves ~7). Their responses become fixtures too. |
| Daily | **11** | GitHub Action, weekdays: 10 tickers + the EURO STOXX 50 benchmark (DM-D16). |
| Weekly | **10** | Dividends, on Sunday (a day with no EOD run). |

The setup total is about 10 calls out of the 500 welcome calls, and every run after that replays recorded data. Guards:

- **Default is dry run.** Without `--live` the script uses fixtures and says so.
- **Hard cap per run** (`--max-calls`, default 10) on top of the daily counter (stop at 18, N-01).
- **The limit is per key, not per machine.** A local live run and the Action share the same 20 calls. The counter in `demo-data/budget.json` only knows about runs that commit it, so don't do live runs locally on a day the Action runs. Otherwise the Action stops early, and it logs why.
- **Retries:** at most one per ticker, and none on 401/403/404 (those won't succeed on a retry).
- **One account, one key.** Don't create extra free accounts to get more calls; that breaks EODHD's terms.

A one-stock *demo* would save almost nothing: the backfill is one call per ticker. It also wouldn't test what the 10 are there for: four currencies, GBX, five sectors, diversification and the peer reference. One stock is useful in two places: the **first live call**, and the **first hand-entered fundamentals file** (ABI.BR), which checks the template and the validator before you enter the other eight.

## 5. Later: commercial mode

Same profile mechanism, a live `EodhdProvider` (paid plan, fundamentals included), the daily build (S4), sign-in and subscriptions on, Hetzner hosting, launch texts in the legal pages. Gated on the EODHD contract (L20) and the paywall work in the roadmap. The demo's snapshot format becomes the test fixture for that provider.
