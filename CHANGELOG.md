# Changelog

All notable changes to Uvalu are documented here, in full: this is the
internal record for the team, operators and admins, and the text of each
GitHub Release. Subscribers see the shorter, benefit-first
[RELEASE_NOTES.md](RELEASE_NOTES.md) in the app under *What's new*; every
release here has a section there too.

From October 2026 versions are calendar versions, `YYYY.MM.N` (the N-th release
of that month); earlier releases used SemVer. Rules in
[CONTRIBUTING.md § Versioning and releases](CONTRIBUTING.md#versioning-and-releases):

- Start a release with one or two sentences: what you'll notice, and anything
  you need to do besides restarting. Say it when scores or signals change, and
  add `Data schema: N` when stored data is migrated.
- Group entries under **Added**, **Changed**, **Fixed** and **Removed** only.
- Plain language; name a file, command or setting when an operator needs it,
  but no function names or work-package ids (those belong in commits).

---

## [Unreleased]

### Fixed

- Translations (TR1, docs/translation-review.md): French showed "Risque
  élevé" for both Elevated and High risk; Elevated is now "Risque accru",
  and Italian and Spanish use "sopra la media" / "superior a la media"
  instead of near-synonyms of High. "Screened out" no longer reads as
  "removed by the filter" (which clashed with the Screener's own filters):
  Uitgesloten, Exclu, Ausgeschlossen, Escluso, Excluido, also in the signal
  distribution line and the help question. The dividend "Yield" column and
  the Analysis yield figures now say dividend yield instead of the general
  word for return.
- Dashboard totals (UX2, docs/ux-review.md): the Current value card says how
  it adds up (holdings + cash, or holdings with no cash recorded) instead
  of an unexplained chip; the Total return card says it covers open
  positions (unrealised + dividends); the value chart says it shows
  holdings without cash. The Dashboard now records today's value point
  (at most every 10 minutes), so the chart's last point matches the card.
- Negative margin of safety (UX3): below -100% the margin is shown as
  "price N× fair value" (new `components.fmt_mos_pct`), and per-model
  values in the fair-value ladder are capped at "< -100%". Fair value on
  the stock preview and the Analysis hero is no longer green.
- Risk page wording (UX4): a factor loading is Low only below 0.3 (0.75
  was shown as Low), the caption gives the thresholds in the user's number
  format, concentration weights show one decimal (no more "30% above
  30%"), the Sharpe reference is formatted per locale, and a risk report
  saved earlier the same day no longer counts as the previous report for
  "two consecutive reports".

## [2026.10.7] — 2026-10-14

**Signals change** with models M3 and M4: the Graham and P/E models use
normalised earnings, so a one-off gain no longer inflates fair values, and a
fair value the models don't agree on, or a margin above 50%, is no longer
called Undervalued.

### Changed

- Model M3. The Graham Number and the P/E fair value use normalised earnings
  per share: the median (3 years) or trimmed mean (4+ years) of net income,
  divided by the shares, instead of the latest year. The P/E growth
  adjustment uses the yearly growth of net income over 3–4 years; without
  that history, the latest growth only counts between −50% and +50%. On
  today's data this cuts Undervalued from 78 to 58 stocks: one-off gains
  (WE.CONNECT, Newprinces, Deutsche Rohstoff) no longer drive the top of the
  list.
- Where the provider's share count covers one share class only (price ×
  shares far from the market cap), the count from market cap ÷ price is used.
- A stock valued on the latest year only, with a price under 4 times those
  earnings, is flagged ("may include a one-off gain") and can't be
  Undervalued.
- Methodology (beta 1.3 and the paid version): normalised earnings, the
  growth adjustment and the M3 change-log row.
- Model M4. When the highest model value is more than 3 times the lowest,
  or the margin of safety is above 50%, the stock gets no Undervalued signal
  and a data flag ("the models disagree" with their range, or "check the
  figures"). On today's data Undervalued goes from 58 to 33 stocks; the
  broken price of TPG0.DE no longer tops the list.
- The signal explanation now also names the currency, one-off, disagreement
  and large-margin reasons, and says when a signal is kept by the stability
  rule instead of claiming the score is above the threshold.
- Methodology beta 1.4 and the paid version: the Undervalued definition, the
  two checks and the M4 change-log row.

## [2026.10.6] — 2026-10-14

**Signals change** with model M2: the coverage is now home listings only,
reported figures in another currency are converted before valuation, and a
stability rule stops signals flipping on small score changes. M2 needs one
full 24-hour data refresh before every stock carries its reporting currency.

### Changed

- Model M2. The coverage is now companies from the six covered countries on
  their home exchange; secondary listings of other companies (about a third
  of the old list, mostly US) and listings that don't trade are left out. A
  share a user added or holds is still scored against the coverage.
- Figures a company reports in another currency than its share is quoted in
  (for example a Swiss company reporting in dollars) are converted with ECB
  reference rates before valuation. When no rate is available the stock is
  flagged and gets no Undervalued signal.
- A stock keeps its signal until its composite score falls 2 points past the
  edge; moving up still needs the full threshold. The 10% minimum margin of
  safety and the quality screen apply without exception.
- An incomplete data update no longer changes a signal: the last complete
  figures are used (up to 7 days after a failed update, up to 90 days for a
  missing year of the financial statements).
- The signal history records which inputs moved each signal change, and each
  build logs a data-quality summary with warnings when the provider sends
  incomplete data for many stocks or a build moves many signals.
- Methodology pages: coverage, currency conversion, stability rule and the
  M2 change-log row.
- Signal names: the middle band is now "Mid score" (was "Neutral", which
  reads like an analyst rating) and a failed quality screen is now
  "Screened out" (was "Fails quality screen"). The stored codes are
  unchanged. Every signal is shown with a visible "Model signal" label, and
  the Dashboard's holdings column is headed "Model signal" with a note that
  signals are the same for every user. A test fails if a new screen shows a
  signal without the label.
- The model signal no longer appears next to your own position. On the
  Risk page, the last column of "Risk contribution by holding" is now
  "Position risk" and shows only the position's own risk rating (High or
  Critical), not "Screened out". In the stock preview, the stock's metrics
  stay with the signal, and your shares, value and P&L move to a separate
  "Your position" section below the record buttons' divider, with a note
  that the signal doesn't take them into account.

### Added

- Joining by invitation now starts with a short confirmation step: country
  of residence (European Economic Area only) and three statements, ticked
  by the invitee (18 or older; read the terms of use and the privacy notice;
  the no-personal-advice acknowledgement). The answers are stored with the
  version of each text and the time, and Settings › Legal documents shows
  what you accepted and when.
- A record of every administrator action on another user's account
  (password reset link, two-step reset, role or status change, sign-out,
  deletion, backup restore), kept 24 months under pseudonymous ids.
- Invitations that were never accepted are deleted 30 days after they
  expire.
- Beta privacy notice 1.4, effective 28 October 2026: the confirmation
  record, the administrator action record, the per-address sign-in limit
  and what a reset link allows.
- Drafts of the GDPR paperwork in `docs/legal/gdpr/`: record of processing,
  legitimate-interest notes and a DPIA screening.
- A limit per network address on failed sign-ins: 20 failed attempts from
  one address within 15 minutes block that address for the rest of the
  window, whatever accounts were tried. Like the account lock, it shows the
  usual "Invalid email or password." message.
- Production set-up for the first server, in `deploy/` with the steps in
  `docs/deployment.md`: Caddy in front with automatic HTTPS and security
  headers, the app as a systemd service on localhost only, and daily
  encrypted offsite backups to a Hetzner Storage Box, kept 29 days. Start
  the app with `UVALU_BEHIND_PROXY=1` behind the proxy.
- `docs/incident-procedure.md`: what to do after a security incident or
  data breach, including the 72-hour notification and the breach register.

### Removed

- Admin › Backups no longer offers "Export key". The deployment's master
  secrets (`AUTH_SECRET`, `ENCRYPTION_KEY` in `.env`) never go to a browser
  any more. When moving to a new server, copy `.env` over SSH and keep one
  offline copy; see `docs/deployment.md`.

### Fixed

- Two-step sign-in: wrong authenticator or backup codes now count towards
  the account lock, with the same limit and lock time as wrong passwords
  (Admin › Security). Entering the correct password again no longer resets
  that count, a locked account refuses even a correct code, and a code that
  was already used to sign in can't be used again. Before, someone who knew
  a password could keep guessing codes.
- Sign-in no longer reveals which email addresses have an account. Every
  failed sign-in shows the same "Invalid email or password." and takes the
  same time, whether the email is unknown, the password is wrong or the
  account is locked. The "attempts remaining" count is gone. The account
  lock still applies; the countdown card now appears after the set number of
  failed attempts in the same browser session, whatever emails were typed.
- The sign-in cookies are now `SameSite=Strict`, and `Secure` when the app is
  served over HTTPS, so other sites can't make the browser send them.
- Tickers, sectors and country names from the data provider or added by
  users are now escaped wherever the app shows them in its own layout
  (holdings, portfolio, dividends, risk and stock pages), so text that looks
  like markup is shown as text instead of being run.

## [2026.10.5] — 2026-10-11

Import & export now works for every user: a portfolio workbook you can restore
from or bulk-add to, a full copy of your data under Settings › Privacy, and
self-service account deletion. Scores and signals don't change. Data schema: 2
— on first start stored data is cleaned (a migration snapshot is taken first;
the step can't be undone). Before publishing privacy notice beta 1.3, confirm
the offsite Storage Box backups rotate within 30 days.

### Added

- **Portfolio import from the export format.** Settings › Import & export
  reads the same workbook it exports: upload it, see what it holds and any
  row problems (sheet and row number) before anything is written, then
  **Add** (append, rows you already have are skipped) or **Replace** (a backup
  is saved, positions, sales, dividends, cash and watchlist are deleted, then
  the file is loaded; settings stay). Sheets are recognised by their headers,
  so a file exported in one language imports in another; older exports still
  import. Every imported buy and sale posts its cash with automatic top-ups,
  like a trade entered by hand; sold positions' dividends are recomputed from
  the dividend rows. Accounts whose trades predate cash management get
  Buy/Sell and top-up entries on a Replace restore, so their balance changes —
  one Adjustment corrects it.
- **Export my data** (Settings › Privacy): everything Uvalu holds about the
  user in one workbook — Account (never a password, code or token), Settings
  (one sheet, every setting as section · setting · value), the portfolio
  sheets and Automatic cash (the entries Uvalu posted for trades and
  dividends).
- **Delete account** (Settings › Privacy): confirmed by typing the account
  email. The login record, portfolio folder, settings file and the account's
  backups in the Admin backup history are removed at once; the last active
  Admin is refused. The Admin portal's Delete user now does the same (it used
  to leave the user's data on disk). Migration snapshots older than 30 days
  are deleted automatically, so "removed from backups within 30 days" holds.
- **Privacy, Plan and Legal documents cards** in Settings, as in the design
  reference: privacy contact, the free-beta plan, and the terms of use and
  privacy notice with their version, effective date and a View button. The
  no-personal-advice acknowledgement is marked "Not available" until
  acceptance is recorded (open item L1).

### Changed

- **The Excel export holds only what you entered**: Positions, Sold,
  Dividends, Cash (typed entries) and Watchlist, with real date and number
  cells, a note on every column header and fixed English column names. It
  doubles as the template for a bulk import — an empty account downloads the
  headers only.
- The provenance line's **Methodology →** link uses the link colour, like
  every other link (it was grey and underlined). Brand guidelines updated.
- Privacy notice (beta) → beta 1.3: account deletion is self-service in the
  settings; the export also carries account details and settings.
- The encrypted backup now includes the target allocation and hand-added
  watchlist tickers.
- Settings › Import & export laid out as the design reference.

### Fixed

- **Swiss dividends recorded without a currency were counted as euros**; they
  now use the exchange's currency (CHF). Migration 2 fills the missing
  currency in stored data.
- Cash activity: each ledger row's edit pencil stuck out 8px past the card
  edge, in every language.
- Dividend log and cash ledger rows picked up the tax-note box's padding,
  background and border from a broken style rule (since 2026.10.3).

### Removed

- The old import of a fixed-layout personal spreadsheet (sheet
  `beleggingen`).
- The CSV export buttons on Portfolio, Cash activity, the Dividend log and
  the annual dividend summary; the workbook in Settings replaces them.
- Stored fields nothing used (migration 2): `google_ticker`, `target_price`
  and `account` on positions and sales; `google_ticker`,
  `declaration_date`, `record_date`, `reinvested` and `reinvested_shares` on
  dividends.

## [2026.10.4] — 2026-10-11

Uvalu has a new logo, the What's new notes are written for subscribers, and
buttons, navigation and labels now match the design reference. Scores and
signals don't change. Nothing to do besides restarting; the new logo build
tools (fontTools, resvg-py) are only needed to regenerate `assets/logo/`.

### Added

- **Two sets of release notes.** This file stays the complete record and the
  GitHub Release text; the new `RELEASE_NOTES.md` holds the subscriber-facing
  notes that *What's new* shows, grouped New / Improved / Fixed / Removed and
  without admin or operator items. `tools/release.py prepare` cuts both;
  `check-changelog` and the release tag guard check that every CalVer release
  has public notes with the same date; `notes --public` prints them.

### Changed

- **About › What's new** and the one-time update notice read the public notes
  instead of this file.
- **Buttons and segmented controls** match the design reference: 12.5px
  labels (primary 500, 34px high), outline buttons in the muted text colour
  until hover, segmented controls 12px/500 (currency codes in monospace),
  the Dashboard range control 11.5px monospace and the benchmark chips 11px.
  Streamlit 1.60 had put every label in its own 14px paragraph, so the
  app's button sizes and colours no longer reached the text.
- **Top navigation**: new icons (home, monitoring, star, work, shield), and
  inactive pages read grey again; the Admin side navigation likewise.
- **Beta notice**: text centred in its box.
- **Model names** follow the design reference and the legal Methodology
  document: "Dividend, single stage", "Dividend, multi-stage", "Book value
  (fallback)" and "FCF value (fallback)" in the stock panel and Analysis; the
  Methodology page uses the document's own names.
- **Portfolio and Risk tables** show the exchange code (BRU, XET, PAR) under
  the ticker, as the Screener does.
- **Dashboard**: the value chart opens on the past year ("Past year · incl.
  deposits") when there is a year of history.
- **Risk**: a "Suboptimal" Sharpe or Sortino verdict is amber; red stays for
  a failed quality screen.
- **Analysis › Assumptions & sensitivity** says the settings are shared
  ("Shared settings · model M1") and marks the discount rate in force.
- **Settings › Language & region**: the preview is one band with sentence-case
  labels and the "Try a number" field inside it.
- **Legal pages**: tables, bold lead-ins and the version chips use the
  document styles of the design reference. **About › What's new** lead-ins
  are medium weight.
- **Closed positions**: "· realised" at its smaller reference size.
- **New logo.** The Consensus mark (two rings for independent valuation
  models, a filled lens where they agree) with the outlined "uvalu" wordmark
  replaces the V-stroke mark in the top bar, the Admin portal, the sign-in
  screen and the browser tab. The top bar uses the light lockup in the light
  theme and the dark lockup in the dark theme. The files live in
  `assets/logo/` and are generated by `tools/build_logo.py` (dev-only
  dependencies: fontTools, resvg-py; Inter Medium in `tools/fonts/` under the
  SIL Open Font License); brand guidelines v1.4 describe them.

### Removed

- The old `favicon.svg` and the unused `.uv-logo-*` sidebar-logo styles.

### Fixed

- **About › What's new**: the notes now fill the card width (the supporting
  pages' 72-character reading measure no longer applies there), and the card
  heading no longer overlaps the first release row.
- **Footer**: the disclaimer line uses the full width (the 980px cap is gone).
- **Footer while a page loads**: it no longer jumps under the top bar. The
  rules that keep it at the bottom of the screen lived in the footer's own
  `<style>`, which Streamlit removes with the old footer mid-load, so the page
  collapsed; they are now in the global stylesheet.
- **Fair-value models**: a model's difference to the price used the amber
  fill colour as text; it now uses the readable amber text colour.
- **Sign-in screen**: the disclaimer, producer line and legal links sit at the
  bottom of the navy panel across its full width (the 520px cap is gone). The
  brand text was one markdown block, so the panel's space-between never
  reached it; it now fills the panel and pushes the legal text down.

## [2026.10.3] — 2026-10-10

The app now follows brand guidelines v1.3 and the updated design reference:
clearer colours and spacing on every screen, and a sign-in that is password
only during the free beta. The model, its scores and its signals are
unchanged. Admins: an account that only ever signed in with Google can't
sign in now; the start-up output and Admin portal › Users list these
accounts, and a password reset lets them set a password.

### Added

- **Screener**: a rank column, short exchange codes (PAR, XET, …), a *Hide
  positions I own* filter, and *No signal* stocks listed at the default
  filters (with their own filter).
- **Dashboard**: *Add position* next to *Refresh*; the sector allocation as
  a compact ring with its legend; upcoming dividends with their payment
  date; top movers open the stock panel.
- **Settings**: *Table density* (compact or comfortable rows) is back; the
  model settings in force are listed for everyone; the Language & region
  card explains each setting, previews it and lets you try reading a
  number in your region's format.
- **Methodology**: today's share of stocks per signal, and the badge
  definitions with the thresholds in force.
- The legal pages can be read before signing in, from the sign-in screen.

### Changed

- **Colours**: margin of safety is green from 15%, plain up to 0% and amber
  below 0% — never red. Red now only marks a stock that fails a quality
  screen (and the Low score badge). Links have their own, more readable
  colour, and small grey text is darker.
- **Scores** are described by band ("Upper band · 70–100"); the Dashboard
  average margin of safety is weighted by position value; holdings show
  their result as a percentage of cost.
- **Page titles and headers** are the same size on every page, with the
  signal details as the third line under the title.
- **Portfolio**: every open position is listed on the overview; dividends
  show net and gross; the closed-positions page is narrower; exports say
  what they export.
- **Stock panel and Analysis**: the analysis button comes first, the model
  summary is the last card on Analysis, and the sensitivity table shows
  four settings without badges.
- **Settings**: one *Account security* card with your sessions in it; your
  account details at the bottom.
- **Sign-in**: password only during the free beta, with the full
  disclaimer and the legal links on the sign-in panel. Accounts are created
  by invitation only. Password reset links are valid for 30 minutes (was
  24 hours).
- **Privacy notice** (beta 1.2): no longer describes Google sign-in,
  passkeys or data the beta doesn't collect; mentions the breached-password
  check; account deletion is by request to privacy@uvalu.app.
- **Analysis**: the model summary now ends "It is general information, not
  personal advice"; fair values are described as estimates of value, not
  forecasts of where the price will go.
- Notices sit in a fixed order under the top bar; the footer is
  left-aligned.

### Removed

- **Settings › Data & alerts**: prices refresh every minute in market hours
  (every 15 minutes outside them), and the Dashboard no longer shows
  ex-dividend, cut or raise badges.
- The *Implied return* tile in the stock panel and *Legal & policies* in the
  user menu (the footer and Settings lead there).

## [2026.10.2] — 2026-10-07

A calmer, more consistent look: signal details sit in one quiet line under the
page title, the supporting pages share one layout, and tooltips follow the
app's theme. Scores and signals are unchanged; nothing to do besides
restarting with `run_app.py`.

### Changed

- **Signal details are quieter and always in the same place.** When the
  signals were computed, the price time, the model version and the
  *Methodology →* link are now a plain line under the page title on the
  Dashboard, Screener and Watchlist, instead of a coloured box.
- **Screener**: each signal filter now shows the share of covered stocks with
  that signal (for example *Undervalued 3%*), replacing the separate coverage
  bar.
- **Dashboard**: the fair-value legend sits on the Holdings title row. A price
  above the model fair value is now amber instead of red, on every
  fair-value bar; red is kept for a failed quality screen.
- **Settings, Methodology, Legal and About share one layout**: a back
  link, the same title size, a section list on the left (a document picker on
  a phone) and a comfortable reading width. Long texts are a little smaller
  and easier to read; card headings are no longer in capitals.
- **About**: the build details are a simple list with a *Copy for support*
  button, and only the release you are running is opened, marked *This
  version*.
- **Tooltips** now follow the app's light or dark theme everywhere, including
  chart labels. Before, they could show as dark boxes on a light page.

### Fixed

- The *Print or save as PDF* button on the legal pages was not visible.
- The last line of some cards on the Methodology and Settings pages
  was cut off.

## [2026.10.1] — 2026-10-05

Versions are now calendar versions: this is the first, `YYYY.MM.N`. Nothing to
do besides restarting with `run_app.py`. Data schema: 1 (recorded on the first
start; no data changes).

### Added

- **Version in the footer** of every screen. Click it for the new **About Uvalu**
  page: the exact version, when it was built, and a line to copy when you
  contact support. Also in the avatar menu.
- **What's new**: the release notes of every version, in the app. After an
  update you see a short notice once, with a link to what changed.
- A prompt to reload the page when a newer version has been installed while
  you were using the app.
- Test installations are clearly marked with a coloured stripe and a DEV or
  TEST label, so they can't be mistaken for the real app.
- An error message now includes a short reference to quote to support.
- Admins: a **System** tab with the server's version, data version, software
  versions and when each data source last updated.
- Operators: stored data now has a version and is upgraded automatically on
  start, with a snapshot first; the app refuses to run on data from another
  version instead of misreading it. Rolling back to an earlier release is a
  documented, tested procedure.

### Changed

- Backups record which version made them. A backup from a newer version is
  refused; an older one is brought up to date when you restore it.

## [2.1.1] — 2026-10-05

PATCH — legal texts only; scores and signals are unchanged. Pull and restart.

### Changed

- **Legal pages reviewed for the free beta** and dated 5 October 2026. The beta texts now match what is true during the beta:
  - Conflicts of interest: the beta's data sources are free; no paid data-provider relationships.
  - Complaints: a beta version that refers to the right sections of the beta Terms and no longer mentions billing.
  - Privacy notice: invitation data, which account data is required, personal emails from our own mailbox, what market-data providers receive (ticker requests only), the sign-in storage and the Google sign-in cookies (30 days).
  - Terms of use: 14 days' notice and a free exit before changes take effect, a feedback clause, a reminder to keep your own records, a pointer to the founder's holdings disclosure, and English as the only language of the legal texts during the beta.
  - Methodology: the signal history starts at the opening of the beta and is kept 24 months.
- All six legal pages are shown in English in every app language, with a notice that no translation exists yet.

### Fixed

- The legal page no longer shows the "Reference language … rely on the version in your own language" note over the English fallback; it appears only over a real translation.
- Data sources linked to the wrong section of the beta Terms of use.

## [2.1.0] — 2026-10-05

MINOR — **scores and signals change**: the scoring and risk algorithms were replaced by their compliant versions (model **M1**, `docs/legal/compliance-implementation-plan.md`, decisions D1–D12 and B2). Nothing needs migrating: pull and restart. Expect different signals and some different fair values, see *Changed*. The app now runs as a **free beta** with the legal pages, footer and beta banner in place.

### Added

- **Legal page** (`/legal`): Terms of use, Privacy notice, Methodology, Data sources, Conflicts of interest and Complaints, rendered from `docs/legal/policies/` (beta versions in `policies/beta/` while the beta runs). A section menu stays in view while you read, each document has an "On this page" list, version and date tags, and a *Print or save as PDF* button that prints only the document. Reachable from the footer, the user menu (*Legal & policies*), Settings and every badge's *Methodology →* link.
- **Legal footer on every screen**: short disclaimer, producer identity, "not authorised or supervised by the FSMA", and the six legal links. **Beta banner** at the top of every screen.
- **Signal provenance** with every signal (REC-4/5/10): when the signals were computed, the time of the delayed prices (an amber "oldest …" chip when some are more than 72 hours old), the model version and *Methodology →*. On the Screener also the share of covered stocks per signal as a stacked bar, and counts in the signal filter buttons.
- **Signal and settings logs** (`data/compliance/`, kept 24 months): every signal change, a daily snapshot of the public signals, and every change to the shared model settings, with the model version.
- **Analysis page**: badge history (12 months), assumptions & sensitivity, data-quality flags, data sources, producer & conflicts (including a notice when the founder holds the stock) and a plain-language model summary at the top.
- **Settings**: a section menu; a *Legal* card; the *Dividend withholding* rates save with their own button; importing an Excel file now asks for confirmation before it replaces your portfolio data.
- Screener: 25 results at a time (*Show 25 more*) and a column header that stays visible while scrolling.

### Changed

- **Signals** (BDG-1/3): **Undervalued / Neutral / Low score / Fails quality screen / No signal** replace BUY / MONITOR / AVOID / VETO / Strong Buy, each with a tooltip saying it is a model output, not a personal recommendation.
- **Scores and fair values**:
  - *Undervalued* now needs at least a 10% margin of safety (D1).
  - Sector medians and percentile ranks come only from the public universe of enabled exchanges. Your own holdings and manual tickers no longer move them (PER-2).
  - A holding without that peer reference gets *No signal* instead of a rank among your own stocks (PER-1).
  - Analyst targets are no longer fetched or used while unlicensed (DATA-6).
  - The badge shows the price and margin of safety it was computed from (B3).
- **Risk page**: observations against the model's reference levels or your own targets, and disclosures, instead of rebalancing actions (PER-4). A failed quality screen stays a flag on the holding (PER-5).
- Dashboard: *Weighted composite score* replaces the conviction verdict. While the peer reference is still being built after a restart, the score card, average margin of safety and holdings table show a loading state instead of provisional numbers.
- **Look and feel** (visual review, `docs/design/visual-review-2026-10-04.md`):
  - Dark-theme signal badges and bar tracks are tinted instead of near-white.
  - Negative amounts put the minus in front of the symbol, like the plus (`-€ 86,01` / `+€ 126,60`).
  - Company names are tidied for display (share-class letters, ALL CAPS, "X, The").
  - Card footnotes use one style, and caution states use amber; red is kept for avoid/veto signals.
  - Settings rows are aligned, Analysis rows split 50/50, and the sector donut shows its shares in the legend.
- Month and day names follow the interface language; the region still sets the order (an English interface with Belgian formats read "mei" and "Maandag").
- "← Back" on the Legal, Settings and Analysis pages returns to the page you came from.
- The statement that Uvalu is not directed at residents of the UK, the US or Switzerland moved from the footer into the Terms of use (INT-5/6).

### Removed

- Rebalancing actions on the Risk page, and the buy/avoid alerts (PER-4, PER-5).
- The internal "PHASE 3" label on Passkeys; it now says "Not available in the beta".

### Fixed

- Portfolio: amounts wrapped mid-number at 1024px ("€ 109,⏎20").
- Analysis: a stock that fails a quality screen showed composite score "0 · Lower range"; it now shows "—" and "Excluded".
- Settings: the dividend-withholding fields ran out of their card, and the language preview still showed a *BUY* badge.
- Settings import: after a successful import the same file was imported again on every rerun.
- Risk: one holding could get both "rating changed to High" and "rating High"; the transition note replaces the plain one.
- The Watchlist is sorted by composite score. Score colours band on the shown (rounded) number. P/E ≤ 0 shows "—".
- Admin: the role select no longer cuts off, and "Last active" follows your date format.

## [2.0.1] — 2026-10-02

### Fixed

- Narrower windows (checked at 1280 and 1024px in all six languages):
  - Top bar: below 1200px the navigation links ran into the market-status text (at 1024px, in English too). The status text now hides there — the coloured dot keeps it as a tooltip — and the navigation icons hide.
  - Watchlist: the *Add ticker* button wrapped onto two lines at 1280px in German and Italian. The button's column now sizes to the button, so the form stays on one row down to 1024px.
  - Dashboard: *Full analysis →* wrapped in German; it stays on one line.
  - Portfolio: the cash card's "Last entry … · dividend" line spilled out of its column (Italian at 1280px, English at 1024px); it now wraps.

## [2.0.0] — 2026-10-02

MAJOR — **Python 3.12+ is now required** (was 3.11). Upgrade the interpreter and recreate the virtualenv before pulling; nothing else needs migrating (language and region settings default to detection; nothing stored changes shape).

### Added

- **Six languages: English, Dutch, French, German, Italian and Spanish** (spec: `docs/i18n-spec.md`). Every screen, dialog, sign-in and 2FA screen, error message, risk and rebalancing text and signal explanation is translated, with the informal form of address and a fixed financial glossary (`locales/glossary.csv`). Signal badges (BUY / MONITOR / AVOID / VETO / Strong Buy), tickers, company and exchange names stay as they are. The admin portal and logs stay English.
- **Settings › Language & region** (first card): language, region format (17 regions, e.g. nl-BE, fr-CH, de-AT), display currency (EUR / USD / GBP / CHF; CHF by default for Swiss regions), date format, time zone (Europe/Zurich by default for Swiss regions, else Europe/Brussels) and first day of the week, with a live preview and a reset. Settings follow you to other devices. Until you choose, both are detected from every language the browser lists (`nl, nl-BE` gives Dutch with Belgian formats; French with a `de-CH` browser gives fr-CH).
- **Language switcher on the sign-in screen**; the choice carries into your profile. `?lang=de` tries a language for the session without saving it.
- **Region-aware numbers, money, percentages and dates** everywhere, including charts (separators and date ticks) and tables. Totals (Dashboard, Portfolio, the Risk page's cash note) can be shown in the display currency, marked ≈. Percentages inside translated text follow the region too (30 % in Germany, 30% in Switzerland), and negative amounts in Swiss regions read -CHF 4’390 rather than CLDR's CHF-4’390.
- **Comma-decimal input**: money and quantity fields accept `1.234,56` in regions that use a decimal comma, and date pickers follow the region's day/month order.
- **CSV export in two formats**: *Spreadsheet format (for Excel)* (region decimal mark, `;` in comma-decimal regions, your date format) and *Machine format (for scripts)* (the previous output).
- Screener: names and signals sort by the language's alphabet, and search ignores accents, case and punctuation.
- Translation workflow: catalogs in `locales/` (see `locales/README.md`), `tools/i18n_update.py` (with `--since <ref>` for the PR summary; it keeps Poedit's line wrapping and the previous English of unreviewed entries, so a run after a Poedit save only touches what changed), `tools/i18n_compile.py`, `tools/i18n_review_csv.py`, `tools/i18n_merge.py` (three-way merge of translation files after a git merge), a pull request template, and an `i18n` CI workflow that blocks a release tag while any translation is unreviewed. Configuration in `i18n.config.json`.

### Changed

- **Dates follow your date format** (default Short, e.g. 01/07/2026 instead of 01 Jul 2026), signed amounts put the sign before the symbol (+€1,234), and CHF amounts use the standard CLDR form (CHF1,234), also in English.
- Table columns, the top bar and the Screener filters size themselves to the translated labels; headers stay on one line with an ellipsis and tooltip.
- Settings › Display: the disabled *Display currency* and *Number format* placeholders are gone, replaced by the Language & region card.
- Automatic cash-ledger notes are stored with a language-neutral copy (`note_i18n`) next to the English `note`, so they show in the viewer's language; older entries keep working.
- **Minimum Python raised to 3.12** (`pyproject.toml`, README, CONTRIBUTING). On 3.11 Babel can't extract `_()` calls inside f-strings, so the translation catalogs would silently lose entries; `tools/i18n_update.py` now refuses to run on older versions.
- New pinned dependencies: `babel` 2.18.0 (CLDR data, pinned so formats don't change silently) and `pyuca` 1.2.
- **Scores and signals now use one peer group: all enabled exchanges together.** Sector P/E and P/B medians (behind the P/E and book-value fair values) and the composite score's percentile ranks were taken per exchange on the Screener, Watchlist and Analysis page. Scores, fair values and some BUY/MONITOR signals move.

### Fixed

- Dashboard, Portfolio, Risk and the stock preview ranked a holding only against your other holdings (since v1.2.0), so its fair value, score and signal could differ from the Screener and Analysis page for the same stock (book value €25 vs €10 for one REIT; a Strong Buy shown as Monitor). Holdings are now scored against the scored universe's medians and ranks.
- Screener: the open Sector filter list clipped long sector names ("Communication S…"), in English too. Open select lists are now at least 260px wide.
- Analysis: the dividend hard-veto check showed "Dividend coverage adequate ✓" next to an "At Risk" flag. It now reads "Dividend covered by earnings" with the cover as its note, and a dividend that is flagged but not vetoed gets an amber "!" with the reason (e.g. "1.57× · at risk: FCF payout 270%").
- Stock preview and Analysis: the note under the six-model fair-value bars always named both "Book value" and "FCF value" as stand-ins, even when only one (or neither) row was shown. It now names only the fallback models on screen.

---

## [1.12.0] — 2026-09-27

MINOR — new capability, no manual migration step (record ids and the cash ledger are created automatically).

### Added

- **Cash Management v1** (design: `docs/design/Uvalu Cash Management.dc.html`, plan: `docs/cash-management-implementation-plan.md`). One cash balance per portfolio, derived from an append-only ledger in the encrypted `cash.json` and retained indefinitely:
  - **Portfolio → Cash balance strip**: balance, invested-vs-cash split bar, total portfolio value, Deposit / Withdraw.
  - **Cash activity page** (Portfolio → strip ⤢, or `/portfolio?section=cash`): five tiles (balance, net deposits, trade flow, income, fees & corrections), a filterable ledger (original amount + currency, FX rate with ECB / manual flag, amount in EUR, running balance, Auto / Manual source) and a full-history **CSV export** (any role).
  - **Add cash transaction** dialog: Deposit / Withdrawal / Fee / Interest / Adjustment, any currency, converted at the ECB rate for the transaction date (manual, flagged rate when frankfurter.dev has none). An adjustment sets the balance as its own correction entry; history is never overwritten. Withdrawals and fees that would take the balance below zero at any point in its history are blocked.
  - **Auto-posting**: Buy / Sell post their cash (value ± fees — both dialogs gained a *Fees* field and a *Cash after trade* preview) and every received dividend is mirrored into the ledger (net of all withholding; updated or removed when the dividend is edited or deleted; DRIP, Stock and future-dated dividends excluded). **A buy is never blocked by the balance**: a shortfall posts a linked automatic top-up deposit first, so the balance lands at €0.00.
  - **Dashboard**: *Current value* now includes cash, and a new *Cash* tile shows the balance and its share of total value.
  - **Risk page**: a banner states that risk metrics cover the invested portion only — cash is excluded from HHI, VaR, CVaR, factor exposure and Monte Carlo — with a link to the cash activity.
  - `portfolio_meta.json`: a fixed EUR base currency and never-reused TRD- / DIV- / C- reference counters. Backups now include `cash.json`, `portfolio_meta.json` and `dividend_meta.json`.
- **Edit and delete cash entries**: every Cash activity row has a ✎. Manual entries open an *Edit cash transaction* dialog (same form as Add, type locked; amount-only edits keep the stored FX rate) with Delete; automatic entries (trades, top-ups, dividends) open the same dialog read-only, with a button to the source record. Edits and deletes that would take the balance below zero are refused. The ledger shows 50 rows at a time with *Show more*.
- **Edit position / Edit trade ↔ cash**: an *Also update the linked cash entry* checkbox re-posts the trade's cash (top-up recomputed), and deleting offers *Also remove its cash entries* — both only while the cash entry still matches the record (not for partly-sold lots).
- **Delete confirmation** in every Edit dialog (positions, closed trades, dividends, cash): Delete → *Keep* / *Delete permanently*.
- **Sell shares…** in the Edit position dialog opens Close position for that holding.
- Optional **Buy date** / **Sell date** (default today) in Add position and Close position, so backdated trades post their cash on the right date.
- `fx.py`: frankfurter.dev (ECB reference rates) client with a permanent incremental disk cache (`.cache/fx_frankfurter.json`).

### Changed

- **FX now comes from one source — frankfurter.dev / ECB reference rates** — instead of yfinance `XXXEUR=X` pairs, for the dividend EUR conversion (`portfolio.dividends_in_eur`) and the risk engine's EUR restatement of price history (`risk._to_eur`, via the `marketdata.fx_to_eur_frame` shim). EUR dividend totals and risk metrics for non-EUR holdings (e.g. CHF) may shift slightly.
- Sell dialog: the confirm button is now "Confirm sale".
- **Leaving Portfolio and coming back lands on the Overview**, not on whichever sub-page (Open / Closed / Dividends / Cash) was open. Links that target a sub-page (Risk's *View cash activity*, the drawer's *Edit*) still go there.
- **Dialogs aligned**: every Portfolio dialog is 420px wide with a one-line subtitle, `*` on required fields and `(opt.)` on optional ones, `st.error` validation messages, one shared *Calculated* box (dividend tax, cash balance, cash after trade) and a *Save* button (Close position keeps *Confirm sale*). The cash dialog's type switch became a *Type* dropdown. The Edit dialogs moved from `pages_/portfolio.py` into `uvalu/dialogs.py`, and every dialog shows a read-only notice for the Viewer role.
- **One layout for every Add/Edit dialog**: identity row (Ticker | Company, or Type | Currency for cash; locked in Edit) → dates row → amounts row → details → *Calculated* box → cash-link line (Edit) → actions. Dates now always sit directly under the identity row; Edit position gained *Price / share* and a *Cash* box previewing the re-posted buy; Add / Edit trade gained a *Result* box (cost basis, proceeds, realised P&L); Edit dividend shows how its cash entry follows. Add and Edit use the same labels (*Sell date* in both trade dialogs). The gap between a dialog's title and subtitle is tightened, with a little more room above the buttons.
- Add dividend suggests your held tickers (any other symbol is still accepted) and rejects an ex-date after the payment date (also in Edit). Add trade validates the ticker like Add position.
- Page headers: *Add position*, *Add trade* (was *Close*, which read like selling a holding), *Add dividend*, *Add transaction*; every export button is *Export*. Open and Closed positions got a subtitle; empty states use the same info box. On the Cash page the Viewer role now sees the Deposit / Withdraw / Add transaction buttons disabled (like the other pages) instead of hidden.

### Fixed

- Selling part of a position removed the whole position (every lot) and booked its full cost basis. `portfolio.sell_position()` now sells FIFO across lots, keeps the unsold shares open with a pro-rata cost basis, and books only the sold shares' cost.
- **Edit trade** changed the share count but kept the old cost basis, silently changing the buy price and the realised P&L. Cost basis and proceeds are now both recomputed from shares × price.
- **Edit position** saved the page's whole render-time table — including live-price columns — back to `portfolio.json`, which could also overwrite a change made in the meantime. Edits now reload the file and change one record, and stray live-price columns are cleaned up.
- Edit dialogs addressed records by row index, which could hit the wrong row if the file changed while the dialog was open. Positions and closed trades now carry a stable `trade_id` (backfilled), dividends their `div_id`.
- Deleting a position or closed trade left its cash entries (and any top-up) in the ledger; the delete now offers to remove them.
- Light theme had no amber tokens (`--amber-bg` / `--amber-txt` fell back to the dark values).

---

## [1.11.1] — 2026-09-23

### Fixed

- Annual dividend income summary: on a narrower card the "N events · year to date" label overlapped the Gross figures (fixed 150px figure columns squeezed the label column to ~0px). All columns are now proportional, and the label truncates with an ellipsis instead of overflowing.

---

## [1.11.0] — 2026-09-23

### Added

- **Dividend Management v2**: a fuller dividend-event schema (declaration/ex/record/payment dates, gross per-share, Cash/Stock/Special type, auto-vs-manual source) with migration for pre-1.10.0 records — the Add/Edit dividend dialogs ask only ex-date + payment date, shares, per-share amount, foreign withholding and type; a new Belgian 30% *roerende voorheffing* tax layer (`portfolio.BE_WITHHOLDING_RATE`), applied automatically on top of any foreign withholding for every Cash/Special dividend; position-level yield-on-cost, trailing-12m yield and income (net + gross) columns on the Open positions table; a per-holding dividend profile (frequency override, dismissed auto-imported events) at `dividend_meta.json`; a "Dividend & income" panel on the Full Analysis page (TTM/forward yield, net YoC, growth streak, 1/3/5yr CAGR, payout ratio EPS/FCF, withholding breakdown, cut/increase detection, payment history); automatic once-per-session import of missing dividend events for held tickers from `marketdata.dividends()` — only ex-dates on which shares were held, skipping events already logged and never re-adding a deleted one (ex-date + amount only — the payment date defaults to the ex-date and is shown in amber until confirmed); a redesigned Dividend log (summary tiles, one-grid event table, Export) and an annual dividend income summary with CSV export; and three new Dashboard alert toggles (dividend cut/suspension, dividend increase, a position-size gate on the existing ex-dividend alert). All Add/Edit portfolio dialogs now share one layout (subtitle, Ticker | Company name first — locked when editing — then fields, then Delete | Cancel | Save).
- `screener._dividend_stats`: now also returns `dgr_1y`/`dgr_3y`/`dgr_5y` (windowed dividend CAGR) and `dividend_last_increase_year` (symmetric to the existing `dividend_last_cut_year`), feeding the new Analysis page dividend panel.

### Fixed

- Add/Edit/Close portfolio dialogs showed ~100px of empty space on the right: since Streamlit 1.60 the visible dialog box is the parent of `[role="dialog"]`, so the 420px width clamp now sizes that box instead of only the inner content.

---

## [1.10.0] — 2026-09-18

### Added

- **Dividend tax/currency/reinvestment tracking**: dividend records now carry native currency (auto-detected from the ticker's exchange, EUR converted for display via `marketdata.fx_to_eur_frame`), a per-exchange withholding-tax default (Settings → Dividend withholding, 0% until set) applied per record and editable, and an optional DRIP/reinvestment flag that folds the reinvested shares/cash into the position's cost basis instead of counting them as cash received. The full Dividends page now shows Gross/Tax/Net/Date columns and a CSV export.
- Settings: wired up the previously dead `alert_dividend_ex_date` toggle as an in-app "· soon" badge on Dashboard holdings going ex-dividend within 7 days.
- `screener._next_expected_ex_div`: forecasts the next ex-dividend date and payment frequency from the full payment history (`marketdata.dividends`), feeding Dashboard's "Upcoming dividends" card instead of yfinance's own `exDividendDate` field, which is normally the *last* ex-div date rather than a forecast and left the card mostly empty.

### Fixed

- Dashboard's "Dividends received"/"Total return" KPIs and Portfolio's dividend totals could include dividends dated in the future — a record entered ahead of its payment date now only counts once its date has passed (`portfolio._sync_portfolio_dividends`, the Portfolio Overview preview, and Dashboard's own aggregate all date-filter at the source now).
- Dashboard's lifetime dividends figure only summed open positions, silently dropping dividends earned on since-sold holdings; now matches Portfolio's own definition (open + sold).
- Portfolio Overview: the Dividends-received preview card stretched to match Closed Positions' height, leaving dead space under a shorter dividend list — CSS carve-out, same fix already applied to Dashboard's own equivalent row.
- Editing a dividend record dated after today (pre-existing future-dated entries, e.g. from before dates were capped) crashed the whole page — `st.date_input`'s bound now extends to the record's own date when needed.

---

## [1.9.0] — 2026-09-14

### Added

- **First-admin setup screen** on the login wall (`auth.no_users_exist()`) — a fresh install with no `ADMIN_EMAIL`/`ADMIN_PASSWORD` configured now gets a working "Create the first admin account" form instead of a dead-end invite-only sign-in screen.
- `docs/support-manual.md` — step-by-step admin/support procedures (creating accounts, handling lockouts, backups/restore/migration) to complement the existing feature and configuration references.

### Fixed

- Login screen: the Google/Microsoft provider buttons now sit with a deliberate 10px gap instead of Streamlit's default inter-element spacing.
- Admin → Security: toggles and "Configured"/"Not configured" badges were centered in their column instead of flush right per the design; the whole section also rendered full-bleed instead of the design's centered column.
- Settings page: rendered full-bleed instead of a centered ~920px column; Security/Active-sessions cards had no row dividers and stretched row-action buttons instead of content-width pills; the 4-option Screening style and Price refresh interval controls wrapped onto two lines inside the now-narrower column; Price refresh interval (converted from a drag slider to a segmented control) visibly resized per selected value; Target allocation used native widget labels/chrome inconsistent with the rest of the page; the Import/Export file-upload dropzone leaked a mismatched native background color instead of blending into the card.

### Docs

- Reorganized `docs/`: 5 completed implementation plans (self-labeled done, shipped per this file's own history) moved to `docs/archive/` with a README explaining what superseded each — `stock_valuation_improvement_plan.md`, `valuation_fv_coverage_plan.md`, `logging-implementation-plan.md`, `uvalu-auth-implementation-plan.md`, `valuation_audit_plan.md`.
- Fixed every cross-reference to the moved files (across docs, this file, `CONTRIBUTING.md`, and code comments in `tools/`/`uvalu/`/`tests/`) and a wrong claim in `docs/design/README.md` that `uvalu-auth-implementation-plan.md` maps the Auth mockup's 16 frames to the real app — that section doesn't exist; it's the original pre-build proposal, which doesn't even match what shipped.
- `docs/user-guide.md`'s "Registration and login" section still described open self-service signup, removed by the 1.8.0 auth overhaul — rewritten to describe the actual invite-only flow.
- README's Documentation table only listed 6 of 14 docs; now lists every living doc plus a pointer to `docs/archive/`.

---

## [1.8.0] — 2026-09-13

A ground-up auth overhaul (M1–M6, `docs/uvalu-auth-implementation-plan.md`): per-account
lockout, session tracking and self-service password change, Google OAuth + invite-only
account creation, admin-assisted password recovery, TOTP two-factor with backup codes, a
new Admin → Security policy page, a Passkeys UI stub, and first-admin bootstrap for a
genuinely fresh deployment — plus a full pass aligning the Admin portal's Users/Security
pages to the design that drove this work.

### Added

- **Per-account login rate limiting and lockout** (M1) — configurable attempts-before-lock and lock duration, with "attempts remaining" copy and a dedicated locked-out screen; unknown emails never reveal a count or lock, avoiding an account-existence leak.
- **Session tracking + self-service password change** (M2) — `auth.py` mints a per-login session id embedded as a JWT claim; Settings → Security/Active sessions lets a user change their password, sign out one session, or sign out everywhere else without invalidating the JWT signature itself.
- **Google OAuth sign-in and invite-acceptance** (M3, `uvalu/oauth.py` new) — Streamlit's native `st.login()`/`st.user` wired to a provider list driven by `secrets.toml`; identities are keyed by `(issuer, subject)` so one account can hold a password and multiple providers at once. Self-service signup is gone — accounts are created only via a one-time `?invite=<token>` link.
- **Admin-assisted password recovery** (M4) — a "Send password reset" row action generates a one-time, 24-hour link (no outbound email exists, so an admin relays it manually, the same pattern already used for invites).
- **TOTP two-factor, backup codes, and a new Admin → Security page** (M5) — QR + manual-key enrollment, 10 single-use backup codes shown once, a session-state-only login challenge (never written to the session cookie), "remember this device" for 30 days, and a new password/2FA/rate-limit/identity-provider policy page for admins. The Users table gains Sign-in and 2FA columns plus "Reset two-factor"/"Sign out all sessions" row actions.
- **Passkeys UI stub** (M6) — Settings and Admin → Security render the design's Passkeys row (PHASE 3 badge, disabled controls); no WebAuthn implementation behind it yet, per the plan's own scoping.
- **First-admin bootstrap** — `bootstrap_admin_from_env()` (`ADMIN_EMAIL`/`ADMIN_PASSWORD`) and `scripts/create_admin.py`, a break-glass CLI, since removing self-service signup left a genuinely fresh deployment with no way to create the first account.
- Advisory, non-blocking password-strength indicator in the Change/Set-password dialogs.
- `docs/design/Uvalu Auth.dc.html` — the 16-frame mockup this branch's UI was built from.

### Fixed

- Admin Security page: cards used Streamlit's native border/radius instead of this app's `var(--line)`/12px-radius/shadow treatment (a stray white border in a real-light-theme session); the left nav and header scrolled away on a tall section instead of staying pinned (`position:fixed`, since Streamlit's own `flex:1 0 0%` default breaks `position:sticky` here).
- Closed 4 gaps between the Auth mockup and the shipped screens: login/lockout error styling, missing wrong-password field highlighting, unconfigured-provider button treatment, and invite/reset screens hardcoding "8 characters" against the real (admin-configurable, 12-char) minimum.
- Several native-widget color leaks (search bar / Role select border, Security's toggles, segmented controls) where Streamlit's real theme showed through this app's own dark tokens, plus an incomplete earlier fix for the "Allowed email domains" field's background.
- Security page: segmented controls (Require 2FA, Grace period, Session lifetime) and sliders now share one consistent control width; row heights, vertical text/control centering, and header padding aligned to the Users table's own values; small controls (toggles, status badges) centered in their column instead of sitting flush-left.
- Users table: the Sign-in column ("Password") rendered 8px off-center against every other cell — two CSS rules for exactly this bug already existed, but their selectors still targeted the columns' old positions from before the Sign-in/2FA columns were added to the table.

### Docs

- `docs/backend-feature-gaps.md`, `docs/architecture.md`, `docs/configuration.md`, `.env.example` updated for the bootstrap path and the deliberately-deferred per-IP rate limiting (no reliable client IP is available in this deployment today).

---

## [1.7.0] — 2026-09-12

### Added

- **Valuation & risk accuracy audit** (`tools/valuation_audit.py`, `docs/valuation_audit_plan.md`). A standalone tool, not wired into the app, for catching the class of bug this release's `NAITR.AS`/`SNBN.SW` fixes came from — before a screenshot has to surface it. Runs `screener.compute_scores` over the full cached fundamentals universe and applies a documented, versioned check catalog: an implied-P/B floor (re-asserting `PTB_SANITY_FLOOR`), a net-income cross-validation (`trailingEps × sharesOutstanding` vs. `netIncomeHistory`, catching a corrupted EPS even when P/B looks normal), `sharesOutstanding == 0` sanity, zero-volume/`fv_basis_thin`-vs-Strong-Buy and `Decision`/`veto` consistency (regression sentinels for the Stage 6 rules in check form), fair-value/price ratio outliers, and dividend-yield sanity. Findings aggregate per ticker, tier by severity (critical/notable/informational), carry the algorithm's own `fv_dark_reasons`/`decision_reason`/`veto_reason_str` explanations, and diff against a persisted suppression/history log (`.cache/valuation_audit_log.json`) so a triaged finding doesn't resurface until its disposition changes. Detection only — no automatic fixes; a human decides fixed / documented-gap / dismissed-false-positive via `--dispose`. `CONTRIBUTING.md` now asks for a run before committing a change to `_fair_value_models`/`compute_scores`/the Stage 5/6 rules.
  - Building it surfaced two things the design pass didn't catch: the net-income check's ratio test collapsed toward zero-noise whenever `trailingEps` or `sharesOutstanding` was near zero (129 of 235 raw hits on the first real run were this artifact, fixed with two coverage exclusions); and its `NAITR.AS` regression sentinel caught a real pending-fetch placeholder row from another running app instance's background fetcher, taught to recognize and skip that shape rather than false-alarm.

### Fixed

- **Spurious Strong Buy on an untraded instrument, and Stage 6 catches up with FV-5's thin-basis flag.** `NAITR.AS` (New Amsterdam Invest N.V. *treasury shares*, a near-untraded secondary listing sharing the company's market data with its real, actively-traded `NAI.AS` line) scored a "Strong Buy" with a +99.7% margin of safety and a 562.5% dividend yield — all downstream of a corrupted €0.04 price on a listing with `averageVolume == 0` and only one fair-value sub-model (a lone book-value fallback, `fv_basis_thin`).
  - `screener._liquidity_score`: a *confirmed* zero `averageVolume` (the ticker genuinely hasn't traded) now scores worst-case (0/10) instead of sharing the neutral 5.0 treatment a merely-*unreported* volume gets.
  - `screener.compute_scores`'s `_hard_veto` gains a new condition: confirmed zero average volume forces Avoid, same as the existing D/E / FCF / trend / dividend-cut vetoes. `uvalu.components.veto_reason_str` and the Analysis page's "Hard-veto checks" panel surface it alongside the others.
  - Stage 6 decision: a `fv_basis_thin` fair value (FV-5, shipped 1.6.0 — fewer than `MIN_FV_MODELS` independent sub-models back the composite) can no longer reach `Decision == "Strong Buy"`; it falls through to Monitor on score instead. This was FV-5's "composite-score asterisk," explicitly deferred at the time as a separate Stage 5/6 proposal — not a hard veto, since a weakly-corroborated fair value isn't a red flag on its own, just unconfirmed.
  - `screener.decision_reason` gained the matching gate string ("the fair value rests on too few independent models to confirm a BUY").
- **Spurious Strong Buy on a per-share fundamentals outlier.** `SNBN.SW` (Swiss National Bank — only 100,000 shares outstanding against a genuinely enormous balance sheet) scored a "Strong Buy" with a >CHF 6M composite fair value against a ~CHF 3,140 price. `bookValue`/`trailingEps` were legitimate but astronomically large per-share (the National Bank Act caps the dividend shareholders receive, so market price never scales with book value/earnings the way standard equity models assume), and both of the row's two live fair-value models (`pe_fair_value`, `pb_fair_value`) were built on that same implausible per-share basis.
  - New `screener.PTB_SANITY_FLOOR` (0.02): `_fair_value_models` now holds Graham, PE Fair Value, and the Book value model dark, any sector, when `Price / bookValue` falls below it — `bookValue` and `trailingEps` share the same `sharesOutstanding` basis for a row, so an implausible implied P/B taints both. Deliberately P/B-only, not a symmetric P/E floor: a low trailing P/E alone is too noisy a signal (real, legitimate Strong Buy rows — `TPG0.DE`, `ALWEC.PA` — have implied P/E well under 2 from ordinary earnings volatility, and would have been broken by a P/E-side floor).
  - Calibrated against the full 7,859-ticker cached universe: a controlled before/after diff changed exactly one row; the lowest P/B among legitimate current `Strong Buy` rows sits at ~0.11, a 5×+ margin above the floor.
  - New `fv_dark_reasons` code `implausible_book` ("price too far below book value to trust") so the drawer's "Six-model fair value" ladder explains the gap instead of showing a bare dash.
  - `docs/data-contracts.md` also records a related, distinct, currently-unfixed case (`LISPE.SW`, a Lindt & Sprüngli participation certificate whose cached fundamentals were contaminated by its sibling registered share) and why closing it needs cross-ticker company-identity data (`ISIN`) the app doesn't reliably have.
- **Dashboard Holdings table: "Margin of safety" column header wrapped to two lines.** Its grid column was only 82px wide — too narrow for the uppercase, letter-spaced label at 10px. Shortened to **"MoS %"**, the abbreviation already used everywhere else in the app (the underlying DataFrame column, the drawer, the Screener sort key).
- **Silent portfolio price-fetch failures.** yfinance's per-ticker `fast_info` fallback can return every field as `None` (a rate limit or outage on that endpoint, unlike the batch download, doesn't raise) — a rate-limited fetch and a genuinely delisted ticker looked identical, surfacing downstream only as a blank "No daily price data available" with nothing in the logs to explain why. `prices.fetch_prices` now logs one summary warning per call when the fallback ends the round with no price for one or more tickers.
- **Screener loading skeleton didn't match the real filter bar/header.** The cold-cache skeleton (`components.skeleton_filter_bar_html`, `screener.py`'s loading branch) rendered shorter/uneven shapes than the real widgets, so the filter panel visibly grew and the six Search/Signal/Sector/Market/etc. shimmer bars sat at an uneven "staircase" of heights instead of one level row; the column-header's bare-markdown labels also hit the same "stColumn under-reports a raw markdown block's height" bug already fixed elsewhere in this file, so the row divider pulled up right underneath overlapped the header text. `scr_filter_panel` is now pinned to the real panel's measured 98px height, all six shimmer bars are a uniform 40px, and the header's skeleton-only columns get a matching `min-height` — confirmed live via `getBoundingClientRect` on a cold-cache reload, with zero change to the already-correct loaded state.

### Changed

- **Dashboard Holdings table's last column now shows total P&L instead of today's price move.** The "Today" column (daily % change) is replaced by **"P&L"** — each position's unrealised gain/loss in € (`current_value − purchase_value`, excluding dividends; same formula as the Portfolio page's "Unrealised P&L"). Rows now sort by that figure, biggest gain first, biggest loss last, instead of by position value.

---

## [1.6.0] — 2026-09-10

### Fixed

- **Fair-value coverage — DDM and EPV no longer vanish for trough-earnings payers** (`docs/valuation_fv_coverage_plan.md`, FV-1 … FV-8 — the full plan).
  - **FV-1:** the DDM payout ramp (`screener._ddm_weight_factor`) is fed by a new `screener._payout_signal(row)` instead of the raw `payoutRatio`. yfinance's reported ratio divides by trailing GAAP net income, so a loss-making or freshly-demerged payer gets an absurd (1.4×, 7.7×) or null value that silently zero-weights **both** DDM variants. `_payout_signal` trusts the reported ratio only inside `[0, 0.95]`, then falls back to `cashPayoutRatio` (DPS·shares / FCF), then to `1 / dividendCoverage`. In the reference portfolio this brings both DDM models back for NEXI.MI, SYENS.BR and LIGHT.AS (previously composite = the lone haircut analyst target) while correctly leaving MELE.BR / BPOST.BR dark. The dimension is recorded as a new `payout_source` column; the dividend **risk / sustainability** scores are unchanged (they still read raw `payoutRatio`).
  - **FV-2:** `screener._normalised_ebit` uses an order-statistic estimator — the median at exactly 3 EBIT years, a symmetric trimmed mean (drop min + max) at 4+ — instead of a plain mean. A single one-off writedown year (e.g. −€19.8bn) was dragging a 4-year mean negative and making EPV refuse the stock outright; it is now trimmed out. (A MAD-based rule was tried first and reverted — on 3–4 point windows it flagged a fast grower's newest, most-relevant year as the "outlier".)
  - `screener._row_is_scorable`'s DDM branch mirrors the new payout-signal chain, so a payer valuable only via its cash payout is no longer wrongly parked on the 24h TTL.
  - **Self-review pass.** A multi-agent code review of the branch turned up ten correctness issues, all fixed here: `_payout_signal` no longer trusts a provider `payoutRatio` of exactly `0.0`; the EPV net-debt term is taken from `totalDebt − totalCash` when the EV was reconstructed (a multi-class `marketCap` leg was injecting phantom debt → false `epv_negative`); the FV-8 sector match uses the resolved sector; the DDM `DDM_MIN_SPREAD` guard clamps instead of dropping the model and now also covers the multistage explicit phase; `_normalised_ebit`'s MAD trim was replaced (it discarded a fast grower's newest year); `fv_model_count` collapses the two DDM variants; the thin-payload heal and the two-lane backfill cover the book-value-only shape; banks get a P/B anchor; and the ladder's "why dark" strings are now authoritative rather than re-derived in the UI.
  - **FV-7:** the DDM's growth rate `g` is now the true DPS CAGR (`_dgr_estimate` → `true_dgr`, else the `earningsGrowth` proxy) — the same figure TER and the dividend scores already use — instead of the raw, noisy `earningsGrowth`. Names whose `earningsGrowth` was a wild TTM number (2–5×) no longer have their DDM pinned to the growth clamp ceiling (e.g. SOLB.BR fair value 77 → 20, back in line with the other five models).
  - **DDM stability guards (FV-7 companions).** A Gordon model collapses as the discount rate approaches the growth rate; feeding the real DPS CAGR makes low-beta payers hit that regime often. `_ddm_single` / `_ddm_multistage` now **clamp `g` down** to `WACC − DDM_MIN_SPREAD` (3 pp floor on the denominator) — the model keeps contributing with a conservative growth assumption rather than dropping out silently for every beta < ~1 payer — and `_ddm_multistage` caps its explicit-phase `g_high` the same way so those terms can't compound above the discount rate. The composite sanity clamp (`FV_SANITY_MULT`) counts the two DDM variants as **one** corroborating vote so a twin blow-up can't defeat it (RI.PA fair value 121 → 90; NEXI.MI now correctly clamps to the model median).
  - **FV-4:** the EPV model's enterprise value is now `screener._enterprise_value(row)` — the provider's `enterpriseValue` when positive, otherwise reconstructed as `(marketCap or Price × shares) + totalDebt − totalCash` from three newly-fetched balance-sheet fields (`totalDebt` / `totalCash` / `marketCap`). yfinance frequently drops `enterpriseValue` on a partial payload (14% of the screened universe) while keeping those legs, which used to kill EPV outright. A per-share EPV that comes out ≤ 0 (net debt exceeds capitalised earnings power — routine for leveraged names and REITs) now sets an `epv_negative` flag instead of just disappearing; `ev_source` records `provider` / `reconstructed` / `none`. Existing caches gain the reconstruction after their next fetch cycle populates the new fields.
  - **FV-3:** two fallback fair-value models — **book value** (`bookValue` × winsorized sector-median `priceToBook`, `screener._sector_pb_medians`) and **FCF value** (`freeCashflow` × 15 − net debt, per share) — now join the composite **only for a stock where none of Graham / PE / EPV could be computed**, i.e. a genuine loss-maker whose fair value would otherwise be a lone haircut analyst target. A single live earnings anchor leaves both dark, so normally-valued names are unchanged. Weights are 0.10 each, outside the six-model sum; new `pb_fair_value` / `fcf_fair_value` columns. The drawer / Analysis "Six-model fair value" ladder still shows six rows — a fired fallback replaces the first dark Graham/PE/EPV row and is relabelled "Book value" / "FCF value" (`components.six_model_ladder_rows`), with a caption. `_row_is_scorable` now accepts `bookValue > 0` or positive `freeCashflow` + `sharesOutstanding` on their own. In the reference portfolio this lifts NEXI.MI (composite → 4 live models) and BPOST.BR off analyst-only composites.
  - **FV-5:** new `fv_model_count` (how many *independent* sub-models fed the composite — `ddm` + `ddm_multistage` count once as one Gordon family, and Graham + PE count once when the EPS was reconstructed from `trailingPE`) and `fv_basis_thin` (`compute_scores`: has a fair value but `fv_model_count < 2`) surface a real-but-weakly-corroborated composite, distinct from `data_thin` (no composite). Any scorable-but-thin row is re-fetched on the 3 h short TTL, and `backfill_thin_rows_from_screener_lane` swaps in the screener lane's row when it has more live models — so a book-value-only degraded payload no longer sticks for a day or diverges between the two fetch lanes.
  - **FV-6:** the drawer / Analysis "Six-model fair value" ladder now explains itself. Each dark row shows a short reason in place of the empty bar ("no positive EPS", "net debt > earnings", "no enterprise value", "not a dividend payer", "discount rate ≈ dividend growth", "n/a for this sector", …) with the full phrase on hover; a **"basis · N of 6 models"** line sits under the composite, amber and flagged "lightly corroborated" when `fv_basis_thin`; and a single caption reconciles the FV-3 book/FCF substitution and the −10% analyst-target haircut so the printed rows match the composite (`components.six_model_ladder_caption`). `fair_value_ladder` gains `reasons` / `basis_count` / `basis_thin` params. The reason codes are emitted authoritatively by `_fair_value_models` (`fv_dark_reasons`, built where the model guards live); `components.six_model_ladder_reasons` only formats them, so the tooltip can't drift from the actual reason a model is dark.
  - **FV-8:** the earnings-anchored models are **skipped for NAV-driven sectors** — Graham + EPV for `Real Estate` and `Financial Services`, plus P/E for `Real Estate` (`_GRAHAM_EPV_SKIP_SECTORS` / `_PE_SKIP_SECTORS`), matched on the **resolved** sector (`sector_for()`, so a provider-null REIT like RET.BR still matches). A REIT books IFRS fair-value revaluation gains in EPS (so EPS and any P/E on it swing ±50% y/y); banks and insurers have no operating EBIT. The book-value model fires for these sectors as a **primary anchor** (not just a loss-maker fallback), so a REIT values off P/B + DDM + analyst and a bank off P/E + P/B + DDM + analyst. `Utilities` are **not** affected (regulated, stable EPS, a real EBIT). Reference portfolio: AED.BR fair value 92 → 62 (was dragged up by a €131 Graham / €131 P/E on revaluation-inflated EPS); every held REIT now reads against ~1× NAV instead.

---

## [1.5.1] — 2026-09-09

### Fixed

- **Portfolio-risk colours are now consistent between the Dashboard and the Risk page.** The Risk page's composite-score gauge used a hand-picked `< 40` / `< 70` colour split (`uvalu.components.score_color`) that didn't line up with the algorithm's own band edges — so a score of 26–39 was labelled **"Moderate risk"** but the ring and label were painted **green**, and the same score showed **amber** on the Dashboard. `score_color` now derives its cut-offs from the new single source of truth `risk.RISK_BANDS` (`risk.risk_band()`): green only for *Low* (≤ 25), amber (`#C98A3A`) for *Moderate* / *Elevated*, red (`#A32D2D`) for *High* / *Critical* (amber→red at 70). Both screens now render one score's meter through the shared `uvalu.components.risk_score_meter_html`, and `score_color` is theme-aware (legible label text on the dark card).
- Dashboard's "Conviction & risk" card now shows the exact band word from `risk.RISK_BANDS` (Low / Moderate / Elevated / High / Critical) instead of collapsing everything above *Moderate* into one "Elevated" bucket.
- Risk page: the per-metric band labels (beta, volatility, max drawdown, Sharpe) are now tinted low/moderate/high via `risk.band_tone()` instead of rendering in flat grey.

---

## [1.5.0] — 2026-09-06

Two independent workstreams: the "Loading Patterns" design rollout and a new
structured logging system (`uvalu/logkit/`).

Implements the "Loading Patterns" design concept (Claude Design handoff,
`Loading Patterns.dc.html`): a small shimmer/spinner pattern library, applied
consistently across every remaining page-load loading state in the app —
including two that used to genuinely delay a page's first paint.

### Added

- `uvalu/components.py`: `skeleton_kpi_card_html`, `skeleton_holdings_row_html` / `skeleton_holdings_table_html`, `skeleton_chart_html`, `skeleton_text_html`, `spinner_html`, `refresh_spinner_inline_html`, `refresh_top_bar_html` — shimmer/spinner primitives matching the design's shapes, built on the existing `.uv-skel-bar` shimmer treatment plus two new keyframes (`uvSpin`, `uvRing`) and a top-of-viewport sweep (`uvBar`) in `uvalu/styles.py`.
- Dashboard: the Holdings table and the "Avg margin of safety" KPI tile previously fell back to a bare "No screener data available"/"—" the moment the page loaded before the `PORTFOLIO_FETCH` background lane finished scoring a held ticker (most visible right after adding a new position). They now show the matching skeleton shape instead and poll until real rows arrive, the same cold-cache idiom the Screener page already used (`loading_skeleton_html`) but shaped like this table's own grid.
- Dashboard / Portfolio / Risk: a timer-triggered price refresh (`price_autorefresh`) now shows a slim non-disruptive top-of-page sweep for that one rerun instead of the page just silently repainting, via `uvalu.ui.consumed_tick`.
- Topbar price-freshness dot (`uvalu/shell.py`) now pulses (`uvRing`) while the feed is genuinely live — static for Delayed/Feed stale/Market closed, so the animation itself signals "still updating".
- Screener: the "🔄 Updating data… N/M tickers" plain-text caption shown above already-visible results while a background fetch runs is now the same top-of-page sweep used everywhere else, instead of a persistent text banner.
- **Portfolio's value-history backfill no longer blocks the page.** Loading Portfolio with missing/stale `value_history.json` used to show a blank page behind `st.spinner("Updating value history…")` until the full yfinance backfill finished. It now runs in a background thread (`portfolio.ensure_value_history_fresh`) and the page renders immediately; Dashboard's value-over-time chart (the only consumer of that data — Portfolio dropped its own history chart in an earlier redesign) shows `skeleton_chart_html` and polls until the backfill lands. Either page can now trigger the backfill, whichever is visited first. Also retires a dead "click **Rebuild history**" hint that pointed at a button removed in that same earlier redesign.
- Analysis/Stock Detail's 1Y price chart no longer re-fetches from yfinance on every render — cached for an hour, with `skeleton_chart_html` shown in place of the old `st.spinner` on a genuine cache miss.
- Fixed a flex-gap bug in `refresh_top_bar_html()`'s four call sites (Dashboard/Portfolio/Risk/Screener): the sweep is `position:fixed` (zero layout height) but its own element-container still ate a full row-gap in the page's vertical block, pushing that page's heading down by that amount for as long as the sweep was showing — most visible on Screener, where a background fetch can run for tens of minutes. Fixed with the existing `uv_hidden_util` container convention (`uvalu/shell.py`'s topbar CSS injection uses the same trick).
- **`uvalu/data.py`'s `load_portfolio_risk()` is now non-blocking.** It's a network-bound call on a cold/stale cache (5y OHLC per holding + a Ken-French factor download) that used to run synchronously with no placeholder — gating the Risk page's *entire* render (not even the title showed) and silently stalling Dashboard's Conviction card plus everything below it (Holdings/Sector allocation/Dividends/Top movers). It now returns `None` while computing in a background thread; both pages render their real layout's shape immediately (skeleton gauge/metrics/factor-breakdown/holdings-table on Risk; a skeleton Conviction card and Sector-allocation/Dividends placeholders on Dashboard) and poll until the report lands.
- Screener/Watchlist's cold-cache loading state now shows the real filter-bar and column-header shapes (not just a generic shimmer card), so there's no layout shift when real rows replace it. Portfolio's Overview KPI strip and Open/Closed/Dividends previews get the same skeleton treatment while the `PORTFOLIO_FETCH` lane is cold.
- Fixed four spacing bugs found right after the skeleton work above landed: Screener's filter-panel-to-results-table gap was collapsing to 0px in both the loading and loaded states (a stale `-16px` CSS hack band-aiding a phantom-sibling gap — same `uv_hidden_util`-shaped root cause as the `refresh_top_bar_html()` fix, now fixed at the source instead); Watchlist's loading-state caption had no padding, sitting flush against its card instead of aligned with the header/rows below it; and the new skeleton-row helpers (Screener/Watchlist/Portfolio's `skeleton_rows()`, Risk's `skeleton_risk_holding_row_html()`) weren't fully replicating the padding/row-gap CSS every real row already has — in Screener/Watchlist/Portfolio's case the shared CSS rule's selector didn't even match any of their actual container keys, so it silently never applied at all.

### Added — structured logging system (`uvalu/logkit/`)

The app previously logged nothing beyond ~23 stray `print()` calls and
swallow-everything `except` blocks. `uvalu/logkit/` adds structured JSON logging
to a colorized terminal and a rotating `logs/uvalu.log`, driven by one config
file (`logging.config.json`). See [docs/logging.md](docs/logging.md) for the
record schema and [docs/archive/logging-implementation-plan.md](docs/archive/logging-implementation-plan.md)
for the rollout.

- **Pipeline** — stdlib `logging` with an async `QueueHandler` → `QueueListener`
  (non-blocking on the caller). One JSON object per line, frozen v1 schema
  (`timestamp` UTC/ms, `level`, `service`, `module`, `correlation_id`,
  `user_id`, `message`, `metadata`). Colorized key=value console when stderr is
  a TTY. Config hot-reload on a 5 s mtime poll for `level` / `per_logger_levels`
  / `sampling` / `stack_traces`.
- **Correlation ID** — one UUID per Streamlit script run (`begin_run()` in
  `app.py`), propagated into every background worker: all four raw
  `threading.Thread` sites (screener fundamentals fetch, off-thread universe
  re-score, risk-report compute, value-history backfill) now go through
  `logkit.spawn()`, which copies the `contextvars` context and logs any crash.
- **User identifier** — `sha256(email)[:16]`, the same pseudonymous hash
  `portfolio.py` / `settings.py` already use for on-disk directory slugs.
- **Redaction** — a filter scrubs passwords, JWTs, `AUTH_SECRET` /
  `ENCRYPTION_KEY`, Fernet tokens, bcrypt hashes and raw emails (→ `user:<hash>`)
  from the message, the `extra` metadata, and rendered stack traces.
- **What's logged** — auth events (login ok/failed + reason, session
  restore/revoke, logout), authorization denials, every data mutation
  (portfolio CRUD, watchlist, user administration, backups — never a money
  amount), config changes (per key, `old`→`new`), external-call timing
  (yfinance / stockanalysis batches: endpoint, `latency_ms`, `status`,
  `retries`), background-job lifecycle (`job.start` / `job.ok` / `job.failed`
  with counts), page-render telemetry (INFO on navigation, DEBUG on re-render),
  and previously-silent data-read failures (`storage.read_failed`).
- **Hardening** — recurring exceptions are grouped by a 6-hex fingerprint and
  deduplicated; high-volume per-ticker fetch progress is sampled to 5%;
  `sys` / `threading` excepthooks catch anything that escaped; the bounded
  queue blocks WARNING+ but drops-and-counts INFO/DEBUG when full;
  `RotatingFileHandler` + a retention sweep cap `logs/` on disk.
- **Config** — `UVALU_ENV` (`development` | `staging` | `production`) added to
  `.env.example`; controls `metadata.environment` and prod stack-trace
  redaction.

---

## [1.4.0] — 2026-09-02

Blank fair-value ladders on the Dashboard / Portfolio / Risk screens for a few
holdings (AED.BR, CPINV.BR, FGR.PA): a partial Yahoo payload raised no error,
so the row was cached for a full day with every fair-value model gated off. The
fix recovers what it can from the row it has, retries what it can't on a short
TTL, borrows a complete row from the other fetch lane, and labels the rest.

### Fixed

- Dashboard / Portfolio / Risk: holdings that showed a blank fair-value ladder and margin of safety (a `—` next to a `MONITOR` badge — seen on AED.BR, CPINV.BR, FGR.PA) now get a real valuation. Root cause was a partial Yahoo payload — `trailingEps` / `targetMeanPrice` / `enterpriseValue` / `payoutRatio` all missing — that raised no error, so `_fetch_one` cached it and stamped a full 24 h TTL; every one of the six fair-value models then gated off and `fair_value` came back `None`, but the row still scored (the MoS sub-score falls back to a neutral 50) so it read as `MONITOR`. The fix:
  - **WP-B** — a missing `trailingEps` is recovered from `trailingPE` (`Price / trailingPE`, only for a sane P/E in `_PE_DERIVE_BAND` and only ever a positive EPS) so Graham Number and PE fair value can run. Done in `screener._fetch_one` for new fetches **and** in `compute_scores`, so a row already cached without an EPS heals on the next score rather than the next fetch. Flagged on the row as `trailingEps_derived`.
  - **WP-A** — a fetched row that has a price but still can't feed any fair-value model (`screener._row_is_scorable`) is retried a couple of times in-loop, then cached on a short `CACHE_TTL_SHORT_HOURS` (3 h) TTL instead of 24 h, so a degraded payload self-heals on the next fetch cycle. A symbol that returned no price at all is left alone (retrying can't fix a delisting).
  - **WP-C** — `_load_portfolio_screener_data` runs `screener.backfill_thin_rows_from_screener_lane`: an unscorable portfolio-lane row is replaced by the `SCREENER_FETCH` lane's row for the same ticker when that one is scorable and no older, so a held ticker never shows a fair value on the Screener page and a blank ladder on the Dashboard.
  - **WP-E** — `apply_live_mos` adds `data_thin`; the Dashboard Holdings ladder shows a "fv pending" hint (not a bare `—`) for a row with no fair value because its fundamentals record came back incomplete.

### Documentation

- `docs/data-contracts.md` — the Fair value section now covers the scorable-row requirement (`screener._row_is_scorable`), the short-TTL retry on a thin fetch, the cross-lane backfill, and the `data_thin` UI hint. `tests/test_data_contracts.py` gains a check that the two fetch lanes agree on whether a held ticker has a fair value.

---

## [1.3.0] — 2026-09-01

Data-integrity pass (WP-DQ1…DQ10) from a review of the Dashboard / Risk /
Portfolio screens against the app's own numbers: the same portfolio no longer
shows two risk scores, the Holdings ladder's price / fair value / margin of
safety reconcile, sectors and hard-veto state agree across every screen, the
price-freshness indicator tells the truth, and the concentration / risk-
contribution figures measure what their labels claim.

### Documentation

- `docs/data-contracts.md` — the cross-page invariants (price freshness, margin-of-safety reconciliation, one sector source, the three-state signal badge, position vs sector HHI, a single portfolio risk score, variance-based risk contribution), with `tests/test_data_contracts.py` as the regression layer that checks the screens actually agree (WP-DQ10).

### Fixed

- Risk page: **"Contribution to risk"** is now percent contribution to portfolio variance — `wᵢ · (Σw)ᵢ` with `Σᵢⱼ = σᵢσⱼρᵢⱼ`, using each holding's own volatility and its correlation to the rest of the book — instead of `weight × |beta|`, which ignored idiosyncratic vol entirely and buried a 53%-vol / 0.39-beta name near the bottom of the list. Falls back to `weight × |beta|` (with a caption saying so) when there isn't enough correlated return history. No change to the composite risk score (WP-DQ9).
- Screener: a blended fair value more than 2× the price (`FV_SANITY_MULT`) that only one of the six models agrees with is clamped to the models' median (floored at the current price) — one runaway model (a DDM with WACC barely above g, a stale REIT NAV) could otherwise drag the weighted mean to +120% on a name with no model support. New `fair_value_clamped` flag; the Analysis page and drawer note when it fires. Individual model values are unchanged (WP-DQ9).
- Analysis page / drawer: a one-line **reason for the current signal** — which gate keeps a name out of BUY (score below threshold, margin of safety below the minimum, no computable fair value), or that Avoid vs Monitor is the composite-score floor, not the margin of safety (`screener.decision_reason`) (WP-DQ9).
- Price freshness: the topbar indicator is driven by the real feed instead of always reading "Live · {wall clock}". It now shows the feed's own `as_of` in market time (CET/CEST) and one of **Live** (all quotes intraday), **Delayed N/total** (some tickers only had a daily close this session), **Feed stale** (served from last-known-good), or **Market closed** — coloured accordingly. `prices.fetch_prices` gained a per-ticker `quote_source` (`intraday` / `eod` / `stale`); `uvalu.data.price_feed_status()` summarises a batch and `_fetch_prices_cached` stashes it for the shell. On the Dashboard Holdings ladder a delayed row's day-change chip is dimmed with a "delayed quote" tooltip (WP-DQ8).
- Signal badge: a holding with no scored screener row (the fundamentals feed returned nothing, or no price) now shows a neutral **"NO DATA"** badge instead of masquerading as **VETO** — the merged `veto` cell was NaN and `bool(nan)` is `True` in Python, so dataless rows painted as hard vetoes. This is what made the Holdings ladder show 6 names "under hard veto" while the Risk page and Dashboard card (which already filtered NaN) counted 5. New `components.is_hard_veto()` is NaN-safe and used at every veto-badge / veto-banner site (WP-DQ6).
- Sectors: a curated `screener.SECTOR_OVERRIDES` / `sector_for()` fallback classifies held tickers the provider leaves null (RET.BR → Real Estate, SYENS.BR → Basic Materials, MELE.BR → Technology, PROX.BR → Communication Services). Applied identically by the Holdings sector tag, the Dashboard allocation donut, the Risk-page enrichment and the Analysis page, so ~a quarter of the book no longer lands in an "Unknown"/"nan" sector bucket and the three screens agree (WP-DQ7).
- Dashboard / Portfolio / Risk: the **margin of safety** shown on the Holdings ladder and in the detail drawer is recomputed from the live quote (`uvalu.data.apply_live_mos`) instead of the fundamentals-cache price snapshot `screener.compute_scores` uses. The ladder rendered a live price, a fair value and a stale-price MoS side by side, so the three didn't reconcile — worst case a holding priced at fair value showing a deeply negative MoS because its cached price was weeks old. `fair_value`, `Value Score`, the sub-score ranks and `Decision` stay on the universe-ranked batch basis; a new `price_stale` column flags rows whose live quote is >10% off the cached price (WP-DQ1).
- Risk page: the **"Sector HHI"** tile now shows an actual sector-level Herfindahl (`Σ sector_weightᵢ²`), not the position-count Herfindahl it had been displaying under that label — for a ~16-name book across 8 sectors that was ~0.07 "Well diversified" when the real sector concentration was ~0.16. The position HHI is unchanged and still feeds the composite risk score (WP-DQ3).
- Risk page: a holding with no sector/country metadata is bucketed as **"Unknown"** instead of leaking the literal string `"nan"` into the concentration labels and flag text (`risk._category_label`, NaN-safe) — matches how the Dashboard sector donut already labels that bucket (WP-DQ3).
- Dashboard / Risk page: both now build the portfolio `RiskReport` through one shared `uvalu.data.load_portfolio_risk()` builder — same enriched frame, hard-veto lookup, target allocation and session cache — so the composite risk score can't differ between the Dashboard's Conviction & risk card and the Risk page gauge for the same portfolio (was ~32 vs ~29; the Dashboard had been calling `assess_portfolio` with none of that context) (WP-DQ4).
- Risk page: the score-gauge caption no longer renders "Moderate risk **risk**" — `composite.label` already carries the "… risk" suffix, the template appended a second one (WP-DQ5).
- Risk page: the **Max drawdown (1Y)** tier word ("Low"/"Moderate"/"High") is now derived from the 1-year drawdown it sits next to, not the 5-year figure — the number said −15% while the label said "High" off the deeper 2022 drawdown. The composite risk score still uses the 5-year drawdown independently (WP-DQ5).
- Dashboard / Screener / Watchlist: the fair-value column and KPI tile are labelled **"Margin of safety"** instead of "Upside" — the value shown has always been `(fair value − price) / fair value`, not raw upside `(fair value / price − 1)`, which differ materially for deep-discount names (WP-DQ2).

### Performance

- Screener: `compute_scores` computes `margin_of_safety` and the `Decision` label with vectorised pandas/NumPy expressions instead of a per-row `df.apply` — bit-identical output, locked by an equivalence test (WP-7). The fair-value models and the composite risk sub-scores stay row-wise (scoring math shared with the risk engine).

---

## [1.2.0] — 2026-08-31

### Performance

Every screen now paints from already-computed data and fills in as background
work lands, instead of blocking the render thread on the screener fetch + scoring
(WP-1…WP-6 of the instant-paint plan).

- **Universe scoring moved off the render thread** — new `uvalu/store.py` (`_UniverseStore`): `_load_all_screener_data()` is now a non-blocking accessor that returns the last-computed per-exchange scored frames immediately and kicks a single background daemon worker when the fundamentals-cache token has moved. The worker runs the `compute_scores` pass **and** the 1–6 live `stockanalysis.com` ticker-list scrapes (`fetch_tickers.py` has no memoisation of its own, so those had been re-running on every render-thread cache miss)
- **Re-score debounce** — `_cache_version()` holds its token steady while a background fetch churns `fundamentals.json`, so a 20–40 min cold fetch triggers ~10 recomputes instead of one per ~20 s cache-file rewrite (`RECOMPUTE_DEBOUNCE_S`)
- **Dashboard / Portfolio / Risk** no longer score the whole enabled-exchange universe just to look up their ~30 holdings — a new `_load_portfolio_scored()` fast path scores only held + sold tickers through the dedicated `PORTFOLIO_FETCH` lane (held tickers on a disabled exchange are covered now too)
- **Version-diffed timed refreshes** — `ui._auto_rerun` / `price_autorefresh` only fire a full rerun when a plain signature (store version, fetch progress, price bucket, portfolio token) has actually changed since the last one, with a `max_idle_ticks` anti-freeze fallback; the dialog-open guard is unchanged
- **Cold-cache loading skeletons** for Screener and Watchlist (`components.loading_skeleton_html` + `ui.poll_while_fetching`) — a still-loading list shows shimmer rows and refreshes itself, instead of a bare "no data" line (Watchlist previously had no auto-refresh at all and looked identical to a genuinely empty watchlist)
- Dropped a dead per-render ~14 MB `fundamentals.json` `json.loads` from the Screener page (the unused `_scr_pf_context` / `open_drawer(pf_context)` path), and made `screener._warm_live_cache` a double-checked lock so two cold-start sessions don't both parse the file

---

## [1.1.0] — 2026-08-30

Valuation + portfolio-risk engine overhaul (WS-1…WS-18): a dedicated market-data
provider, an EUR-consistent quantitative risk engine, and a multi-model fair
value that no longer leans on point-in-time snapshots or sell-side targets.

### Added
- Screener: **multi-year statement history** (`screener._statement_history`) — annual revenue, EBIT, net income, operating cash flow, retained earnings and total assets pulled per ticker on each 24h refresh, groundwork for trend-based vetoes, accrual-aware earnings quality and a normalised EPV (WS-10)
- **`marketdata.py`** — single yfinance wrapper: disk-cached daily price history (`.cache/history/`, incremental tail refetch), dividend payment history (`.cache/dividends/`), and EUR FX rates
- **`scoring.py`** — the shared 0–10 fundamental scorers, extracted from `screener.py` (which re-exports them); the risk engine no longer imports `screener.py`'s private namespace
- **`portfolio_enrichment.py`** — `enrich_for_risk()` builds the frame `risk.assess_portfolio` expects
- Risk engine: per-holding **beta regressed** against `^STOXX50E` (yfinance fallback), realised per-position volatility, and a days-to-liquidate liquidity check
- Risk engine: **true dividend growth rate** from DPS history feeds TER and the dividend scores; dividend-sustainability flag adds a "DPS cut in the last 3 years" check; `IncomeRisk.income_stability` score, wired into the composite
- Risk engine: Fama-French **Developed** 5-factor + momentum set (US fallback), disk-cached with a stale-copy fallback when offline
- Risk engine: historical stress scenarios **replay the held basket's real drawdown** when history covers the window; Monte Carlo is now a block bootstrap re-centred on a CAPM drift
- Risk engine: **drift-vs-target** rebalancing triggers — set a target allocation under Settings → Target allocation and a daily risk snapshot enables sector/name/HHI drift, two-period Sharpe, and rating-transition signals
- Settings → **Target allocation** editor (personal sector / per-name weights + HHI ceiling)
- Settings → Screening & veto rules → **Screening style** (balanced / value / growth / income) — an admin-controlled composite-weight preset threaded through `compute_scores` via `settings.get_score_weights()` (WS-18)
- Screener: **trend-based hard vetoes** (`screener._trend_veto`) — a stock is now vetoed on 3+ straight years of revenue decline, 3 years of negative EBIT, an eroding negative retained-earnings balance, or a dividend cut in the last 2 years while coverage is under 1.5×; surfaced in the drawer/Analysis veto banner and the Analysis "Hard-veto checks" panel (WS-15)

### Changed
- Screener: **PE Fair Value** now uses the stock's own sector-median trailing P/E across the universe (winsorized 6–30×) with a bounded PEG tilt, instead of a flat 15× for every stock; 15× is kept as the small-sample fallback (WS-11)
- Screener: **DDM weight** now ramps continuously with the payout ratio (full across 30–70%, tapering to 0 by 5% / 95%) instead of a hard 5–90% in/out gate — no more fair-value cliff between an 89% and a 91% payer (WS-12)
- Screener: **earnings quality** adds a Sloan accrual ratio `(netIncome − operating cash flow) / totalAssets` alongside the FCF/NI conversion and FCF-history consistency terms (WS-16)
- Screener: **beta** is Blume-adjusted (`0.67 × raw + 0.33 × 1.0`) before it feeds WACC and the market-risk score, de-noising yfinance's trailing single-estimate beta; a beta outside [0.1, 5.0] still falls back to 1.0 (WS-17)
- Screener: each composite sub-score is now a **50/50 blend of its cross-sectional percentile rank and an absolute 0–100 band** (`_blend_ranks` / `_abs_band` / `BLEND_PCT`), so a universe where every stock is overvalued no longer produces a full spread of inflated MoS ranks (WS-14)
- Screener: **default composite weights rebalanced** from `0.30 / 0.18 / 0.22 / 0.15 / 0.15` to `0.24 MoS / 0.22 risk / 0.24 quality / 0.15 momentum / 0.15 dividend` (`screener.W_*` and the `balanced` screening style) — margin of safety now co-leads with quality instead of dominating, and risk is weighted more heavily, so a wide discount can't by itself outvote weak fundamentals; the `value` style keeps the old MoS-led weighting
- Screener: **EPV now capitalises the mean of `ebitHistory`** (`_normalised_ebit`, ≥3yr) instead of a single point-in-time EBIT, so a peak or trough year no longer sets the valuation (review 2.3)
- Screener: **analyst-target weight** cut from 0.208 to 0.130 (freed weight to EPV / Graham) and further scaled down per-stock when the sell-side estimates are widely dispersed (`(targetHighPrice − targetLowPrice) / targetMeanPrice`) or thinly covered (`numberOfAnalystOpinions`) (WS-13)
- All risk metrics computed on EUR-restated price history (was a currency blend)
- Composite score drops the factor slot and renormalises when the Fama-French feed is unavailable, instead of a flat placeholder
- `earnings_quality` blends multi-year FCF-history consistency with the FCF/net-income ratio
- Help page expanded from a column reference into a full in-app guide, with an overview and a section for every page (Dashboard, Portfolio, Risk, Screener, stock details, Settings) alongside the column glossary
- Column reference now documents the Ex-Div Date, Div Date, Sector and Country columns, and their tooltips show on the screener headers

### Docs
- `stock_valuation_algorithm.md` / `portfolio_risk_assessment_algorithm.md` brought fully in sync with the WS-1…WS-18 implementation
- `configuration.md` corrected — stale constant names, the pre-2026 veto list, and composite/risk weight tables that had drifted from the specs; weight and veto tables now reference the algorithm specs instead of duplicating the numbers
- `architecture.md` `formatting.py` entry and the table-density note updated to match the code

### Removed
- `uvalu/formatting.py`: dead `COLUMN_HELP` / `_HINT_WATCHLIST` tooltip dicts and the `fmt_div_flag` / `f_str` helpers (superseded by `help.py`)

---

## [1.0.0] — 2026-07-30

### Added
- Multi-exchange screener covering 750+ stocks across Brussels, Amsterdam, Paris, Milan, Frankfurt, and Swiss exchanges
- 6-stage valuation algorithm: Graham Number, PE Fair Value, EPV, DDM (1-stage & 2-stage), Analyst Target
- Composite score (0–100) with Strong Buy / Monitor / Avoid signals
- Portfolio tracker with live pricing, unrealised P&L, and benchmark comparison (S&P 500, Euro Stoxx 50)
- Dashboard with KPI cards, performance treemap, sector allocation, and top movers
- Realised positions with annualised return (CAGR)
- Dividend history tracking with tax estimate
- 8-stage portfolio risk assessment: concentration, volatility, VaR, factor exposure, stress tests, Monte Carlo simulation
- Multi-user authentication with JWT sessions and role-based access (admin / user)
- Per-user encrypted data storage (Fernet)
- Watchlist across all exchanges
- Admin panel: user management, exchange toggles, backup & restore, Excel import
- Export to Excel (Positions, Sold, Dividends, Watchlist)
- Self-signed TLS for localhost HTTPS
