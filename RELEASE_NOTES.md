# Release notes

What's new in Uvalu, as the app shows it under *What's new*. These notes are
for subscribers: what they'll notice and what it does for them. The full record
of every change, with operator and admin detail, is
[CHANGELOG.md](CHANGELOG.md).

Rules in [CONTRIBUTING.md § Versioning and releases](CONTRIBUTING.md#versioning-and-releases):

- Every release in CHANGELOG.md has a section here, with the same version and
  date. A release with nothing to notice still gets one line.
- Open with one or two sentences on what the release brings you. Say it when
  scores or signals change, and when you need to do something.
- Lead each entry with the benefit, then how to find it.
- Group entries under **New**, **Improved**, **Fixed** and **Removed** only.
- Leave out what subscribers never see: admin and operator tools, hosting,
  backups, test builds, restarts, data versions, internal names.

---

## [Unreleased]

**Clearer currencies and dividend tax by country.** Signals don't change.
If you had set withholding rates per exchange, they moved to the matching
country: check them once in Settings.

### Improved

- **Every amount shows its currency**: prices read "EUR 55.86" or
  "CHF 8.80", and a price in another currency also shows its value in your
  own currency underneath.
- **Dividend withholding by country**: each country starts at its usual
  rate withheld at source, set by where the company is registered (Airbus
  follows the Netherlands rate). Change any rate in Settings, or reset it.
- **Buy and sell prices in the stock's own currency**, converted to euros at
  that day's ECB rate.

- **Add a stock the way your broker writes it**: a ticker like "NOVO B.CO"
  is understood when you add it to your watchlist or record a trade.

### Fixed

- **Swiss holdings valued in euros**: positions on the SIX Swiss Exchange
  are converted from Swiss francs at the latest ECB rate before they count
  towards your portfolio value, gains and risk figures. Portfolios with only
  euro stocks don't change.

## [2026.10.9] — 2026-10-17

**Prices in the right currency, clearer market names, and stress tests based
on European markets.** Signals don't change; your risk score can change
slightly.

### Improved

- **Official exchange names**: the Market filter and stock details now name
  each exchange as it is officially called, such as Euronext Brussels or
  Xetra.
- **Faster screener updates**: new data shows up sooner after a restart.

- **Stress tests based on European markets**: the past-crisis scenarios on
  the Risk page now use the EURO STOXX 50's own falls instead of the
  S&P 500's, so they match the index your portfolio's beta is measured
  against. Your risk score can change slightly; signals don't.

### Fixed

- **Swiss stocks in Swiss francs**: prices and fair values of SIX Swiss
  Exchange stocks are shown in CHF instead of with a euro sign.
- **Fair values on narrow screens**: on the Dashboard the fair value under
  each bar no longer breaks in two in German or Spanish.
- **Watchlist after a restart** says it is loading your stocks, instead of
  asking you to wait for the next screener refresh.

## [2026.10.8] — 2026-10-15

**Easier to read and to use with a keyboard or screen reader, and more
secure.** Signals and scores are unchanged. If you were sent an invitation
before 15 October that you haven't used yet, ask for a new one.

### Improved

- **Easier with a screen reader or keyboard**: pages have proper headings
  and landmarks, a "Skip to content" link comes first when you press Tab,
  and each browser tab shows the page name. Buttons say what they do and to
  which stock ("View Investor AB", "On the watchlist: …"), instead of
  "star" or an icon's code name. Main buttons have a slightly darker green,
  so their text is easier to read.
- **"Mid score" in French, Italian and Spanish** now says "intermediate"
  instead of a word that also means "average".
- **Your sign-in is kept in one place**: only in the session cookie, which
  ends after 24 hours, no longer also in your browser's storage.
- **Charts and loading messages for screen readers**: the value and price
  charts are described in one sentence with their figures, and the
  Screener says when results arrive and how many match your filters.
- **Accessibility statement**: what works for screen readers and keyboards,
  what doesn't yet, and how to tell us (footer › Accessibility).
- **Tables for screen readers**: every table (Screener, Watchlist, holdings,
  positions, dividends and cash activity) is read as a table with column
  headers, and the Screener says which column it is sorted by.

### Fixed

- **Safer Excel exports**: a note that starts with "=" is exported as text,
  never as a formula Excel would run.

- **Clearer labels in Dutch, French, German, Italian and Spanish**: the two
  highest risk bands have distinct names in French, Italian and Spanish,
  "Screened out" no longer sounds like your own Screener filter, and the
  dividend yield column says dividend yield.
- **Dashboard figures that add up**: the value and return cards say what
  they include, and the value chart ends on today's value.
- **Clearer margin of safety**: when the price is far above the model fair
  value, you see "price 2.3× fair value" instead of a large negative
  percentage.
- **Clearer Risk page**: factor ratings, concentration warnings and the
  Sharpe reference read correctly in your number format.

## [2026.10.7] — 2026-10-14

**Signals change.** Fair values no longer jump on a single exceptional year,
and Undervalued now needs the models to agree.

### Improved

- **Fair values look past one-off gains**: the earnings-based models now
  use a company's earnings over the last 3–4 years instead of the latest
  year alone, so a sale or a revaluation no longer makes a share look
  cheap. The Methodology page explains how.
- **Undervalued means more**: a share is only marked Undervalued when the
  valuation models roughly agree and the gap to the fair value isn't so
  large that it points to a data error. When the models disagree, the
  explanation shows their range.

## [2026.10.6] — 2026-10-14

**Signals change.** Uvalu now covers companies on their own home exchange
only, values them in the right currency, and keeps signals steady when a score
only wobbles. Signing in is safer too.

### New

- **A short confirmation when you join**: an invitation now starts with your
  country of residence and three statements to confirm. Settings › Legal
  documents shows what you accepted and when.

### Improved

- **A cleaner list of stocks**: the Screener covers companies from Belgium,
  the Netherlands, France, Italy, Germany and Switzerland on their own home
  exchange. Second listings of foreign companies and shares that don't trade
  are gone, so each company appears once. A share you added or hold yourself
  is still scored.
- **Fair values in the right currency**: when a company reports in another
  currency than its share price, for example a Swiss company reporting in
  dollars, its figures are converted first. If no exchange rate is available,
  the stock page says so and the stock isn't marked Undervalued.
- **Steadier signals**: a stock keeps its signal until its score clearly
  moves past the edge, and an incomplete data update no longer changes a
  signal. The Methodology page explains the rule.
- **Clearer signal names**: "Mid score" replaces "Neutral" and "Screened out"
  replaces "Fails quality screen", and every signal is shown as a model
  signal.
- **Signals stay apart from your own position**: the Risk page's last column
  is now "Position risk", your position's own rating. In the stock preview,
  your shares, value and result are in their own "Your position" section.
- **Privacy notice 1.4**, effective 28 October 2026: it covers the new
  confirmation record and how account security works.

### Fixed

- **Safer sign-in**: two-step codes now count towards the account lock, a
  code can't be used twice, and failed sign-ins no longer show whether an
  email address has an account.
- **Safer sign-in cookies**: other websites can't make your browser send
  them.
- **Names shown exactly as written**: company names, tickers and sectors are
  always shown as plain text.

## [2026.10.5] — 2026-10-11

Bring your portfolio in and take all your data out: restore or bulk-add from a
file, download everything Uvalu holds about you, and delete your account
yourself. Your scores and signals don't change.

### New

- **Restore or add to your portfolio from a file**: in Settings › Import &
  export, upload an Uvalu export — or the export with rows you added — and see
  what it holds before anything changes. Then add the new rows or replace
  your portfolio with the file.
- **Download all your data**: Settings › Privacy › Export my data gives you
  your account details, settings and portfolio in one Excel workbook.
- **Delete your account yourself**: Settings › Privacy › Delete account
  removes your account and data at once, and from backups within 30 days.
- **Privacy, plan and legal documents in Settings**: your privacy contact,
  your free-beta plan, and the terms and privacy notice with their version.

### Improved

- **A cleaner Excel export**: only what you entered — positions, sales,
  dividends, cash and watchlist — with real dates and a short note on every
  column, so you can fill it in and import it again.
- **Links look the same everywhere**: Methodology → now has the link colour.

### Fixed

- **Swiss dividends** without a currency are now counted in Swiss francs, not
  euros.
- The cash activity and dividend log lists line up neatly with their card
  again.

### Removed

- **CSV export buttons** on Portfolio, Cash activity and the dividend pages:
  the Excel export in Settings › Import & export has the same data.

## [2026.10.4] — 2026-10-11

A new logo and a calmer, clearer Uvalu: quieter buttons, model names you can
look up, and exchange codes everywhere. Your scores and signals don't change.

### Improved

- **What's new is written for you**: each update now says what it brings
  you, in plain words.
- **A new Uvalu logo**: two rings for independent valuation models, and the
  lens where they agree — the idea behind every fair value you see.
- **Calmer buttons and navigation**: smaller, quieter buttons, new menu
  icons, and the page you're on is the only one highlighted.
- **Model names you can look up**: the valuation models carry the same names
  as in the Methodology, so you can find how each one works.
- **Exchange codes everywhere**: Portfolio and Risk show BRU, XET or PAR under
  the ticker, like the Screener.
- **Dashboard chart opens on the past year**, so the change you see covers a
  full year.
- **Clearer Risk colours**: a weak risk-adjusted return shows in amber; red is
  kept for a failed quality screen.
- **Easier to read**: the legal pages' tables, the region preview in Settings
  and the sensitivity table on Analysis match the rest of the app.

### Fixed

- On *About Uvalu*, the release notes use the full width of the card, and the
  *What's new* heading no longer overlaps the first release.
- The disclaimer at the bottom of every page uses the full width.
- While a page loads, the legal notes stay at the bottom of the screen
  instead of jumping to the top.
- On the sign-in screen, the legal notes sit at the bottom of the dark panel
  and use its full width.

## [2026.10.3] — 2026-10-10

A clearer, calmer Uvalu: colours tell you at a glance where a stock stands,
and the Screener and Dashboard put what you use most within one click. Your
scores and signals are unchanged. Used to sign in with Google? Ask support
for a password reset link to set a password.

### New

- **Find new ideas faster in the Screener.** Stocks are ranked, exchanges
  show as short codes (PAR, XET, …), and *Hide positions I own* keeps the
  list to stocks you don't hold yet. Stocks without a signal are listed too,
  with their own filter, so nothing is left out.
- **Your portfolio at a glance on the Dashboard.** Your sector mix as a
  compact ring, upcoming dividends with the day they're paid, and *Add
  position* right next to *Refresh*. Click a top mover to see its details.
- **Tables the way you like them.** Settings › *Table density*: compact or
  comfortable rows.
- **Numbers in your own format, explained.** Settings › *Language & region*
  explains each choice, shows a preview, and lets you check you're reading a
  number the right way.
- **See how the model works today.** Methodology shows how many stocks carry
  each signal right now and exactly what each badge means.
- **Read our terms before you sign in**: the legal pages open from the
  sign-in screen.

### Improved

- **Colours that mean one thing.** Margin of safety is green from 15% and
  amber below 0%. Red now only marks a stock that fails a quality screen, so
  it stands out when it matters. Links and small text are easier to read.
- **Scores you can place.** Each score shows its band (for example *Upper
  band · 70–100*). Your average margin of safety counts bigger positions
  more, and each holding shows its result as a percentage of what you paid.
- **Every page reads the same way**: titles and headers have the same size
  everywhere, with the signal details in the line under the title.
- **Portfolio**: all your open positions on the overview, dividends shown
  net and gross, and exports say what's in them.
- **Stock details and Analysis**: the analysis button comes first, the model
  summary rounds off the page, and the sensitivity table is quicker to scan.
- **Your security in one place**: Settings › *Account security* now lists
  your active sessions; your account details are at the bottom.
- **Safer sign-in.** During the free beta you sign in with your password, and
  new accounts are by invitation. Password reset links now expire after 30
  minutes.
- **Updated privacy notice** (beta 1.2): it describes only what the beta
  actually collects. To delete your account, write to privacy@uvalu.app.
- **Clearer wording in Analysis**: fair values are estimates of what a
  company is worth, not forecasts of its price.
- Messages at the top of the page always appear in the same order.

### Removed

- **Settings › Data & alerts**: there's nothing to set any more — prices
  refresh by themselves, every minute while markets are open. The Dashboard
  no longer shows ex-dividend, cut or raise badges.
- The *Implied return* tile in stock details. *Legal & policies* left the
  user menu; you'll find it in the footer and in Settings.

## [2026.10.2] — 2026-10-07

A calmer, more consistent Uvalu: fewer distractions on every page and
tooltips that match your theme. Your scores and signals are unchanged.

### Improved

- **Signal details in one quiet, predictable place.** When signals were
  computed, the price time, the model version and a *Methodology →* link now
  sit in one plain line under the title on the Dashboard, Screener and
  Watchlist.
- **See how selective a filter is.** Each signal filter in the Screener shows
  the share of stocks with that signal, for example *Undervalued 3%*.
- **Dashboard**: the fair-value legend sits right above your holdings, and a
  price above fair value is amber instead of red — red is kept for stocks
  that fail a quality screen.
- **Settings, Methodology, Legal and About work the same way**: a back link,
  a list of sections (a document picker on your phone) and a comfortable
  reading width.
- **Tooltips match your light or dark theme** everywhere, chart labels
  included.

### Fixed

- The *Print or save as PDF* button on the legal pages is visible again.
- The last line of some cards on Methodology and Settings is no longer cut
  off.

## [2026.10.1] — 2026-10-05

Always know which version of Uvalu you're using and what each update brings.

### New

- **What's new, in the app**: the notes of every update. After an update you
  see a short notice once, with a link to what changed.
- **About Uvalu**: click the version at the bottom of any page (or open your
  user menu) to see exactly which version you're on, with a line to copy
  when you contact support.
- **Always on the latest version**: if Uvalu is updated while you're using
  it, you're asked to reload the page.
- **Faster help from support**: error messages include a short reference to
  quote when you get in touch.
