# Implementation plan: align the app with the design reference (October 2026, round 3)

Version 3.1, 11 October 2026 (gaps G01–G09 decided as recommended). Replaces version 2.1 of 9 October, whose steps S01–S29 shipped in v2026.10.3; that version is in git history (`59af1c0`, `654d8e7`).

**Status (11 October 2026).** Implemented on `feature/design-reference-round-3`: S01–S10 and S12, one commit per step (S01–S03 in one commit), full test suite green, each step checked live at 1280px in the dark theme. Not done: **S11 (logo)**, waiting for the logo assets from prompt 1 of `logo-implementation-prompt.md` (open-items D1). Findings while building: S01 also covers outline-button text colour (`--muted`, `--text` on hover) and the popover buttons ("Export CSV"); DR-01 (drawer title) was a measuring error, the title was already hidden; G09 was already met (the commit links only for admins). New strings are drafted in all five translations and unreviewed (fuzzy), like D4.

**Baseline.** The code on `feature/public-release-notes` at `28006ba` (`master` at `85b08bc` plus two commits that change only the footer, the legal text width and release notes). The reference files are the working-tree copies in `docs/design/` from the latest design-project export (not yet committed): `Design reference.md`, `Uvalu.dc.html`, `Uvalu Admin.dc.html`, `Uvalu Auth.dc.html`, `README.md`, plus the new, untracked `logo-consensus-spec.md` and `logo-implementation-prompt.md`. Brand: `docs/uvalu-brand-guidelines.md` v1.3 (already updated in S29; the copy in `docs/design/uvalu-brand-guidelines.md` is older and is not used).

**What changed in the reference since version 2.1.** Compared with the committed copies:
- `Uvalu.dc.html`, `Uvalu Admin.dc.html`, `Uvalu Auth.dc.html`: the text wordmark is replaced by the new Consensus logo lockup (two rings and a lens, SVG, Inter 500) in the top bar, the Admin sidebar and the sign-in panel; new token `--logo-ring` (`#FFFFFF` dark, `#0D1F3C` light).
- Top navigation icons are Material Symbols at 16px: `home`, `monitoring`, `star`, `work`, `shield` (they were inline SVGs in the mockup).
- The beta bar is now drawn as a rounded box: outer padding `8px 28px 0`, box padding `7px 14px`, centred content, `--soft` fill, 0.5px `--line`, radius 8px (decision G01 of 9 October, now in the mockup).
- Admin side navigation icons are 16px (were 20px).
- `Design reference.md`: the beta-bar sentence and the icon sizes (16px in navigation, 20px only for status icons in banners and dialogs).
- `README.md`: the dividends deviations now say "Export" and "keeps the mockup's left-hand width". This disagrees with the mockup (see G02).

**How the assessment was done.** The app (`_dev_entry.py`, dark theme) and the mockups (served from `docs/design/`) were opened at **1280px** in the built-in browser. For each screen a script read the computed font size, weight, colour token, font family and case of every text element in both, and the results were compared by text. Positions and padding were measured with `getBoundingClientRect` where they mattered. Values were then checked against the source (inline styles in the mockups, `uvalu/styles.py` and the page code). The light theme was checked through the token definitions and the source only: switching the app to light needs a stored user setting, which this read-only task did not change. Every step therefore verifies light as well as dark. At **920px** the Dashboard had no horizontal overflow and the beta box kept one line.

---

## 1. Summary

- **12 steps:** 8 small, 4 medium, no large. About 28 hours, roughly 4 working days. S11 (logo) depends on the separate logo-asset prompt in `docs/design/logo-implementation-prompt.md`.
- Most of the reference already matches: all decided items (labels, Data & alerts removal, Settings order, "Margin of safety", amber for negative margins, bands 70/40, P&L column, 24px titles, "← Back to …", No signal in the Screener, brand v1.3 tokens, focus ring, radii, notice order, supporting-page frame) were verified in the code and are listed as Matches.
- The new findings are mostly **shared styling** that Streamlit 1.60's markup now bypasses: button and segmented-control labels render at Streamlit's 14px/400 instead of 12.5px, and inactive top-nav and Admin-nav items render in `--text` instead of `--muted`, because the label sits in a new wrapper `<span>` / `<p>` that sets its own colour and size.
- **Biggest risk 1:** S01 changes the label size of every button and segmented control at once. It touches every screen. Mitigation: one shared rule set keyed on `data-testid` / `data-variant`, nothing else in the pull request, and a screenshot set of all screens before and after.
- **Biggest risk 2:** S05 renames the valuation models in three places. The Methodology names must stay identical to the legal Methodology document (`docs/legal/policies/beta/methodology.md`, § 3), which the app shows on the Legal page. G06 needs your decision first.
- **Biggest risk 3:** S11 (logo) loads or embeds Inter for the wordmark. The rest of the app uses the system font stack. The spec recommends outlined SVG paths (no font load); a live-text lockup would add a Google Fonts request to every page.

Layout differences per screen (Layout rows in section 2):

| Screen | Must match | Should match |
| --- | ---: | ---: |
| Global (top bar, menus, buttons, beta bar, footer, notices) | 4 | 1 |
| Dashboard | 3 | 0 |
| Screener | 0 | 0 |
| Watchlist | 0 | 0 |
| Portfolio (overview, open, closed, dividends, cash) | 3 | 0 |
| Risk | 1 | 0 |
| Analysis | 3 | 0 |
| Stock drawer | 1 | 0 |
| Settings | 3 | 0 |
| Methodology | 0 | 0 |
| Legal | 3 | 0 |
| About | 1 | 0 |
| Sign-in and invitation | 0 | 0 |
| Admin | 1 | 0 |
| **Total** | **23** | **1** |

## 2. Assessment

Notation: `--x` is a CSS token. "Mockup" is `Uvalu.dc.html` unless stated. `MUT` = `--muted`, `TXT` = `--text`. Layout rows give the level and the mockup value first, then the code value. Per screen the most visible differences come first, then the rest, then what was checked and matches. Items decided on 9 October (gaps G02–G36 of version 2.1, implemented in S01–S29) are not reopened; where the mockup still shows the old variant, the row says "decided".

### 2.1 Global elements

| ID | Item | Category | Code location | Mockup value | Code value |
| --- | --- | --- | --- | --- | --- |
| GL-01 | Button labels | Layout · Must match · typography | Streamlit buttons app-wide; no shared rule in `uvalu/styles.py` (single overrides exist, e.g. `.st-key-scr_more`, `.st-key-pf_open_ov_all`) | 12.5px; primary weight 500, secondary/tertiary 400; padding 8px 13–14px; 16px icon with 7px gap | 14px/400 (Streamlit default `<p>` inside the button) |
| GL-02 | Button height | Layout · Should match | same | ≈ 33px (8px + 16px icon + 8px + border) | 40px (Streamlit min-height) |
| GL-03 | Inactive top-nav links | Layout · Must match · colour | `shell._topbar_css`, `.st-key-uv_topbar_nav a … p { color: inherit }` | `--muted`, active `--text` on `--soft` | All links `--text`: Streamlit 1.60 wraps the label in a `<span>` that sets its own colour, so `inherit` picks up `--text` |
| GL-04 | Top-nav icons | Layout · Must match | `app.py` lines 112–116 (`st.Page(icon=…)`), shown by `shell.render_topbar` | `home`, `monitoring`, `star`, `work`, `shield` (Material Symbols outlined, 16px) | `dashboard`, `search`, `star`, `business_center`, `monitoring` (16px) |
| GL-05 | Beta bar alignment | Layout · Must match · text position | `shell.render_beta_banner` (`.uv-beta-box`) | Content centred (`justify-content:center`) | Left-aligned |
| GL-06 | Logo | Gap → G01 | `shell.render_topbar` (`col_logo`); `app.py` `page_icon="favicon.svg"` | Consensus lockup SVG, 26px high (mark + "uvalu" wordmark, accent `--logo-accent`, rings `--logo-ring`), gap 13px to "value engine" | Text wordmark 22px/500, "u" in `--logo-accent`; old favicon |
| GL-07 | Beta bar spacing | Layout · Should match (not reported, ≤ 4px) | `.uv-beta-box` | padding 7px 14px, 8px above, inset 28px | padding 6px 12px, 12px under the 61px top bar, inset 24px (the app's page gutter) |

Matches: brand v1.3 tokens in `styles.py` `:root` / `[data-theme="light"]` (incl. `--link`, `--logo-accent`, `--amber-*`, `--veto-*`, `--nosig-bg`), `.streamlit/config.toml` `primaryColor` `#1A8C6E` and `linkColor` `#167A60` / `#3FBF98`; `:focus-visible` ring (mint dark, teal light); `prefers-reduced-motion`; no radii of 7/9/10/14px left; no readable `--faint` text except placeholders and the provenance separator (decoration); top bar 58px (mockup) vs 61px (code, within tolerance); nav text 13px/500, padding 7px 13px, active `--soft` + `--text`; theme toggle 34×34 outline; user menu (name 13px/500, mono e-mail, "Free beta" chip, Settings · Methodology · About Uvalu · Admin portal, Sign out in `--down-txt`); update notice and reload prompt strips; notice order (update notice, reload prompt, beta bar, peer-rebuild strip); beta box fill, border, radius, "Beta" 600 `--up-txt`, "Terms →" `--link`; peer-reference rebuild strip wording; stale chip (`warning` symbol, "oldest {age}"); footer (disclaimer, producer line, FSMA line, six links 11px `--link`, version 10.5px mono); provenance line (12px `--muted`, values 11.5px mono, quiet "Methodology →"); page titles 24px/500; back links "← Back to …"; no horizontal overflow at 920px.

### 2.2 Dashboard

| ID | Item | Category | Code location | Mockup value | Code value |
| --- | --- | --- | --- | --- | --- |
| DB-01 | Chart range control | Layout · Must match · typography | `dashboard.render` (`st.segmented_control`, key `db_range`); CSS `.st-key-db_range button[data-variant="segmented_control"]` | 11.5px mono / 500; active `--text`, others `--muted` | 14px sans / 400; active also `--muted` |
| DB-02 | Benchmark chips | Layout · Must match · typography | `dashboard.render` (S&P 500 / Euro Stoxx 50 pills) | 11px / 400 `--muted` | 14px / 400 |
| DB-03 | "Full analysis →" | Layout · Must match · typography | `.st-key-db_conv_full_analysis` | 11px `--link` | 14px `--link` |
| DB-04 | Chart default range and label | Gap → G03 | `dashboard.render` (`default="All"`, `_range_txt`) | Default 1Y; label "past year" (11.5px `--muted`) | Default All; label "All · incl. deposits" |

Matches: title, subtitle, provenance; Refresh and Add position in the header (typography under GL-01); KPI tiles (labels 10.5px/500 uppercase `--muted`, sub-lines 11px); "Avg margin of safety" / "weighted MoS"; chart card title 15px/500; Score & risk card ("Weighted composite score" 11px uppercase, "Upper/Middle/Lower band · …" `--up-txt`); risk meter (bands 25/70 and HIGH kept, decided G12); Holdings title, legend, column headers (10px uppercase `--muted`, "Margin of safety", "P&L"), tickers 13.5px mono/500, badges 10.5px/500; Sector allocation donut with TOTAL; Upcoming dividends ("/ yr fwd" `--up-txt`, column header, date block, net + gross); Top movers rows open the drawer.

### 2.3 Screener

| ID | Item | Category | Code location | Mockup value | Code value |
| --- | --- | --- | --- | --- | --- |
| — | Reset filters button | Layout · Must match (counted under GL-01) | header | 12.5px | 14px |

Matches: title "Value screener", provenance; filter labels 10px uppercase `--muted`; five signal chips incl. No signal, 10.5px/500 (chip label "Fails quality screen", decided G20; the mockup still says "Fails screen"); "share of covered stocks" note (brand §8); "Hide positions I own" chip; columns `#`, Company, Signal, Composite score ↓ (sorted header `--text`), Margin of safety, Price, P/E, Yield; exchange codes 9px mono; company names 12px `--muted`; "Show 25 more · 25 of N shown" (mockup pages by 12, app by 25, as the reference says); a stock without a margin passes the margin filter at its default (`screener.py`, the missing-margin rule replaced `fillna(-999)`).

### 2.4 Watchlist

Matches: title 24px; add card (Ticker, Company name labels 10px uppercase); columns Company, Signal, Composite score, Margin of safety, Price, P/E, Yield; exchange codes 9px mono; remove control in the last column. Add ticker button typography is GL-01.

### 2.5 Portfolio (overview, open, closed, dividends, cash)

| ID | Item | Category | Code location | Mockup value | Code value |
| --- | --- | --- | --- | --- | --- |
| PF-01 | Exchange tag in position rows | Layout · Must match · typography | `portfolio._exchange_label` → `components.portfolio_open_row` (and the closed and dividend rows that reuse it) | Short code (PAR, XET, SWX, LON, MIL, MAD), 9px mono `--muted` | City name ("Brussels", "Frankfurt"), 10.5px sans `--muted` |
| PF-02 | "· realised" on the Closed positions card | Layout · Must match · typography | `portfolio.render`, line ~378 | 12px / 400 `--muted` | Inherits the card title: 15px / 400 |
| PF-03 | "· realised" on the Closed positions page title | Layout · Must match · typography | `portfolio.render`, `page_header(title_suffix=…)` line ~516 | 14px / 400 `--muted` | Inherits the title: 24px / 400 |
| PF-04 | Dividends: annual summary and its button | Matches the mockup; README disagrees → G02 | `portfolio.render` (`pf_tax_section`, `export_menu(_("Export summary"))`); `export_menu(_("Export log"))` | Summary full width, tax box under it; "Export log", "Export summary" | Same as the mockup |

Matches: titles 24px; back links "← Back to Portfolio"; KPI tiles incl. "Dividends (12m)" with "net · {gross} gross"; Cash balance card ("EUR base", `open_in_full` icon, Deposit / Withdraw); open-positions columns (Position, Shares, Avg cost, Price, Cost basis, Income 12m, Yield, YoC net, Weight); closed rows "{name} · closed {month}"; Dividends received ("Position · paid", "Net / gross", gross line 10.5px mono); dividend log and chips; cash ledger; decided dividend and cash deviations.

### 2.6 Risk

| ID | Item | Category | Code location | Mockup value | Code value |
| --- | --- | --- | --- | --- | --- |
| RK-01 | Exchange tag in the contribution table | Layout · Must match · typography | `risk.render` (`exchange=_crow["exch"]`, line ~456) → shared row helper | Short code, 9px mono `--muted` | City name, 10.5px sans |
| RK-02 | Sharpe verdict colour | Gap → G04 | `risk.render` metric grid (line ~290); `risk.py` `ratio_label` → tone ("Suboptimal" → `high`) | Sub-lines are neutral `--muted` ("risk-adjusted") | "Suboptimal" in `--down-txt` (red) |
| RK-03 | Factor rows and metric sub-labels | Gap → G07 | `risk.render` factor card, metric grid | Illustrative rows (Concentration, Leverage "… (hard veto)", Market, Volatility, Cyclicality, FX); sub-labels "vs Euro Stoxx 50", "annualised", "1-week" | Computed factor loadings (Mkt-RF, SMB, HML, RMW, CMA, WML) with Low / Moderate tiers; verdict sub-labels; VaR 1-day |

Matches: title, "View cash activity" `--link`; gauge "Moderate risk" `--amber-txt`; metric labels 10.5px uppercase; factor row titles 12.5px/500, tier 11px/500 mono in `--up-txt` / `--amber-txt`; Concentration card; contribution columns; flags ("Fails quality screen" `--down-txt`, "High risk" amber); Risk observations card (kept, decided G22).

### 2.7 Analysis

| ID | Item | Category | Code location | Mockup value | Code value |
| --- | --- | --- | --- | --- | --- |
| AN-01 | Model names | Gap → G06 (legal: consistency with the Methodology document) | `components.six_model_ladder_rows` / `fair_value_ladder` labels; `analysis.py` lines ~669–728 | "Graham Number", "P/E fair value", "EPV", "Dividend, single stage", "Dividend, multi-stage", "Book value (fallback)" | "Graham Number", "P/E fair value", "EPV", "Dividend discount", "DDM 2-stage", "Book value" / "FCF value" |
| AN-02 | Composite fair value row | Layout · Must match · typography | `components.fair_value_ladder` (`composite_html`) | Label 12.5px / 500 | 12.5px / 600 (value 14px / 600) |
| AN-03 | Model delta colour | Must change (brand v1.3: `--amber-fill` only for fills) | `components.fair_value_ladder._row` (delta `<span>` uses `_ladder_bar_color`) | Text `--amber-txt` (decided rule; the mockup itself still draws `--down-txt`, see Suggestions) | `--amber-fill` (`#C98A3A`) as text |
| AN-04 | Dividend panel value weights | Layout · Must match · typography | `analysis.an_card_dividend` (Withholding value, "Feeds DDM inputs" value) | 12.5px / 400 ("FR 12.8% + BE 30%", "automatic") | 12.5px / 500 ("BE 30% only", "automatic") |
| AN-05 | Sensitivity card | Layout · Must match · text position | `analysis._render_history_and_sensitivity` (line ~138) | Header note "Shared settings · model M1" (11px `--muted`) on the title row; rows "Discount 7.0%", "Discount 8.0% · current", "Discount 9.0%" | No header note; rows "Discount rate 4,4%" etc. without a current marker |
| AN-06 | Sub-score names | Gap → G08 | `analysis.py` `_sub_fields` | Quality, Momentum, Financial health, Dividend safety | Margin of safety, Risk (inverted), Quality, Momentum, Dividend (the model's five components) |

Matches: back link, ticker 26px mono, badge, "Composite score" label, sector · exchange subtitle (full exchange name, as in the mockup drawer), band label `--up-txt`, provenance; hero tiles ("Not held" / "{n} shares · €{value}" 13px/500); chart card; sub-scores card; model ladder layout; Financials & valuation; "Quality screen checks" (decided G08 over "Hard-veto checks"); Dividend & income tiles and table; badge history with the footer sentence and without "Recomputed daily" (decided G07); Data sources rows; Producer & conflicts with "Conflicts of interest policy →" `--link`; Model summary last; no DRIP box (decided G09).

### 2.8 Stock drawer

| ID | Item | Category | Code location | Mockup value | Code value |
| --- | --- | --- | --- | --- | --- |
| DR-01 | Dialog title | Layout · Must match · structure | `drawer.open_drawer` (`@_dialog(N_("Stock preview"))`) | No visible title; the drawer starts with the ticker row | "Stock preview" 24px / 600 above the ticker |
| DR-02 | Model names, composite row, delta colour | Shared with AN-01, AN-02, AN-03 | `components.fair_value_ladder` | see Analysis | see Analysis |

Matches: ticker 18px mono, badge, provenance bar (decided G23), three tiles (no "Implied return", decided G24) with Fair value and Margin of safety coloured, "Model fair values" 11px uppercase, "Position & metrics", "Your records · nothing is executed", View full analysis first. Button typography is GL-01.

### 2.9 Settings

| ID | Item | Category | Code location | Mockup value | Code value |
| --- | --- | --- | --- | --- | --- |
| ST-01 | Segmented controls | Layout · Must match · typography | `[class*="st-key-set_row_"] button[data-variant="segmented_control"]` in `styles.py` (~line 1540); `locale_ui.render_card` | 12px / 500; currency codes mono | 14px / 400 sans |
| ST-02 | Language & region preview band | Layout · Must match · typography, case, colour | `locale_ui._preview` | Header "Preview" 12px / 500 `--text`; tag chip "{region} · {currency}" 10.5px mono `--up-txt`; value labels 11px sentence case `--muted` | "Preview" 12px / 400 `--muted`; tag `--muted`; labels 10.5px uppercase |
| ST-03 | "Try a number" | Layout · Must match · typography | `locale_ui._preview` (text input label) | 11px / 400 `--muted`, inside the band | 13.5px / 500 `--text` |
| ST-04 | "Sign out everywhere else" colour | Gap → G05 | `.st-key-set_sessions_revoke_wrap button p` | `--muted` | `--link` |

Matches: frame (back link, 24px title, 200px rail, 760px content); rail order Language & region, Account security, Display, Target allocation, Dividend withholding, Import & export, Model settings, Legal (Privacy and Plan deferred); row titles 13.5px/500, descriptions 12px `--muted`; "Follows region · …" status line; Account security rows (Password, "Linked account · Google" / "Not in the beta", Two-factor with the code's description (decided G31), Passkeys "Not available in the beta" (decided G33), Active sessions without location); Display with Theme and Table density; Target allocation; Dividend withholding with its own anchor `set-withholding`; Import & export with the code's texts (decided G16); "Model settings in force" list plus admin controls (decided G14); Legal documents card (decided G18); account footer with "Free beta"; no Data & alerts.

### 2.10 Methodology

| ID | Item | Category | Code location | Mockup value | Code value |
| --- | --- | --- | --- | --- | --- |
| ME-01 | Model names | Gap → G06 | `help.py` `_MODELS` (lines ~106–113) | "Price/earnings value", "Dividend model, single stage", "Dividend model, multi-stage", "Book value (fallback)", "Free cash flow value (fallback)" (same as the legal Methodology document) | "PE Fair Value", "DDM — 1-stage", "DDM — 2-stage", "Book value and FCF fallbacks" |

Matches: title "Methodology", links row (Full methodology →, Data sources →, Conflicts of interest →) in `--link`; rail (Badges, Models, Quality screens, FAQ, Data sources, Conflicts, About Uvalu); "Badges · meaning and thresholds" with live numbers (decided G32); Reading the badges with four columns; "The fair-value models" title (decided G07); quality-screen list; FAQ; Data sources; Conflicts.

### 2.11 Legal

| ID | Item | Category | Code location | Mockup value | Code value |
| --- | --- | --- | --- | --- | --- |
| LG-01 | Tables in documents | Layout · Must match · typography | `legal._document` (markdown body); CSS `.st-key-legal_doc_body` in `legal.py` | Header cells 10.5px / 500 uppercase `--muted`; body cells 12.5px `--muted`; hairline rows | Streamlit markdown tables: header 16px / 700 `--text`, body 16px `--text` |
| LG-02 | Bold lead-ins ("Same for everyone.") | Layout · Must match · colour | same | 14px / 600 `--text` | 14px / 600 `--muted` |
| LG-03 | Meta chips | Layout · Must match · text | `legal._document` (parses `**Version:** … · **Last updated:** …`) | "Version", "Last updated", "Model version" without colons | "Version:", "Last updated:", "Model version:" |

Matches: frame, rail with "On this page" and numbered sections, English-only note under the rail, eyebrow "Uvalu · Legal", print button, title 20px (decided G02; the mockup draws 30px), body text 14px `--muted`, bullets in `--link`.

### 2.12 About

| ID | Item | Category | Code location | Mockup value | Code value |
| --- | --- | --- | --- | --- | --- |
| AB-01 | What's new lead-ins | Layout · Must match · weight, colour | `about.py` release list (HTML from `changelog.py` / `RELEASE_NOTES.md`) | Lead-in 13.5px / 500 `--text` | 13.5px / 600 `--muted` |
| AB-02 | Commit hash | Gap → G09 | `about.py` (`buildinfo.commit_url`) | Plain mono `--text` | Link to GitHub in `--link`; the repository is private, so the link fails for users |

Matches: rail (This version, What's new, Legal & policies); build rows (App version, Commit, Built, Environment, Scoring model) 13px; support line 12px mono; "Copy for support"; group headings ("Changed", "Fixed") 12px/500 `--muted`.

### 2.13 Sign-in and invitation (`uvalu/authgate.py`)

| ID | Item | Category | Code location | Mockup value | Code value |
| --- | --- | --- | --- | --- | --- |
| AU-01 | Logo on the brand panel | Gap → G01 | `authgate.py` line ~244 (hero) | Lockup SVG 48px high (dark variant), gap 23px to "value engine" | Text wordmark 24px, "u" in `--mint` |

Matches (from source; the sign-in screen was not opened, the dev session is signed in): password-only sign-in, tagline headline (decided G06), full footer with legal links, lock-out text, forgot-password text, "← Back to sign in".

### 2.14 Admin (`uvalu/pages_/admin.py`; `Uvalu Admin.dc.html`)

| ID | Item | Category | Code location | Mockup value | Code value |
| --- | --- | --- | --- | --- | --- |
| AD-01 | Side navigation items | Layout · Must match · typography, colour | `.st-key-admin_sidebar button` (line ~902) | 12.5px; inactive `--muted`; active `--soft` + `--mint`, 500; icon 16px | 14px `--text` for all items (the button rule doesn't reach the inner `<p>`); icons 16px |
| AD-02 | Sidebar logo | Gap → G01 | `admin.py` sidebar header | Lockup SVG 24px high, gap 12px to "admin" | Text wordmark 20px, "u" in `--link` |

Matches: section order Users, Data feeds, System, Backups, Security (decided G25); "User management" 15px/500; stat tiles; users table headers 10.5px uppercase; status chip; "← Back to app" (button typography under GL-01).

## 3. Gaps needing a decision

**Decided 11 October 2026: all nine gaps follow the recommendation.** The Recommendation column is now the decision; the Alternative column is kept for the record.

| ID | Gap | Recommendation (decided) | Alternative | Step |
| --- | --- | --- | --- | --- |
| G01 | **Logo.** All three mockups show the Consensus lockup; the app shows a text wordmark. The spec (`logo-consensus-spec.md`) adds a favicon, PWA icons and an outlined-wordmark rule, and leaves two decisions open (wordmark typeface; light lockup in the app). | Run prompt 1 of `logo-implementation-prompt.md` (assets with an outlined wordmark, no font load) first, then S11 places the inline SVG lockup in the top bar (light/dark by theme), the Admin sidebar and the sign-in panel, and swaps `page_icon`. | Keep the text wordmark until the design system is updated. | S11 |
| G02 | **README vs mockup (dividends).** The new `README.md` says the log button is "Export" and the annual summary "keeps the mockup's left-hand width" with an "Export" button. The mockup (which wins) and the code have "Export log", "Export summary" and a full-width summary. | Keep the code; restore the two README lines to match the mockup in S12. | Change code and mockup to "Export" and a narrower card. | S12 |
| G03 | Dashboard chart default range: 1Y with "past year" (mockup) vs All with "All · incl. deposits" (code). "incl. deposits" was added so the change isn't read as a return. | Default 1Y; label "Past year · incl. deposits" (keeps the accuracy note). | Keep All. | S08 |
| G04 | Sharpe verdict "Suboptimal" in red on Risk. The reference keeps red for a failed quality screen; the mockup shows neutral sub-lines. | `--amber-txt` for the weakest verdict, so red stays reserved; keep the verdict words. | Keep red. | S08 |
| G05 | "Sign out everywhere else": `--muted` in the mockup, `--link` in the code (brand: link text in `--link`). | Keep `--link`. | `--muted`. | — |
| G06 | **Legal (consistency).** Model names differ: drawer and Analysis use "Dividend discount" / "DDM 2-stage" / "Book value" / "FCF value"; Methodology uses "PE Fair Value" / "DDM — 1-stage" / "DDM — 2-stage"; the legal Methodology document and the mockup's Methodology card use "Price/earnings value", "Dividend model, single stage", "Dividend model, multi-stage", "Book value (fallback)", "Free cash flow value (fallback)"; the mockup's drawer and Analysis use the short forms "P/E fair value", "Dividend, single stage", "Dividend, multi-stage", "Book value (fallback)". | Follow the mockup per place: short forms in drawer and Analysis (plus "FCF value (fallback)"), the legal document's names on the Methodology page. Then every name traces to the legal text. | One set everywhere (the legal document's long names), which may not fit the drawer's label column. | S05 |
| G07 | Risk factor rows and metric sub-labels: the mockup's rows are illustrative (and say "hard veto", banned by `tests/test_legal_guards.py`); the code shows computed loadings and verdicts. | Keep the code's content; layout already matches. | Rebuild the factor card on the mockup's six themes. | — |
| G08 | Analysis sub-score names: mockup "Financial health", "Dividend safety"; the model's components are Margin of safety, Risk, Quality, Momentum, Dividend (also listed in Settings › Model settings "Score weighting"). | Keep the code's names (accuracy). | Mockup names (would misdescribe the model). | — |
| G09 | About › Commit links to GitHub; the repository is private. | Plain text, as in the mockup; keep the link for admins only if you want it. | Keep the link. | S10 |

Decided on 9 October (version 2.1) and not reopened: G02 (legal title 20px), G03 (full-width data screens), G04 (16px nav icons, now also in the mockup), G05 (producer wording), G06 (tagline), G07 (no "six models" / "daily" claims), G08 (no "hard veto"), G09 (no DRIP box), G10–G36 as recorded in version 2.1.

## 4. Steps

Order: shared styling (S01–S03), shared row and ladder helpers (S04–S06), then per screen (S07–S10), logo (S11), docs (S12).

### S01 · Shared button and segmented-control type

- **Why:** GL-01, GL-02, DB-01, DB-02, DB-03, ST-01 (Layout, Must match: typography).
- **Files and functions:** `uvalu/styles.py` (new shared block next to the existing segmented-control rules ~line 399); remove the now-redundant single overrides only where they set the same values (`.st-key-scr_more button p`, `.st-key-pf_open_ov_all button p` keep their colour). `tests/test_styles.py`.
- **Changes:**
  - Add shared values: `--uv-btn-fs: 12.5px`, button padding `8px 13px`, min-height 34px, icon 16px with 7px gap.
  - Target the label `<p>` (Streamlit 1.60 renders it in `div[data-testid="stMarkdownContainer"]` inside the button): `button[data-testid^="stBaseButton-"] p` → 12.5px; `stBaseButton-primary` → weight 500. Keep the existing link-styled overrides (back links, "Show all …") which set their own size.
  - Segmented controls: `button[data-variant="segmented_control"] p` → 12px / 500, inactive `--muted`, checked `--text`. Dashboard range (`.st-key-db_range`) → 11.5px mono / 500. Settings currency (`st-key-set_row_…currency…`) → mono.
  - Pills used as chips (`button[data-variant="pills"]`): benchmark chips (`.st-key-db_bench…`) → 11px / 400 `--muted`. Screener signal chips already 10.5px/500, leave as is.
  - "Full analysis →" (`.st-key-db_conv_full_analysis button p`) → 11px.
  - Leave Streamlit inputs, selects, sliders, toggles, uploader and dialogs alone (Accept the framework).
- **Strings:** none.
- **Data and settings impact:** none.
- **Risks and open questions:** buttons get 6px lower; check that header rows with a title and buttons still align (`page_header`) and that the dialog footers don't shrink below a comfortable click target (34px kept).
- **Tests:** extend `tests/test_styles.py` with assertions that the shared selectors exist (as for the segmented-control fix of 10 October).
- **How to verify:** at 1280px, both themes: Dashboard header buttons (12.5px, primary 500, height ≈ 34px), range control (11.5px mono), benchmark chips (11px), Portfolio header, Screener Reset filters, Settings segmented controls (12px/500, currency mono), Admin "Invite user". Compare with `Uvalu.dc.html` Dashboard and Settings. 920px: header buttons stay on one line beside the title or wrap under it as today.
- **Size:** M.
- **Depends on:** —

### S02 · Top bar and Admin navigation: icons and inactive colour

- **Why:** GL-03, GL-04, AD-01 (Must match); `Design reference.md` "16px in navigation".
- **Files and functions:** `app.py` lines 112–116 (`st.Page` icons); `uvalu/shell.py` `_topbar_css`; `uvalu/pages_/admin.py` sidebar CSS (~line 902); `tests/test_styles.py`.
- **Changes:**
  - Icons: Dashboard `:material/home:`, Screener `:material/monitoring:`, Watchlist `:material/star:`, Portfolio `:material/work:`, Risk `:material/shield:`.
  - Nav colour: set the colour on the link's inner wrapper and label (`a[data-testid="stPageLink-NavLink"] span`, `… p`, `[data-testid="stIconMaterial"]`) to `--muted`; hover and the active `a[href="{active_path}"]` to `--text`.
  - Admin sidebar: apply 12.5px and `--muted` to `.st-key-admin_sidebar button p` and its icon; active `.st-key-admin_navbtn_{active} button p` → `--mint`, 500.
- **Strings:** none.
- **Data and settings impact:** none.
- **Risks and open questions:** `st.Page` icons also show in Streamlit's hidden sidebar nav; nothing visible changes there. Check the Risk page icon no longer duplicates the Admin portal's `shield` in the user menu (the menu keeps `shield` for Admin portal; the mockup's menu has the same pairing).
- **Tests:** a test that `_NAV_ITEMS` pages carry the five icon names; style test for the nav colour selector.
- **How to verify:** 1280px, both themes, on every top-level page: one link `--text` on `--soft`, the other four `--muted`, 16px icons as in `Uvalu.dc.html`. Admin: compare with `Uvalu Admin.dc.html` sidebar. 920px: icons are hidden below 1200px (existing rule) and links fit.
- **Size:** S.
- **Depends on:** —

### S03 · Beta bar centred

- **Why:** GL-05 (Must match: text position); reference "centred text".
- **Files and functions:** `uvalu/shell.py` `render_beta_banner`.
- **Changes:** add `justify-content:center` to `.uv-beta-box`; padding `7px 14px` (from 6px 12px). Keep the 24px page gutter (GL-07 within tolerance) and the existing margins.
- **Strings:** none.
- **Data and settings impact:** none.
- **Risks and open questions:** when the text wraps (long translations at 920px), centred lines are fine per the mockup (`flex-wrap:wrap`).
- **Tests:** existing `tests/test_shell*.py` / beta-banner tests keep passing; add an assertion on `justify-content:center` if a markup test exists.
- **How to verify:** 1280px both themes vs `Uvalu.dc.html` with Tweaks environment = production: box centred, "Beta" `--up-txt`, "Terms →" `--link`. 920px: one line in English.
- **Size:** S.
- **Depends on:** —

### S04 · Exchange short codes in Portfolio and Risk rows

- **Why:** PF-01, RK-01 (Must match: typography).
- **Files and functions:** `uvalu/pages_/portfolio.py` `_exchange_label` (callers at lines ~351, 405, 489, 549, 660); `uvalu/pages_/risk.py` contribution rows (`exchange=_crow["exch"]`, ~line 456) and where `exch` is built; `uvalu/components.py` `portfolio_open_row` (and the closed / dividend row helpers that render `exchange`); `uvalu/formatting.py` `exchange_code` (already used by the Screener).
- **Changes:** pass `formatting.exchange_code(ticker)` instead of `exchange_label(ticker)`; render it as 9px mono `--muted` (the Screener's `stock_row` style). The drawer's "Exchange" row and the Analysis subtitle keep the full name (mockup).
- **Strings:** none (codes are not translated); city-name msgids stay in use by the drawer.
- **Data and settings impact:** none.
- **Risks and open questions:** tickers without a known suffix: `exchange_code` returns `None`; render nothing (as the Screener does).
- **Tests:** `tests/test_components.py` (portfolio row markup), `tests/test_formatting.py` unchanged; add a Risk page AppTest assertion that the row shows "BRU"/"XET" style codes.
- **How to verify:** 1280px both themes: Portfolio overview open positions and Risk contribution table vs `Uvalu.dc.html` Portfolio and Risk: code under the ticker, 9px mono `--muted`.
- **Size:** S.
- **Depends on:** —

### S05 · Model names (drawer, Analysis, Methodology)

- **Why:** AN-01, ME-01; G06 (decided 11 October: short forms in drawer and Analysis, the legal document's names on Methodology). Legal: names must trace to `docs/legal/policies/beta/methodology.md` § 3.
- **Files and functions:** `uvalu/components.py` `six_model_ladder_rows` (labels, incl. `N_("Book value")`, `N_("FCF value")`) and the fallback note at lines ~742–748; `uvalu/pages_/analysis.py` (labels at ~669–728); `uvalu/drawer.py` (uses the same helper); `uvalu/pages_/help.py` `_MODELS` (~106–113).
- **Changes (per the recommendation):**
  - Drawer and Analysis: "Dividend discount" → "Dividend, single stage"; "DDM 2-stage" → "Dividend, multi-stage"; "Book value" → "Book value (fallback)"; "FCF value" → "FCF value (fallback)". "Graham Number", "P/E fair value", "EPV" unchanged.
  - Update the fallback note sentences to the new names.
  - Methodology: "PE Fair Value" → "Price/earnings value"; "EPV (Earnings Power Value)" → "Earnings power value (EPV)"; "DDM — 1-stage" → "Dividend model, single stage"; "DDM — 2-stage" → "Dividend model, multi-stage"; "Book value and FCF fallbacks" → two entries "Book value (fallback)" and "Free cash flow value (fallback)", descriptions taken from the legal document's table.
  - Internal keys used for matching (`shown = {…} & {"Book value", "FCF value"}`) switch to the new msgids.
- **Strings:** rename the msgids above; update `locales/*/LC_MESSAGES/uvalu.po` for nl, fr, de, it, es (and the English source). Remove the old msgids.
- **Data and settings impact:** none (labels only; no stored values use the names).
- **Risks and open questions:** the drawer label column width with "Dividend, multi-stage" (≈ 130px at 12.5px) — check it doesn't wrap at 920px. Translations of the legal names should match the translated legal UI strings where they exist.
- **Tests:** `tests/test_components.py` (ladder labels), `tests/test_compliance_algorithms.py` (add: Methodology model names equal the legal document's § 3 names), i18n catalogue tests.
- **How to verify:** drawer and Analysis vs `Uvalu.dc.html` drawer (TTE.PA) and Analysis; Methodology Models card vs the mockup's Methodology page and the Legal › Methodology document. Both themes.
- **Size:** M.
- **Depends on:** —

### S06 · Fair-value ladder and drawer details

- **Why:** AN-02, AN-03 (Must change, brand), DR-01.
- **Files and functions:** `uvalu/components.py` `fair_value_ladder` (`_row`, `composite_html`); `uvalu/drawer.py` `_dialog` / `open_drawer`; `uvalu/styles.py` (dialog title rule).
- **Changes:**
  - Delta text colour: a separate text colour next to `_ladder_bar_color`: `--up-txt` above +3%, `--muted` within ±3%, `--amber-txt` below −3%; bars keep `--up-txt` / `--axis` / `--amber-fill`.
  - Composite row label weight 600 → 500 (value stays 14px mono `--up-txt`; mockup value 500 — set 500 too).
  - Drawer title: keep `"Stock preview"` as the dialog's accessible name but hide it visually for this dialog only (scoped by the drawer's own key container), so the drawer starts with the ticker row as in the mockup.
- **Strings:** none.
- **Data and settings impact:** none.
- **Risks and open questions:** hiding a dialog title needs a selector on Streamlit's dialog header; use a key on the drawer body and `:has()` from the dialog to it. If that proves fragile, keep the title and record the 24px difference.
- **Tests:** `tests/test_components.py` (delta colour token for a negative delta is `--amber-txt`); drawer AppTest still finds the dialog.
- **How to verify:** drawer for a stock with a model below price (amber text, amber bar), Analysis model card; both themes vs `Uvalu.dc.html` drawer.
- **Size:** S.
- **Depends on:** S05 (same function; avoid conflicts).

### S07 · Portfolio: "· realised" sizes

- **Why:** PF-02, PF-03 (Must match).
- **Files and functions:** `uvalu/pages_/portfolio.py` lines ~378 and ~516.
- **Changes:** card suffix `font-size:12px`; page-title suffix `font-size:14px`; both weight 400 `--muted`.
- **Strings:** none.
- **Data and settings impact:** none.
- **Risks and open questions:** none.
- **Tests:** none new; existing portfolio AppTests.
- **How to verify:** Portfolio overview (Closed positions card) and Closed positions page vs `Uvalu.dc.html`; both themes.
- **Size:** S.
- **Depends on:** —

### S08 · Dashboard chart range and Risk verdict colour

- **Why:** G03 and G04 (decided 11 October as recommended).
- **Files and functions:** `uvalu/pages_/dashboard.py` (`st.segmented_control(default=…)`, `_range_txt`); `uvalu/pages_/risk.py` metric grid tone mapping; `risk.py` `ratio_label` tone table (line ~164).
- **Changes:** default range "1Y"; label "{range} · incl. deposits" with "past year", "past month", "past 3 months", "all time" as the range words; "Suboptimal" tone `high` → render in `--amber-txt` on the Risk metric grid (red stays for the quality-screen flag).
- **Strings:** add "Past year · incl. deposits", "Past month · incl. deposits", "Past 3 months · incl. deposits", "All time · incl. deposits" (or one template plus four range words); remove "{range} · incl. deposits" if replaced. Update all six catalogues.
- **Data and settings impact:** none (the range is not stored).
- **Risks and open questions:** the 1Y view needs a year of value history; for younger portfolios fall back to All.
- **Tests:** dashboard AppTest default range; risk tone test.
- **How to verify:** Dashboard chart card vs `Uvalu.dc.html` (1Y selected, "past year"); Risk metric grid; both themes.
- **Size:** S.
- **Depends on:** S01 (range control style).

### S09 · Analysis and Settings details

- **Why:** AN-04, AN-05, ST-02, ST-03 (Must match).
- **Files and functions:** `uvalu/pages_/analysis.py` `an_card_dividend`, `_render_history_and_sensitivity` (~line 138); `uvalu/locale_ui.py` `_preview`.
- **Changes:**
  - Dividend panel: Withholding and "Feeds DDM inputs" values weight 400.
  - Sensitivity: header note "Shared settings · model {model}" (11px `--muted`) on the card title row; rows "Discount {rate}" and "· current" after the rate in force.
  - Preview band: "Preview" 12px / 500 `--text`; tag chip 10.5px mono `--up-txt`; value labels 11px sentence case `--muted` (drop `text-transform:uppercase`); "Try a number" label 11px `--muted` (label of the text input via its key container).
- **Strings:** add "Shared settings · model {model}", "Discount {rate}", "{label} · current"; remove "Discount rate {rate}". Six catalogues.
- **Data and settings impact:** none.
- **Risks and open questions:** "· current" needs the rate in force; take it from the same settings the card shows under "Discount rate".
- **Tests:** analysis AppTest for the new strings; `tests/test_locale_ui.py` preview markup.
- **How to verify:** Analysis (Assumptions & sensitivity, Dividend & income) and Settings › Language & region vs `Uvalu.dc.html`; both themes.
- **Size:** M.
- **Depends on:** S01.

### S10 · Legal and About text styles

- **Why:** LG-01, LG-02, LG-03, AB-01 (Must match); G09.
- **Files and functions:** `uvalu/pages_/legal.py` (`_document`, the CSS block at ~line 89); `uvalu/pages_/about.py` (release list HTML, commit row); `uvalu/changelog.py` if it builds the lead-in markup.
- **Changes:**
  - Legal tables: `.st-key-legal_doc_body table` header cells 10.5px / 500 uppercase `--muted`, body cells 12.5px `--muted`, 0.5px `--line-2` row rules, no outer border; keep print styles.
  - Bold lead-ins (`strong` in paragraphs) → `--text`.
  - Meta chips: strip the trailing colon from the parsed labels.
  - About › What's new: lead-ins 500 `--text`.
  - About › Commit: plain mono text (G09).
- **Strings:** none (labels come from the documents).
- **Data and settings impact:** none.
- **Risks and open questions:** the legal documents are also printed; check print output keeps black text.
- **Tests:** `tests/test_legal*.py` (chip parsing without colons); about page AppTest.
- **How to verify:** Legal › Methodology (tables in §2 and §3) and About vs `Uvalu.dc.html` Legal and About; both themes; print preview of one document.
- **Size:** S.
- **Depends on:** —

### S11 · Logo lockup

- **Why:** GL-06, AU-01, AD-02; G01.
- **Files and functions:** `uvalu/shell.py` `render_topbar` (`col_logo`); `uvalu/authgate.py` hero (~line 244); `uvalu/pages_/admin.py` sidebar header; `app.py` `page_icon`; `uvalu/styles.py` (`--logo-ring` token: `#FFFFFF` dark, `#0D1F3C` light); assets from `assets/logo/` (logo prompt 1).
- **Changes:** inline SVG lockup (outlined wordmark) — top bar 26px high, gap 13px to "value engine", colours from `--logo-accent` / `--logo-ring`; Admin sidebar 24px high, gap 12px, dark variant; sign-in panel 48px high, gap 23px, dark variant; favicon from the small mark (32px PNG). `aria-label="uvalu"`, `role="img"`. Keep the "value engine" tag rule below 1100px.
- **Strings:** none ("uvalu" is the brand name, not translated).
- **Data and settings impact:** none.
- **Risks and open questions:** the spec's two open decisions (typeface; light lockup). Without outlined paths the SVG needs Inter; don't add a font request.
- **Tests:** `tests/test_logo_assets.py` (from the logo prompt); a shell test that the top bar contains the SVG with `aria-label`.
- **How to verify:** top bar in both themes, Admin, sign-in panel and the browser tab icon vs the three mockups at 1280px; 920px: logo plus nav fit.
- **Size:** M.
- **Depends on:** logo prompt 1 (`docs/design/logo-implementation-prompt.md`, assets with an outlined wordmark).

### S12 · Docs and release notes

- **Why:** G02; open-items D1 is done by the new mockups.
- **Files and functions:** `docs/design/README.md` (dividends lines), `docs/open-items.md` (remove D1; add the mockup follow-ups from Suggestions), `CHANGELOG.md`, `RELEASE_NOTES.md`.
- **Changes:** restore "The log download sits next to Add dividend as "Export log"" and "The annual summary card is full width with the tax-estimate box under it; its button is labelled "Export summary""; write the release entries (section 6) in both files.
- **Strings:** none.
- **Data and settings impact:** none.
- **Risks and open questions:** none.
- **Tests:** `tools/release.py check-changelog`.
- **How to verify:** read-through.
- **Size:** S.
- **Depends on:** S01–S11.

**Totals:** 8 small (S02, S03, S04, S06, S07, S08, S10, S12), 4 medium (S01, S05, S09, S11). About 28 hours.

## 5. Not in this plan

- Phone and tablet layouts (deferred in `Design reference.md`).
- Settings › Privacy: Export my data, Delete account, Privacy contact.
- Acceptance records, the invitation consent boxes and the Settings › Legal acceptance rows (open-items L1).
- Settings › Plan card.
- Two-factor extensions and passkeys (decided 9 October).
- The "Check with real translations" list (seven items in `Design reference.md`).

## 6. Release notes draft

`CHANGELOG.md`:

```markdown
## [2026.10.N] — 2026-10-DD

Buttons, navigation and a few labels now match the design reference. Scores
and signals don't change.

### Added

- **New logo.** The Consensus mark (two rings, the lens where the models
  agree) in the top bar, the Admin portal, the sign-in screen and the browser
  tab.
- **Assumptions & sensitivity** marks the discount rate in force and says the
  settings are shared ("Shared settings · model M1").

### Changed

- **Buttons and segmented controls** use the smaller 12.5px label (12px for
  segmented controls) across the app.
- **Top navigation**: new icons (home, monitoring, star, work, shield);
  inactive pages are grey again. The Admin side navigation matches.
- **Beta notice** text is centred in its box.
- **Model names** follow the Methodology document: "Dividend, single stage",
  "Dividend, multi-stage", "Book value (fallback)", "FCF value (fallback)" in
  the stock panel and Analysis; the full names on the Methodology page.
- **Portfolio and Risk tables** show the exchange code (BRU, XET, PAR) like
  the Screener.
- **Dashboard** chart opens on the past year.
- **Risk**: the weakest Sharpe verdict is amber; red stays for a failed
  quality screen.
- **Legal pages**: tables and bold lead-ins use the document styles.
- **About**: the commit is plain text.

### Fixed

- Model differences below the price used the amber fill colour as text; they
  now use the readable amber text colour.
```

`RELEASE_NOTES.md` gets the subscriber version (New: the logo; Improved: calmer buttons and navigation, clearer model names, exchange codes, chart opens on the past year).

## 7. Suggestions (outside the reference)

- **Update the design project** where the mockup still contradicts decided rules: model deltas below price in `--down-txt` (should be `--amber-txt`), the Risk "Size" flag in `--faint`, the "Fails screen" chip label, "hard veto" texts, the 30px legal title, lowercase "dark/light" in Settings, and the README dividends lines (G02). Add these to `docs/open-items.md` under Design and code.
- **A style regression test** that reads computed label sizes is not possible in AppTest; a small checklist in `docs/design/` of the shared selectors that depend on Streamlit's markup (`button p`, page-link `span`, `data-variant`) would make the next Streamlit upgrade faster to check.
