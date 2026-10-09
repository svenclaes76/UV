# Implementation plan: align the app with the October 2026 design reference

Version 2, 9 October 2026. Prepared against `master` at `88fd076` (Brand Guidelines v1.3 merged), with the updated reference files from `docs/design/HOW-TO-APPLY.txt` in the working tree (not yet committed). Sources: `docs/design/Design reference.md`, `Uvalu.dc.html`, `Uvalu Admin.dc.html`, `Uvalu Auth.dc.html`, `docs/uvalu-brand-guidelines.md` v1.3 (identical to `docs/design/uvalu-brand-guidelines.md`), `docs/legal/compliance-implementation-plan.md`, `docs/legal/policies/beta/*.md`, `docs/design/legal-docs.js`, `uvalu/compliance/disclosures.py`.

How the assessment was done: values were read from the mockup templates and their logic class, from the brand guidelines, and from the code (`uvalu/styles.py`, `uvalu/shell.py`, `uvalu/components.py`, every page in `uvalu/pages_/`, `uvalu/drawer.py`, `uvalu/locale_ui.py`, `uvalu/authgate.py`, `uvalu/update_notice.py`, `auth.py`, `settings.py`, `app.py`, `.streamlit/config.toml`). Widths are worked out for a 1280px window from the fixed values in both. Neither the app nor the mockups were opened in a browser, so every step ends with a side-by-side check at 1280px in both themes and a 920px spot-check.

## 0. What changed since version 1

The reference now follows Brand Guidelines v1.3 and adds authentication decisions. Effects on this plan:

- **Colour tokens.** Version 1 planned new `--mint-txt` / `--teal-txt` tokens and new teal, muted and faint values. v1.3 replaces that: the existing values stay (they already match v1.3), and a `--link` token is added for link text (`#167A60` light, `#3FBF98` dark), plus `--logo-accent`, `--veto-bg`, `--veto-line` and `--nosig-bg`. Positive text uses `--up-txt`; Mint Pulse is never text on light. `--faint` becomes decoration only, so every readable `--faint` text moves to `--muted` (about 140 places). Radii are rounded to 4/6/8/12px and a `:focus-visible` ring is added. S01–S03 are rewritten.
- **Items that now match the code** and were removed from the plan: provenance values (11.5px mono) and the quiet underlined "Methodology →"; the stale chip's "oldest {age}" format (only the icon and tooltip change); supporting pages left-aligned on the gutter with a 32px gap; the founder notice wording (the mockup now uses the code's sentence and only adds a policy link); the ±3% fair-value ladder band (only its colours change); legal document title 20px (brand) — see G02.
- **Changed targets:** notice order is now update notice, reload prompt, then the beta bar; "Beta" in the beta bar is `--up-txt` with a "Terms →" link (its shape: see your decisions below); ladder fills are `--up-txt` / `--axis` / `--amber-fill`; sub-score text is `--up-txt` / `--link` / `--amber-txt`; uppercase small labels are `--muted`.
- **Authentication (new decisions):** password sign-in only in the beta (no provider buttons), Google shown as "Not in the beta" in Settings and Admin, full footer on the sign-in panel, password reset through an admin, accounts by invitation only, sessions without location, and the beta privacy notice without Google sign-in. New steps S25–S27. (MFA for admins is in the reference too; you deferred it, see below.)
- **Gaps:** resolved by the new reference: badge colours (old G01), founder notice (old G04), ladder thresholds (old G12), 2FA text (old G17). New gaps on the beta bar shape, legal title size, data-screen width, nav icon size, sign-in headline and link, invitation consent scope, MFA policy details, passkeys and the breached-password check. Gaps are renumbered.
- **Your decisions of 9 October (version 2.1):** the beta bar stays a rounded box (Brand §8, G01); the sign-in headline is the tagline (G06); invitation consent stays deferred (G30); passkeys are deferred (G33); two-factor changes are deferred (G31), so the step that enforced MFA for admins is gone and S26 no longer touches the MFA policy. These five are listed under "Decided" in section 3 and removed from the open gaps.

## 1. Summary

- 29 steps: 9 small, 20 medium, no large. About 98 hours, roughly 12 working days.
- Order: brand tokens and their use (S01–S03), shared page frame and card styles (S04–S05), decided labels and behaviour (S06–S09), global chrome (S10–S11), one or two steps per screen (S12–S24), authentication and the beta privacy notice (S25–S27), legal wording (S27) and release notes (S28).
- 31 gaps are still open (section 3); 9 involve legal text, a legal document or a legal guard. Five more are decided.
- Biggest risk 1: S03 replaces `--faint` with `--muted` in about 140 places and rounds legacy radii. Every screen gets slightly darker secondary text in one go. Mitigation: a mechanical pull request with a before/after screenshot set, nothing else in it.
- Biggest risk 2: S25 removes provider sign-in for the beta. A tester who only ever signed in with Google can't get in. Mitigation: check `auth.has_password` for every beta account before release and send those accounts an admin reset link.
- Biggest risk 3: the page frame (S04) wraps every page in a new container, and the existing CSS depends on Streamlit's internal wrappers and on `margin-top:-16px` gap fixes. Mitigation: one keyed wrapper per page, nothing else in that step, and a measured title position on every page.

Layout differences per screen (Layout rows in section 2; decided items count as Must change, not here):

| Screen | Must match | Should match |
| --- | ---: | ---: |
| Global elements (top bar, menu, banner, footer, notices, frame) | 11 | 0 |
| Dashboard | 11 | 1 |
| Screener | 10 | 2 |
| Watchlist | 3 | 0 |
| Portfolio (overview, open, closed, dividends, cash) | 12 | 0 |
| Risk | 5 | 0 |
| Analysis | 9 | 1 |
| Stock drawer | 3 | 0 |
| Settings | 8 | 0 |
| Methodology | 4 | 0 |
| Legal | 4 | 1 |
| About | 1 | 0 |
| Sign-in and invitation | 2 | 0 |
| Admin | 3 | 0 |
| **Total** | **86** | **5** |

## 2. Assessment

Notation: `--x` is a CSS token. "Mockup" is `Uvalu.dc.html` unless stated; "Brand" is the brand guidelines v1.3. Layout rows give the level (Must / Should). For each screen the five most visible differences come first, then the rest, then what matches.

### 2.1 Brand tokens (all screens)

| ID | Item | Category | Code location | Reference value | Code value |
| --- | --- | --- | --- | --- | --- |
| BR-01 | `--link` token | Must change | `styles.py` `:root`, `[data-theme="light"]`; `.streamlit/config.toml` `linkColor`; `runtime.ThemeColors` | `#167A60` light, `#3FBF98` dark, for all link text; hover `--text` (mockup) | None; links use `var(--teal)` / `#1A8C6E` (4.2:1 on white) or `--mint`; Streamlit `linkColor` `#1A8C6E` / `#1DD6A4` |
| BR-02 | Badge tokens | Must change | `styles.py` `.uv-badge-*`; `components.signal_badge_html` | Light and dark use the token pairs: Undervalued `--up-bg`/`--up-txt`, Neutral `--amber-bg`/`--amber-txt`, Low score `--down-bg`/`--down-txt`, Fails quality screen `--veto-bg` (`#0D1F3C` light, `#1E2D4A` dark) with `--veto-line` hairline in dark, No signal / No data `--nosig-bg` with `--muted`; 10.5px/500, padding 0 9px, radius 6px, no letter-spacing | Light uses fixed tints (`--uv-pos-bg` `#E8F5F0` etc.); dark uses the token pairs; `min-width:64px`, `letter-spacing:0.03em` |
| BR-03 | Readable `--faint` text | Must change | ~140 uses: `components.py` (37), `admin.py` (23), `risk.py`, `authgate.py`, `analysis.py`, `shell.py`, `dashboard.py`, … | `--faint` for decoration only (separators, dots, disabled fills); uppercase labels, captions, sub-labels, empty states in `--muted` | Column headers (`header_cell_html`), tile labels, captions, sub-lines, footer producer line in `--faint` |
| BR-04 | Mint and teal as text | Must change | `components.py`, pages, `shell.py`, `dialogs.py`, `update_notice.py` | Positive figures and labels `--up-txt`; links `--link`; Mint Pulse only on navy surfaces and as fills | `var(--mint)`, `var(--uv-mint)`, `#1DD6A4`, `var(--teal)` as text, also on light |
| BR-05 | Amber fill as text | Must change | `components.py`, `risk.py`, `analysis.py`, `dashboard.py`, `dialogs.py` | Text `--amber-txt`; `#C98A3A` / `--amber-fill` only for bars and swatches | `#C98A3A` used as text colour |
| BR-06 | Radii | Must change | `styles.py` (5), `authgate.py` (4), `drawer.py` (2), `risk.py` (2), `settings.py` (1) | 4 / 6 / 8 / 12px only | 7, 9, 10, 14px in 14 places |
| BR-07 | Focus ring | Must change | `styles.py` | `:focus-visible` 2px solid outline, offset 2px, `--teal` light, `--mint` dark | None of the app's own |
| BR-08 | Reduced motion | Must change | `styles.py` | `@media (prefers-reduced-motion:reduce)` disables animation (mockup; Brand §7 Loading) | Animations always run |
| BR-09 | Logo accent | Must change (brand token) | `shell.render_topbar`; admin sidebar | `--logo-accent`: `#1DD6A4` dark, `#1A8C6E` light | `var(--teal)` in both themes |
| BR-10 | Primary button colour | Must change | `.streamlit/config.toml` | `--teal #1A8C6E` fill with white text in both themes | Dark `primaryColor` `#1DD6A4` (mint fill) |

Matches: `--bg`, `--panel`, `--panel-2`, `--text`, `--muted`, `--faint`, `--line`, `--line-2`, `--teal`, `--mint`, `--up-*`, `--down-*`, `--amber-txt`, `--amber-bg`, `--amber-fill`, `--uv-track`, `--grid`, `--axis`, `--shadow` (all already v1.3 values); 12-colour categorical palette (`ui._DONUT_PALETTE`); tooltip style; Material Symbols as the icon set.

### 2.2 Global elements

| ID | Item | Category | Code location | Mockup value | Code value |
| --- | --- | --- | --- | --- | --- |
| GL-01 | Beta bar | Layout · Must (shape decided: G01) | `shell.render_beta_banner` | Rounded box per Brand §8 (decided): `--soft` bg, 0.5px `--line` border, radius 8px, 11.5px `--muted`; "Beta" 600 in `--up-txt`; "Terms →" in `--link` (mockup); placed after the update notice and reload prompt | Rounded box with the same bg, border and radius; "Beta" in `--mint`; no Terms link; placed before the notices |
| GL-02 | Notice order | Layout · Must | `app.py` lines 155–159 | Top bar, update notice, reload prompt, beta bar, peer-reference strip, error box | Top bar, beta banner, update notice, reload prompt |
| GL-03 | Page titles | Must change | `dashboard`, `screener`, `watchlist`, `portfolio`, `cash`, `risk` renders | 24px/500, −0.02em, 1.2 | 22px/500 |
| GL-04 | Footer | Layout · Must | `shell.render_footer`, `_FOOTER_CSS` | Left-aligned; disclaimer 11.5px `--muted` max 980px; producer and "Not authorised…" as two spans (11px `--muted`); links left, gap 6px 16px, no separators, 11px `--link`, hover `--text`; version 10.5px mono `--muted`, hover `--link` | Links centred with "·" separators in `--teal`; version centred in `--faint` |
| GL-05 | User menu | Must change + Layout · Must (+ G27) | `shell.render_topbar` | Header: name 13px/500, e-mail 11px mono `--muted`, chip "Free beta" (10px/500, radius 6px, `--soft`, `--up-txt`). Items with 16px Material icons: Settings, Methodology, About Uvalu, Admin portal; divider; Sign out `--down-txt` (hover `--down-bg`) | Name 14px/600, e-mail 12px mono, role chip; "Methodology & help", extra "Legal & policies"; Sign out in `--text` |
| GL-06 | Nav links | Layout · Must (+ G04) | `shell._topbar_css` | 13px/500, padding 7px 13px; active `--soft` bg + `--text`; icon 16px in the mockup, 20px in Brand §6 | 12.5px, padding 7px 12px; active text `--mint`; icon 16px |
| GL-07 | Logo | Layout · Must | `render_topbar` | 22px/500; "u" in `--logo-accent`; "value engine" 10px `--muted` | 20px; "u" in `--teal`; 9px `--faint` |
| GL-08 | Theme toggle | Layout · Must | `_topbar_css` | 34×34, transparent, 0.5px `--line`, `--muted` icon; hover `--teal` border | 32×32, `--navy` fill and `--mint` icon (dark) |
| GL-09 | Update notice | Layout · Must | `update_notice.render_whats_new_notice` | Strip on `--panel`, bottom `--line-2`, padding 8px 28px, 12.5px; "●" `--up-txt`; "See what's new" `--link`; "Dismiss" `--muted` | In-page container; "●" `--mint` |
| GL-10 | Reload prompt | Layout · Must | `update_notice.render_reload_prompt` | Strip on `--panel` (same as update notice); "Reload" `--link` | In-page container; link `--teal` |
| GL-11 | Peer-reference rebuild | Gap → G10 | `app.py`; `data.peer_reference_pending` | Strip with 12px spinner, `--panel-2`, 12.5px `--muted`: "Rebuilding the peer reference after a restart. Signals show “No signal” until it finishes, usually within a few minutes." | Skeletons on Dashboard and Risk only |
| GL-12 | Error state | Gap → G11 | `app.py`; `shell.render_error_reference` | Box radius 8px, `--down-bg` / `--down-txt` 13px: "Couldn’t load the portfolio data. Try again in a moment." + 12px `--muted` "Something went wrong. Reference for support: " + mono reference | Caption with the reference, then the exception |
| GL-13 | Stale-price chip | Layout · Must | `components._stale_chip_html` | Material `warning` symbol (14px) + "oldest {age}", 11px/500, padding 1px 8px, radius 6px, `--amber-bg` / `--amber-txt`; tooltip "Some prices are more than 72 hours old. Signals for those stocks use the last known price." | "⚠" character; 10.5px, padding 1px 7px; tooltip "{count} prices are more than 72 hours old." |
| GL-14 | Maintenance version line | Layout · Must | `shell.render_maintenance` | 11.5px mono `--muted` | Sans, `--faint` |
| GL-15 | Producer line | Gap → G05 (legal text) | `shell.producer_line` | "Sven Claes, trading as Uvalu · Pol Heynsstraat 7, 2200 Herentals, Belgium · enterprise number: registration pending · support@uvalu.app" | "Uvalu · Sven Claes, Pol Heynsstraat 7, … · enterprise number: registration pending · support@uvalu.app" |
| GL-16 | Data-page width | Gap → G03 | `styles.py` `.block-container` | Wide pages max 1440px centred; Watchlist and Analysis max 1180px centred; padding 22px 28px 60px. Brand §7: data screens "full content width" | Full width, padding 0 24px |

Matches: provenance line (12px muted, values 11.5px mono, faint separators, quiet underlined "Methodology →"); supporting pages left-aligned at 1180px with a 200px rail, 32px gap and 760px content; environment marker; maintenance texts; avatar (navy with mint initials); price status text; tooltips; top-bar height (58 vs 61px).

### 2.3 Dashboard

| ID | Item | Category | Code location | Mockup value | Code value |
| --- | --- | --- | --- | --- | --- |
| DB-01 | Holdings margin-of-safety column | Must change | `dashboard.render` (`_hh_labels`); `components.holdings_row_html` | Header "Margin of safety"; value `--up-txt` ≥ 15%, `--text` 0–15%, `--amber-txt` below 0 | "MoS %"; `--up-txt` ≥ 0, `--down-txt` (red) below 0 |
| DB-02 | Holdings P&L column | Must change | `holdings_row_html` | % against average cost as an up/down chip, tooltip "Unrealised result against your average cost" | Signed € amount, no tooltip |
| DB-03 | Score & risk band | Must change | `dashboard.render` (`_conv_label`, `_conv_ring`) | "Upper band · 70–100" / "Middle band · 40–69" / "Lower band · 0–39" in `--up-txt`; ring `--mint`, never red | "Upper/Middle/Lower range of the model scale" in `--text`; ring red below 40 |
| DB-04 | Ladder fills and legend | Must change | `components._ladder_bar_color`, `fair_value_legend_html` | Fill `--up-txt` below fair value, `--axis` within ±3%, `--amber-fill` above, on `--uv-track`; legend swatches the same, radius 4px, 11.5px `--muted` | Mint / teal / amber (same ±3% band) |
| DB-05 | Upcoming dividends card | Layout · Must | `db_card_dividends` | Header "{€k} / yr fwd" 11px mono `--up-txt`; column header "Ex-date · payment" / "Net est."; rows with date block (15px mono day, 9px uppercase month), "ex-date · pays {date}" 10.5px mono `--muted`, net `--up-txt` + "{gross} gross"; 5 rows | "{amount} / yr" 13px `--mint`; no column header or date block; "{date} · {yield} yield" + alert badges; 6 rows |
| DB-06 | Sector allocation | Layout · Must | `ui._donut_chart` | 132px SVG donut, "TOTAL" + short total in the centre, legend list to the right (8px swatch radius 4px, 11.5px `--muted`, mono %) | Plotly pie, legend below |
| DB-07 | Header actions | Layout · Must | heading | Refresh (outline, `refresh` icon) and Add position (filled `--teal`, `add` icon) | Refresh only |
| DB-08 | Subtitle | Layout · Must | `st.caption` | 13px `--muted`; "… · valued against a model fair-value estimate." | 14px caption; "… · compared with model fair-value estimates." |
| DB-09 | Avg margin of safety tile | Layout · Must (+ G13) | `_kpi_card(_k4)` | Delta "model" (outline, `--muted`), sub "weighted MoS"; value-weighted | No delta, sub "vs model fair value"; simple mean |
| DB-10 | Chart headline value | Layout · Must | `db_card_chart` | 24px mono, margin-top 7px | 20px, margin-top 4px |
| DB-11 | Top movers | Layout · Must | `db_card_movers` | Ticker 12px mono/500 (64px), name 12px `--muted`, 52×22 diverging bar, chip; 8px rows with dividers; row opens the drawer | Name only, 36×5 bar from the left, no dividers, not clickable |
| DB-12 | Holdings ticker | Layout · Must | `holdings_row_html` | 13.5px mono/500 | 13px |
| DB-13 | Ladder labels | Layout · Must | `_fair_value_bar_html` | Price `--text`, "fv …" `--muted`, weight 400 | Weight 500, "fv" `--uv-muted` |
| DB-14 | "Full analysis →" | Layout · Must | `.st-key-db_conv_full_analysis` | `--link`, hover `--text` | `--teal`, hover `--mint` |
| DB-15 | Score card labels | Layout · Must | conviction HTML | "Weighted composite score" 11px uppercase `--muted`; "/ 100" `--muted` | 12px uppercase `--faint`; `--faint` |
| DB-16 | Alert badges | Must change (Code removals) | `dashboard.render` 629–672 | None | "· soon", "· cut", "· raised" |
| DB-17 | Risk meter bands | Gap → G12 | `risk_score_meter_html` | 0–33 / 33–66 / 66–100, LOW · MODERATE · ELEVATED | `risk.RISK_BANDS` 25 / 70, LOW · MODERATE · HIGH |
| DB-18 | Bottom-row heights | Layout · Should | `db_card_` rows | Cards stretch to the row height | Content height |

Matches: KPI set and tile style; chart range control, benchmark chips, legend row, 250px chart; 118px gauge; Beta / Volatility / Max drawdown; Holdings title, legend on the title row, description, grid; provenance placement; Refresh button.

### 2.4 Screener

| ID | Item | Category | Code location | Mockup value | Code value |
| --- | --- | --- | --- | --- | --- |
| SC-01 | No signal stocks | Must change | `screener.render` line 333 (`fillna(-999)`); line 203 (`_valued_df`) | Missing margin passes while Min margin of safety is −20% | Dropped |
| SC-02 | Default signal filter | Must change (follows from the Screener decision) | `st.pills(default=["undervalued"])`, `_filters_dirty` | None selected (all signals) | Undervalued only |
| SC-03 | Signal chips | Layout · Must (+ G20) | `_SIGNAL_CHIPS`; `.st-key-scr_signal_pills` | Five chips incl. No signal, each with its share; 10.5px/500; no visible note (Brand §8 keeps the note "share of covered stocks") | Four chips, 9px/400, note shown |
| SC-04 | Margin-of-safety colours | Must change | `components.stock_row` | `--up-txt` ≥ 15%, `--text` 0–15%, `--amber-txt` below 0; No signal "—" `--muted` | `--uv-mint` ≥ 15%, `--down-txt` below 0 |
| SC-05 | Score bar bands | Must change | `components._score_bar_cell_html` | Bar `--mint` ≥ 70, `--teal` 40–69, `--amber-fill` below 40; number `--up-txt` ≥ 70 | 75 / 55; number `--uv-mint` |
| SC-06 | Title | Must change | `screener.render` | 24px | 22px |
| SC-07 | "Hide positions I own" | Layout · Must | filter row | Toggle chip at the end of the filter bar | Missing |
| SC-08 | Rank column | Layout · Must | `_HH_WIDTHS`, `stock_row` | "#" 32px, right, 12px mono `--muted` | Removed |
| SC-09 | First column label | Layout · Must | `_SORT_COLUMNS` | "Company" | "Position" |
| SC-10 | Exchange tag | Layout · Must | `stock_row` | Short code (PAR, XET …) 9px mono `--muted` | City name 10.5px sans |
| SC-11 | Reset filters | Layout · Must | header | Always shown, `refresh` icon | Only after a change |
| SC-12 | Search icon | Layout · Must | `scr_search_wrap` | Search icon in the field | None; closest stable option is to keep it out (native input), a 15px difference |
| SC-13 | Slider values | Layout · Must | slider labels | `--up-txt` | `--mint` |
| SC-14 | Star colours | Layout · Must | `stock_row` | On `--up-txt`, off `--muted` | `--uv-mint`, `--uv-muted` |
| SC-15 | Subtitle | Layout · Must | `st.caption` | 13px, plain count | 14px, bold count |
| SC-16 | Filter gap | Layout · Should | `.st-key-scr_filter_row` | 22px | 32px |
| SC-17 | Show more | Layout · Should | `scr_more` | Outline button 8px 14px | Tertiary button |

Matches: filter panel, controls and ranges, results card, sticky header, row padding, badges with tooltip, page size 25 and label, empty state, provenance.

### 2.5 Watchlist

| ID | Item | Category | Code location | Mockup value | Code value |
| --- | --- | --- | --- | --- | --- |
| WL-01 | Remove control | Layout · Must | `watchlist.render` → `stock_row` | "×" in a 32px last column, `--muted`, hover `--down-txt` | "★" first column |
| WL-02 | First column label | Layout · Must | `_HH_LABELS` | "Company" | "Position" |
| WL-03 | Exchange tag | Layout · Must | `stock_row` | Short code | City name |
| WL-04 | Margin-of-safety colours | Must change | shared with SC-04 | Amber below 0 | Red |
| WL-05 | Title | Must change | `watchlist.render` | 24px | 22px |
| WL-06 | Duplicate ticker | Gap → G28 | add form | "Already on your watchlist." | Silent |
| WL-07 | Page width | Gap → G03 | frame | 1180px centred | Full width |

Matches: add-ticker card and button, empty state, provenance, columns.

### 2.6 Portfolio (overview, open, closed, dividends, cash)

| ID | Item | Category | Code location | Mockup value | Code value |
| --- | --- | --- | --- | --- | --- |
| PF-01 | Back links | Must change | `portfolio.render` (`back_open/closed/div`); `cash.render_page` | "← Back to Portfolio" | "← Back to Positions" |
| PF-02 | Titles | Must change | same | 24px | 22px |
| PF-03 | Open positions preview | Layout · Must | overview | Every open position | Top 5 + "Show all {count} positions" |
| PF-04 | Dividends received preview | Layout · Must | `portfolio_dividend_row` | Header "Position · paid" / "Net / gross"; name + type chip; "{TICKER} · paid {date}"; net `--up-txt` + gross line | "Position" / "Net dividend"; net only, `--mint` |
| PF-05 | Annual summary and tax box | Layout · Must | dividends (`_yc1`, `_yc2`) | Summary full width, tax box below, full width | 1.6 : 1, tax box right |
| PF-06 | Export buttons | Gap → G26 | `export_menu` | "Export CSV" / "Export log" / "Export summary" outline buttons (`download` icon) | "Export" menu |
| PF-07 | Closed page width | Layout · Must | closed | Title row and card max 760px | Full width |
| PF-08 | Full-page subtitles | Layout · Must | open, closed | None | Captions |
| PF-09 | Weight bar | Layout · Must | `portfolio_open_row` | `--teal` | `--uv-mint` |
| PF-10 | Dividends (12m) tile | Layout · Must | `_o5` | "net · {gross} gross" | "income received" |
| PF-11 | Dividend log chips | Layout · Must | `dividend_log_row` | Special `--amber-bg` / `--amber-txt`; Auto `--soft` / `--up-txt`; unconfirmed pay date `--amber-txt` | Fixed light tints in both themes; `--uv-mint`; `#C98A3A` text |
| PF-12 | Viewer chip | Layout · Must | `cash.render_page` | "Viewer · read-only" chip | None |
| PF-13 | Cash footnote | Layout · Must | `cash.render_page` | None | Long caption |
| PF-14 | Closed-trade dialog titles | Layout · Must | `dialogs.add/edit_closed_trade_dialog` | "Add closed trade" / "Edit closed trade" | "Add trade" / "Edit trade" |
| PF-15 | Income values | Layout · Must | cash tile, dividend nets, YoC | `--up-txt` | `--mint` / `--uv-mint` |

Matches: summary tiles, cash strip, column sets incl. DRIP, dividend tiles, tax texts, ledger, buys never blocked, dividend dialogs without declaration/record date/frequency (decided). Dialog radius 12px and Material close icon come with S03.

### 2.7 Risk

| ID | Item | Category | Code location | Mockup value | Code value |
| --- | --- | --- | --- | --- | --- |
| RK-01 | Notice order | Layout · Must | `risk.render` | Cash note, then estimates warning | Reverse |
| RK-02 | Title | Must change | `risk.render` | 24px | 22px |
| RK-03 | Gauge card width | Gap → G21 | `st.columns([1, 2.2])` | 300px : 1fr | 1 : 2.2 |
| RK-04 | Meter in gauge card | Layout · Must | gauge HTML | None | Adds the meter |
| RK-05 | Factor tier colours | Layout · Must | `_loading_tier` | Low `--up-txt`, Moderate `--amber-txt`, Elevated `#A32D2D` | `--uv-mint`, `#C98A3A` as text, `--down-txt` |
| RK-06 | Concentration bars | Layout · Must | concentration | `--teal`; over the reference `--amber-fill` | `--amber-txt` as fill |
| RK-07 | Flag colours | Layout · Must | flags | Amber `--amber-txt`; none `--muted` | `#C98A3A` text; `--faint` |
| RK-08 | Risk observations card | Gap → G22 | `risk_card_observations` | None | Present (PER-4) |

Matches: metric grid, factor bars, concentration card, contribution table, cash note.

### 2.8 Analysis

| ID | Item | Category | Code location | Mockup value | Code value |
| --- | --- | --- | --- | --- | --- |
| AN-01 | Score band label | Must change | header | 12px `--up-txt`: "Upper band · 70–100" etc.; "No signal · no peer reference"; "Excluded · fails quality screen" | "Upper/Middle/Lower range" in up / amber / red; nothing for No signal |
| AN-02 | Margin-of-safety tile | Must change | `_hero_card` | `--up-txt` ≥ 15%, `--text` 0–15%, `--amber-txt` below 0 | Green / red |
| AN-03 | Model summary | Layout · Must | `_render_model_summary` | Last card; 13.5px `--muted`; closing sentence "Generated from the model outputs above; the same text is shown to every user. It is not a recommendation to buy, hold or sell." | Second card; caption; no closing sentence |
| AN-04 | Founder notice link | Layout · Must | `components.founder_notice_html` | Code's sentence (12px `--muted`) followed by "Conflicts of interest policy →" in `--link` | Sentence only |
| AN-05 | Fair value tile | Layout · Must | `_hero_card` | `--up-txt` | `--text` |
| AN-06 | "Your position" tile | Layout · Must | `_hero_card` | "{n} shares · €{value}" 13px/500 sans | "{n} shares" 23px mono |
| AN-07 | Sub-score colours | Must change | `quality_score_color` | Bars `--mint` ≥ 70, `--teal` 40–69, `--amber-fill` below 40; text `--up-txt` / `--link` (G34) / `--amber-txt` | 70 / 45; base colours as text |
| AN-08 | Two-card rows | Layout · Must | three `st.columns(2)` | 1 : 1.25 (sub-scores : models); 1.25 : 1 (financials : checks) | 1 : 1 |
| AN-09 | Financials colours | Layout · Must | `_warn_colors` | Warnings `--amber-txt`, else `--text` | Up / down colours |
| AN-10 | "Lightly corroborated" | Must change (red only for a failed screen) | `fair_value_ladder` | Amber | `--uv-neg-txt` (red) |
| AN-11 | Sensitivity card | Layout · Must (+ G06) | `_render_history_and_sensitivity` | Four stats incl. Terminal growth; grid rows (label · fair value · margin of safety · badge); note about 8% → 9% | Three stats; key/value rows |
| AN-12 | Badge history header | Gap → G07 | history card | "Recomputed daily after EU close"; footer "Full log with inputs and model version is kept for every badge change." | No note; other caption |
| AN-13 | Producer card | Gap → G05 | `_render_sources_and_producer` | Mockup wording (see GL-15); link `--link` | Code wording; link `--teal` |
| AN-14 | DRIP toggle | Gap → G09 | `an_card_dividend` | DRIP box | None |
| AN-15 | Veto wording | Gap → G08 | banner, checks | "Hard veto active", "Hard-veto checks" | "Fails quality screen", "Quality screen checks" |
| AN-16 | Dividend panel colours | Layout · Must | `an_card_dividend` | YoC, "automatic", Auto chip `--up-txt` | `--uv-mint` |
| AN-17 | Page width | Gap → G03 | frame | 1180px centred | Full width |
| AN-18 | Chart height | Layout · Should | `plotly_chart` | 200px | 260px |
| AN-19 | Data-source flag dot and labels | Layout · Must | sources card | Label column `--muted` | `--faint` |

Matches: header, composite 30px, hero tiles, veto banner style, chart card, model ladder, checks list, payment history, cut box.

### 2.9 Stock drawer

| ID | Item | Category | Code location | Mockup value | Code value |
| --- | --- | --- | --- | --- | --- |
| DR-01 | Margin-of-safety tile | Must change | `drawer.open_drawer` | Amber below 0 | Red |
| DR-02 | Fair value tile | Layout · Must | `_cells` | `--up-txt` | `--text` |
| DR-03 | Fourth tile | Gap → G24 | `_cells` | Three tiles | "Implied return (est.)" added |
| DR-04 | Provenance | Gap → G23 (REC-5) | `signal_provenance_html` | One 11px mono line, no Methodology link | Provenance bar with link |
| DR-05 | Action order | Layout · Must | buttons | "View full analysis" full width, divider, records label, outline Edit / Record sale | Label first, three buttons in a row |
| DR-06 | Composite score colour | Layout · Must | `_score_color` | `--up-txt` | `--mint` |
| DR-07 | Veto title | Gap → G08 | veto box | "Hard veto triggered" | "Fails quality screen" |

### 2.10 Settings

| ID | Item | Category | Code location | Mockup value | Code value |
| --- | --- | --- | --- | --- | --- |
| ST-01 | Data & alerts | Must change (Code removals) | `set_card_data`; `_SECTIONS` | Not present | Present |
| ST-02 | Section rail | Must change | `_SECTIONS` | Language & region, Account security, Display, Target allocation, Dividend withholding, Import & export, Model settings, Legal | "Account", "Portfolio", "Data & alerts"; no Dividend withholding |
| ST-03 | Account security card | Must change + Layout · Must | `set_card_profile`, `set_card_security`, `set_card_sessions` | One card: Password, "Linked account · Google" ("Sign-in with Google is not available in the beta." / "Not in the beta"), Two-factor (mockup text "Authenticator app code at sign-in. Mandatory for admin roles." not adopted: two-factor deferred, the code's description stays), Backup codes and Trusted devices indented on `--panel-2`, Passkeys, Active sessions inside the card | Profile card, "Security" card, separate sessions card |
| ST-04 | Sessions | Must change (auth: no location) + Layout · Must | sessions rows | No location; meta "Signed in {time} · password + 2FA" / "Last seen {age} · password"; "This session"; "Sign out everywhere else" as a link top right | "{device} · signed in {date}"; "Current"; button at the bottom |
| ST-05 | Account footer | Layout · Must (+ G27) | `set_card_profile` | After the last card: avatar, name, "{email} · Free beta", outline Sign out | Top of the page; role; link-styled |
| ST-06 | Model settings card | Gap → G14 | `set_card_screening` | "Model settings in force" read-only list | Admin sliders |
| ST-07 | Subtitle | Gap → G19 | `support_page(subtitle)` | Mentions privacy and plan | Other text |
| ST-08 | Table density | Gap → G15 | `set_card_display` | Theme + Table density | Theme only |
| ST-09 | Target allocation rows | Layout · Must | `set_card_targets` | Label left / control right; no description | Side-by-side textareas, description |
| ST-10 | Withholding anchor | Must change | `set_card_dividend_tax` | `set-withholding` | None |
| ST-11 | Import & export | Layout · Must (+ G16) | `set_card_import` | Stacked rows, buttons right | Two columns, dropzone |
| ST-12 | Backup codes, trusted devices | Layout · Must | rows | "{n} of 10 unused. Regenerating replaces the old set." / "{n} devices skip the code until {date}." | Other texts |
| ST-13 | Legal card | Gap → G18 | `set_card_legal` | "Legal documents", rows, English-only footnote | "Legal", six links, privacy e-mail sentence |
| ST-14 | Language & region card | Layout · Must | `locale_ui.render_card`, `_preview` | Row descriptions; currency as EUR/USD/GBP/CHF segmented with "Follows region · {region}" / "Use region default"; date format as three radio cards with examples; week-start status line; preview band on `--panel-2` with tag chip "{region} · {currency}", five values and "Try a number"; "✓ Saved to your profile" (11.5px `--up-txt`) in the header; right-aligned reset bar "Return all six settings to the detected defaults?" | No descriptions (except currency); currency select; segmented date format; bordered preview without tag or number field; toast "Settings saved"; tertiary reset button |
| ST-15 | Value colours | Layout · Must | `_slider_label`, row hints | Slider values `--up-txt`; hints `--muted` | `--mint`; some `--faint` |
| ST-16 | Passkeys row | Deferred (passkeys, G33) | `set_row_passkeys` | "2 registered: MacBook Pro, iPhone 15" + Manage | "Not available in the beta." + disabled Manage (unchanged) |

Matches: frame (left-aligned, 200px rail, 32px gap, 760px content), card headers, Theme control, withholding grid and save.

### 2.11 Methodology

| ID | Item | Category | Code location | Mockup value | Code value |
| --- | --- | --- | --- | --- | --- |
| ME-01 | Title and menu label | Must change | `app.py` line 119; `help.render`; `shell.py` | "Methodology" | "Methodology & help" |
| ME-02 | Card order and rail | Layout · Must | `_render_cards`, `_rail` | Badges, Reading the badges, Models, Quality screens, FAQ, Data sources, Conflicts, About; rail incl. About | FAQ after Conflicts; no About |
| ME-03 | Links row | Layout · Must | first block | In the header, 12px `--link` | Content column, `--teal` |
| ME-04 | Reading the badges | Layout · Must | `help_card_reading` | Four columns incl. "Coverage today"; labels 10px uppercase `--muted`; three notes incl. Sensitivity | Three columns; two notes |
| ME-05 | Data sources labels | Layout · Must | `help_card_sources` | 120px `--muted` | 110px |
| ME-06 | FAQ prices answer | Must change (Code removals) | `_FAQ` | No reference to Settings › Data | Refers to Settings → Data |
| ME-07 | Badges card | Gap → G32 | `help_card_signals` | "Badges · meaning and thresholds" with numbers | Threshold words |
| ME-08 | Models title | Gap → G07 | `help_card_models` | "The six fair-value models" | "The fair-value models" |
| ME-09 | Conflicts and About texts | Gap → G05, G35 | conflicts, about cards | Mockup wording, no support-refusal line | Code wording with PER-6 line |
| ME-10 | Quality-screen title | Gap → G08 | `help_card_vetoes` | "Hard-veto rules" | "Quality screens" |

### 2.12 Legal

| ID | Item | Category | Code location | Mockup value | Code value |
| --- | --- | --- | --- | --- | --- |
| LG-01 | Document header | Layout · Must (+ G02) | `legal._document` | Eyebrow "Uvalu · Legal" (10.5px uppercase `--muted`) with print button on the same row; title below (30px in the mockup, 20px in Brand §5); chips; divider 24px 0 6px | Title 20px with print button beside it; no eyebrow |
| LG-02 | Body text colour | Layout · Must | `.st-key-uv_support_content p, li` | `--muted` | `#3E3D3A` / 85% white |
| LG-03 | English-only note | Layout · Must | rail | 11px `--muted` note under the rail | Notice in the card when untranslated |
| LG-04 | List bullets | Layout · Must | long-form CSS | "•" in `--link` | Default bullets |
| LG-05 | Card padding | Layout · Should | `.st-key-legal_doc_body` | 30px 44px 40px | 28px 32px 32px |

### 2.13 About

| ID | Item | Category | Code location | Mockup value | Code value |
| --- | --- | --- | --- | --- | --- |
| AB-01 | Button hover | Layout · Must | `_copy_button`, `legal._print_button` | Hover border `--teal` (token) | Literal `#1A8C6E` |

Matches: rail, build rows, support line, "This version"; release list in `st.expander` (Accept the framework).

### 2.14 Sign-in and invitation (`uvalu/authgate.py`; `Uvalu.dc.html` sign-in, `Uvalu Auth.dc.html` frames 01–07)

| ID | Item | Category | Code location | Reference value | Code value |
| --- | --- | --- | --- | --- | --- |
| AU-01 | Provider buttons | Must change (auth) | `_render_provider_buttons` (sign-in, lock-out, invite) | None in the beta (password only); provider screens marked "later" | Configured providers as buttons; Microsoft as "NOT CONFIGURED" |
| AU-02 | Sign-in footer | Must change (auth) | hero foot (`_foot`) | Full disclaimer, producer line with "Not authorised…", and the six legal links (`#3FBF98` on navy), 11px at 60% white | Disclaimer and producer line at 35% white; no links |
| AU-03 | Lock-out note | Must change (auth) | lock-out frame | "The lock applies to password sign-in only." | Adds "Providers are unaffected." |
| AU-04 | Forgot password | Layout · Must | `_render_forgot` | "During the beta Uvalu doesn’t send emails. Ask your admin to reset your password. They give you a single-use link, valid for 30 minutes." + outline "Back to sign in" | "Uvalu has no automated password reset — ask an admin to send you a one-time reset link from the Admin portal." |
| AU-05 | Form title | Must change | `.uv-login-heading` | 24px (main mockup) | 22px |
| AU-06 | Hero headline and stats | Decided: tagline (G06) + Gap → G07 | hero | Main mockup: "Calculate fair value with six models."; Auth mockup: tagline "Find value before the market does."; stats 6 / 6 / "Daily" | "five models"; 5 / 6 / "24 h" |
| AU-07 | "New to Uvalu?" | Gap → G29 | form | "Accept your invitation" (main) / "Ask for an invite" (Auth), `--link` | "Ask your admin for an invite", `--teal` |
| AU-08 | Link and icon colours | Layout · Must | "Forgot?", field icons | `--link`; Material `mail` / `lock` icons `--muted` | `--teal` |
| AU-09 | Invitation consent | Deferred (G30) | `_render_invite_accept` | EEA country, refusal state, three unticked boxes stored with version and time; re-acceptance screen | Password only |

Matches: two-panel layout, field labels, Sign in button, wrong-password and lock-out states, breached-password block, provider-identity screen (kept for later), two-factor challenge and backup-code dialogs.

### 2.15 Admin (`uvalu/pages_/admin.py`; `Uvalu Admin.dc.html`, `Uvalu Auth.dc.html` frames 16–17)

| ID | Item | Category | Code location | Reference value | Code value |
| --- | --- | --- | --- | --- | --- |
| AD-01 | Account creation | Must change (auth) | `_render_security` (auto-provision toggle); `auth.oauth_login`; `settings.auto_provision_oauth` | "Invitation only." fixed, shown as "Invite only · fixed" | Toggle "auto-provision" with allowed domains |
| AD-02 | MFA requirement | Deferred (two-factor, G31) | `_render_security` (`require_mfa`); `auth.login`; `authgate` | Always required for admins | Policy Off / Admins / Everyone, stored only, not enforced (unchanged) |
| AD-03 | Identity providers | Must change (auth) | `_render_security` providers list | Google "NOT CONFIGURED · Not in the beta" | Configured state from secrets |
| AD-04 | Section order | Gap → G25 | `_NAV_ITEMS` | Users, Data feeds, System, Backups (Admin mockup); Security after Backups (Auth mockup) | Users, Security, Data feeds, Backups, System |
| AD-05 | System title | Layout · Must | `_SECTION_TITLES` | "System" | "System & versions" |
| AD-06 | Text colours | Layout · Must | 23 `--faint` uses | Readable text `--muted` | `--faint` |
| AD-07 | Logo accent | Layout · Must | sidebar | "u" in `--link` (Admin mockup) | `--teal` |

Matches: shell, stat tiles, users table without a Plan column (the Admin mockup still has "Pro Plan"; not used, free beta), feeds, backups, System cards, invite and restore dialogs.

## 3. Gaps needing a decision

| ID | Gap | Recommendation | Alternative | Step |
| --- | --- | --- | --- | --- |
| G02 | Legal document title: mockup 30px, Brand §5 "Document title 20px" (code has 20px). | 20px (no change). | 30px. | S24 |
| G03 | Data-screen width: mockup caps wide pages at 1440px and Watchlist and Analysis at 1180px (centred); Brand §7 says data screens use the full content width. | Brand: full width, no cap (at 1280px only Watchlist and Analysis differ). | Mockup caps. | S04 |
| G04 | Nav icon size: mockup 16px, Brand §6 "20px in navigation". | 16px (mockup and code agree). | 20px. | S10 |
| G05 | **Legal.** Producer line format and the producer, conflicts and About texts. Same facts; REC-1 and BIZ-3 still met. | Adopt the mockup wording; legal review. | Keep the code's. | S28 |
| G07 | **Legal (accuracy).** "six models" (sign-in, Methodology title) and "Daily" / "Recomputed daily after EU close": the app has five models plus fallbacks and recomputes when fundamentals refresh (the daily build, S4 in the compliance plan, is not done). | Keep "5", "24 h · model update cycle" and "The fair-value models"; no "daily" claims until S4 ships. | Adopt the mockup. | S18, S23, S25 |
| G08 | **Legal / brand.** Mockup says "Hard veto active / triggered", "Hard-veto checks", "Hard-veto rules". Brand §9 lists "hard veto" under Avoid; `tests/test_legal_guards.py` bans it. | Keep the code's wording. | Change guard and brand (not advised). | S18, S19, S23 |
| G09 | DRIP toggle on Analysis: no per-holding DRIP data. | Leave out. | New per-holding field. | S18 |
| G10 | Peer-reference rebuild: strip + No signal badges (mockup) vs skeletons (code). | Add the strip; keep skeletons. | No signal badges. | S11 |
| G11 | Error box: the mockup text is about portfolio data; the handler doesn't know what failed. | "Couldn’t load this page. Try again in a moment." + reference line. | Mockup text. | S11 |
| G12 | **Legal.** Risk meter bands 33/66 (mockup) vs methodology.md and `risk.RISK_BANDS` 25/50/70/85 (Brand §8 Charts names the same five bands). | Keep the code's bands. | Mockup bands. | S12, S17 |
| G13 | Avg margin of safety: value-weighted (mockup) vs mean. | Value-weighted. | Mean with a new sub-label. | S12 |
| G14 | Model settings card: read-only list (mockup, user view) vs admin sliders. | Read-only list for everyone; sliders below for admins (D2). | List only. | S22 |
| G15 | Table density row. | Restore; extend the compact rule to Screener, Watchlist and Portfolio rows. | Remove setting and CSS. | S22 |
| G16 | Import & export texts claim cash and re-import; the code does neither. | Keep the code's texts; adopt the row layout. | Build round-trip first. | S22 |
| G17 | **Legal.** Sensitivity table badge per scenario vs D2 "never changes a badge". | No badge column; add Terminal growth. | Badge column. | S18 |
| G18 | Settings › Legal card while acceptance rows are deferred. | "Legal documents", six links, privacy e-mail sentence, English-only footnote. | Keep "Legal". | S22 |
| G19 | Settings subtitle names deferred privacy and plan. | Drop them while deferred. | Mockup text. | S22 |
| G20 | **Legal.** Chip label "Fails screen" vs badge label "Fails quality screen". | Full label. | Short. | S09 |
| G21 | Risk gauge width 300px vs 1 : 2.2 (your earlier feedback). | Keep 1 : 2.2. | 300px. | S17 |
| G22 | Risk observations card (PER-4) not in the mockup. | Keep. | Remove. | S17 |
| G23 | **Legal.** Drawer provenance without Methodology link (REC-5). | Keep the code's provenance bar. | Mockup line + link. | S19 |
| G24 | Drawer "Implied return (est.)" tile. | Remove. | Keep. | S19 |
| G25 | Admin section order differs between the two mockups. | Users, Data feeds, System, Backups, Security. | Code order. | S26 |
| G26 | Export buttons vs the format menu. | Keep the menu, labelled "Export CSV" / "Export log" / "Export summary". | Plain CSV buttons. | S15, S16 |
| G27 | "Free beta" chip instead of the role (menu, Settings footer). | "Free beta" in both; role in Admin. | Keep the role. | S10, S20 |
| G28 | Watchlist duplicate message. | Add it. | Leave. | S14 |
| G29 | "New to Uvalu?" link: "Accept your invitation" (main) vs "Ask for an invite" (Auth); there is no self-service invitation page. | "Ask for an invite" as plain text (Auth mockup). | "Accept your invitation". | S25 |
| G32 | Methodology badge definitions with live numbers vs threshold words. | Live numbers. | Words. | S23 |
| G34 | Sub-score middle band text in `--link` (mockup): a link colour on non-link text. | `--text` for the middle band. | `--link` as in the mockup. | S08 |
| G35 | **Legal.** Mockup's About card drops the support-refusal line (PER-6). | Keep it. | Remove. | S28 |
| G36 | **Legal.** Breached-password check (Have I Been Pwned by hash prefix) is not in the beta privacy notice ("still to confirm"). The 30-day trusted-device cookie is already listed (`uv_td`). | Add one sentence on the hash-prefix check to the security section; legal review. | Leave out. | S27 |

### Decided on 9 October

| ID | Gap | Decision | Effect |
| --- | --- | --- | --- |
| G01 | Beta bar shape (strip in the reference, box in Brand §8) | Rounded box (Brand §8) | S11 keeps the box; `Design reference.md` and the mockup need the same change in the design project (S28) |
| G06 | Sign-in headline | The tagline "Find value before the market does." | S25 |
| G30 | Invitation consent (EEA country, three stored boxes, re-acceptance) | Deferred | Not in this plan (section 5) |
| G31 | Two-factor for admins (enforcement, policy options, grace period, Settings text) | Deferred | The MFA-enforcement step is removed; S26 and S20 leave the MFA policy and texts as they are |
| G33 | Passkeys (Settings row, privacy-notice wording) | Deferred | Settings row and privacy-notice passkey sentences unchanged |

## 4. Steps

Every step runs `python tools/i18n_update.py`, drafts new entries (fuzzy) in nl, fr, de, it, es and en, runs `python tools/i18n_compile.py` and `python tools/i18n_review_csv.py`, and pastes `python tools/i18n_update.py --since master` into the PR. Verification uses `/run-uvalu` (SSL off) at 1280px in light and dark next to the named mockup screen, plus a 920px spot-check.

### S01 · Brand v1.3 tokens

- **Why:** reference, colours per Brand v1.3; BR-01, BR-02 (tokens), BR-07, BR-08, BR-10.
- **Files and functions:** `uvalu/styles.py` (`GLOBAL_CSS` token blocks); `.streamlit/config.toml`; `uvalu/runtime.py` (`ThemeColors`, `theme_colors`).
- **Changes:** add `--link` (`#3FBF98` dark, `#167A60` light), `--logo-accent` (`#1DD6A4` / `#1A8C6E`), `--veto-bg` (`#1E2D4A` / `#0D1F3C`), `--veto-line` (`rgba(245,247,250,0.18)` / transparent), `--nosig-bg` (`rgba(245,247,250,0.07)` / `rgba(128,128,128,0.15)`). Add the `:focus-visible` ring (2px solid, offset 2px, `--teal` light, `--mint` dark) and the `prefers-reduced-motion` rule. `config.toml`: dark `primaryColor` `#1A8C6E`; `linkColor` `#167A60` / `#3FBF98`. `ThemeColors.link`. Leave every other token value as it is (they match v1.3).
- **Strings:** none. **Data and settings impact:** none.
- **Risks and open questions:** dark primary buttons change from mint to teal with white text (4.2:1, as in the mockup). Streamlit widgets that follow `primaryColor` (toggles, sliders, focus) change colour too.
- **Tests:** new `tests/test_styles.py`: every v1.3 token defined in both blocks; contrast of `--link`, `--muted`, `--up-txt`, `--amber-txt`, `--down-txt` against `--panel` ≥ 4.5 in both themes.
- **How to verify:** Settings and Dashboard in both themes: buttons, links (after S02), keyboard Tab shows the ring.
- **Size:** S. **Depends on:** none.

### S02 · Use the tokens: links, positive text, amber text, badges, logo

- **Why:** BR-02, BR-04, BR-05, BR-09; Brand §4 usage rules and §8 badges and links.
- **Files and functions:** `components.py` (`methodology_link_html` CTA variant, `signal_badge_html`, `stock_row` star, `fair_value_ladder` composite row, `portfolio_open_row` YoC, `portfolio_dividend_row`, `dividend_log_row`, `_CASH_TYPE_STYLE`, `MINT_CHIP_STYLE`, `_cash_ledger_row_html`); `shell.py` (logo, footer links); `update_notice.py`; `dialogs.py`; pages; `drawer.py`; `authgate.py`; `styles.py` (`.uv-badge-*`, `.st-key-db_conv_full_analysis`).
- **Changes:** link text → `--link` (hover `--text`); positive figures and labels on any theme → `--up-txt`; `#C98A3A` / `--amber-fill` as text → `--amber-txt`; keep Mint on navy surfaces and as fills. Badges: one rule set on the token pairs for both themes, Fails quality screen on `--veto-bg` with a `--veto-line` inset hairline, No signal / No data on `--nosig-bg` with `--muted`; remove `min-width:64px` and `letter-spacing`. Logo "u" → `--logo-accent`. Special-dividend chip → `--amber-bg` / `--amber-txt`.
- **Strings:** none. **Data and settings impact:** none.
- **Risks and open questions:** about 60 edits; list remaining base-colour hits as fills in the PR (`grep -nE "var\(--(uv-)?mint\)|#1DD6A4|#C98A3A|var\(--teal\)|#1A8C6E"`).
- **Tests:** `tests/test_components.py` (badge and colour assertions); new `tests/test_styles.py::test_no_mint_or_teal_text` (scan of `color:` declarations, allow-list for navy surfaces).
- **How to verify:** light theme on every main screen: no mint text on white, links dark green; badges against mockup Screener rows.
- **Size:** M. **Depends on:** S01.

### S03 · Readable text off `--faint`, radii, Material icons in markup

- **Why:** BR-03, BR-06; Brand §4 ("`--faint` decoration only"), §7 radii, §6 icons; GL-13 icon.
- **Files and functions:** every file in the `--faint` count (section 2.1); `styles.py`; radii in `styles.py`, `authgate.py`, `drawer.py`, `risk.py`, `settings.py`; `components._stale_chip_html`; `dialogs.py` close buttons.
- **Changes:** `--faint` → `--muted` for every readable text (uppercase column headers in `header_cell_html` and the hand-built headers, tile labels, sub-captions, empty states, footer producer line, admin labels); keep `--faint` for separators, dots, rings, disabled fills and placeholders. Radii 7/9/10 → 8px, 14 → 12px. Stale chip: Material `warning` symbol (14px) instead of "⚠", 11px, padding 1px 8px, tooltip text per GL-13. Any remaining inline SVG icons in markup → Material Symbols outlined (16px inline).
- **Strings:** add "Some prices are more than 72 hours old. Signals for those stocks use the last known price."; remove the "{count} price(s) is/are more than 72 hours old." plural.
- **Data and settings impact:** none.
- **Risks and open questions:** mechanical but wide; keep it alone in its PR with before/after screenshots of every screen.
- **Tests:** `tests/test_components.py` (stale chip lines 602–603, header cell colour); new `tests/test_styles.py::test_no_faint_text` (scan for `color:var(--faint)` on text elements with an allow-list) and `test_only_brand_radii`.
- **How to verify:** both themes, every screen: secondary text slightly stronger, nothing else moves; stale chip with Tweak `dataState` stale.
- **Size:** M. **Depends on:** S02.

### S04 · Page frame and page header

- **Why:** "All page titles 24px"; GL-03, GL-16 (G03), DB-08, SC-15, AU-05; Brand §7 page layouts.
- **Files and functions:** `styles.py` (shared values); `components.py` (new `page_frame(kind)`, `page_header(...)`, `back_link(...)`); page headings; `.uv-login-heading`.
- **Changes:** shared values `--uv-page-pad: 22px 28px 60px`, `--uv-section-gap: 18px`, title 24px/500/−0.02em/1.2, subtitle 13px `--muted` (2px below on data pages, 4px on supporting pages), provenance 8px below. `page_frame`: keyed container (`st-key-uv_page_data` / `st-key-uv_page_support`); width per G03 (recommended: data pages full width, supporting pages unchanged at 1180px left-aligned). `page_header`: title, subtitle, provenance, actions right. `back_link`: 12px `--muted`, hover `--text`, "← Back to {page}". Sign-in form title 24px.
- **Strings:** none. **Data and settings impact:** none.
- **Risks and open questions:** the new wrapper vs `margin-top:-16px` rules; measure title offsets before and after.
- **Tests:** `tests/test_pages_*.py` that look for `font-size:22px`; new `tests/test_components.py::test_page_header_renders_title_subtitle_and_actions`.
- **How to verify:** every page title at the same x and size; header spacing 2px / 8px against mockup Dashboard; 920px: buttons wrap under the title.
- **Size:** M. **Depends on:** S03.

### S05 · Shared cards, table headers and tiles

- **Why:** Layout fidelity (shared values); Brand §7 spacing and §8 metric cards.
- **Files and functions:** `styles.py`; `components.py` (`card_header_html`, `table_header_html`, `kpi_card`, `header_cell_html`).
- **Changes:** card family (`--panel`, 0.5px `--line`, 12px radius, `--shadow`; padding 18px, 18px 20px or 0). `card_header_html`: data cards 16px 20px 14px with `--line-2`; supporting cards 14px 20px; title 15px/500. `table_header_html`: 10px uppercase 0.06em `--muted`, padding 10px 20px, numbers right. Rows 12px 20px, hover `--soft`. `kpi_card(size="lg"|"md")`: 26px (Dashboard) / 23px (Portfolio, Cash, Dividends, Analysis); label 10.5px uppercase `--muted`/500. Section gap 18px.
- **Strings:** none. **Data and settings impact:** none.
- **Risks and open questions:** 16 → 18px gaps move every section by 2px.
- **Tests:** `tests/test_components.py`.
- **How to verify:** Dashboard and Portfolio overview against the mockup at 1280px.
- **Size:** M. **Depends on:** S04.

### S06 · Label changes

- **Why:** "Label changes for the code"; "← Back to …"; "Margin of safety"; ME-01, ST-02, PF-01, DB-01 (header).
- **Files and functions:** `app.py` line 119; `help.render` and translator comments; `shell.render_topbar`; `settings._SECTIONS` and the Security header; `portfolio.render` back buttons; `cash.render_page`; `dashboard.render` headers; `CHANGELOG.md` [2026.10.2] (About › What's new).
- **Changes:** "Methodology & help" → "Methodology"; "Account" → "Account security" (rail and card heading); "Portfolio" → "Target allocation" (rail); "← Back to Positions" → `_("← Back to {page}", page=_("Portfolio"))`; "MoS %" → "Margin of safety".
- **Strings:** remove "Methodology & help", "Account", "← Back to Positions", "MoS %", "Security" (if unused); reuse "Methodology", "Target allocation", "Margin of safety", "← Back to {page}"; add "Account security". Six catalogues.
- **Data and settings impact:** none.
- **Risks and open questions:** none.
- **Tests:** `tests/test_pages_portfolio.py` lines 93, 214; `tests/test_i18n.py` line 502; `tests/test_pages_help.py`; `tests/test_shell.py`; `tests/test_pages_settings.py`.
- **How to verify:** menu, Methodology, Settings rail, Portfolio back links, Holdings header, About notes; `?lang=de`.
- **Size:** S. **Depends on:** none.

### S07 · Settings: remove Data & alerts

- **Why:** "Code removals"; ST-01, ST-10, DB-16, ME-06; G (compliance-plan row, S29).
- **Files and functions:** `settings.py` (page: `_SECTIONS`, `set_card_data`, withholding header, docstring); `uvalu/ui.price_autorefresh`; `dashboard.render` 629–672; root `settings.py` `_USER_DEFAULTS`; `help._FAQ`; `styles.py` (`set_row_refresh`); `docs/architecture.md` line 289.
- **Changes and readers:**

  | Setting | Reader | Outcome |
  | --- | --- | --- |
  | `refresh_interval_s` (`refresh`) | `ui.price_autorefresh` (Dashboard, Portfolio, Risk) | Fixed default: `PRICE_REFRESH_S = 60` in market hours, 900s outside (unchanged rule) |
  | `alert_dividend_ex_date` (`alert_ex_div`) | Dashboard "· soon" badge | Removed with the badge |
  | `alert_dividend_size_threshold_pct` (`alert_dividend_size`) | Dashboard, gate for "· soon" | Removed |
  | `alert_dividend_cut` (`alert_div_cut`) | Dashboard "· cut" badge | Removed (the cut stays on the Analysis page) |
  | `alert_dividend_increase` (`alert_div_increase`) | Dashboard "· raised" badge | Removed |
  | `alert_price_target` | none | Removed (unused) |

  Withholding header gets `anchor="set-withholding"` and a rail entry between Target allocation and Import & export. FAQ answer: "During the free beta prices are delayed quotes from Yahoo Finance; each signal shows the time of the price it used. Fundamentals are refreshed about every 24 hours. Real-time prices are not offered."
- **Strings:** remove "Data & alerts", "Price refresh interval" and its description, "Ex-dividend alerts" + description, "Only above this position weight", "any size", "0% flags every held ex-date; raise it to only badge your larger positions.", "Dividend cut / suspension alerts" + description, "Dividend increase alerts" + description, "· soon", "· cut", "· raised"; keep "{minutes} min" (lock-out uses it); change the FAQ answer.
- **Data and settings impact:** old keys stay in stored settings and are ignored; no migration. Users with 30s or 300s get 60s.
- **Risks and open questions:** none.
- **Tests:** remove `test_changing_refresh_interval_persists`; update `test_section_nav_links_every_card_anchor`; `tests/test_ui.py` line 314; new `test_upcoming_dividends_have_no_alert_badges`, `test_settings_order_matches_reference`.
- **How to verify:** Settings rail and order against mockup `startPage=settings`; Dashboard dividends; Methodology FAQ.
- **Size:** M. **Depends on:** S06.

### S08 · Signal colours and score bands

- **Why:** decisions on margin colours, red reserved, score bands 70/40, Holdings P&L; Brand §8 fair-value ladder; DB-01–DB-04, SC-04, SC-05, WL-04, AN-01, AN-02, AN-07, AN-09, AN-10, DR-01, G34.
- **Files and functions:** `components.py` (new `mos_text_color`, `score_band`, `score_band_label`; `holdings_row_html`, `stock_row`, `_score_bar_cell_html`, `quality_score_color`, `_ladder_bar_color`, `fair_value_legend_html`, `fair_value_ladder`); `dashboard.render`; `analysis.render`; `drawer.open_drawer`.
- **Changes:** margin text `--up-txt` ≥ 15, `--text` 0–15, `--amber-txt` below 0. Score bands: upper ≥ the Undervalued threshold (70), middle ≥ 40; bars `--mint` / `--teal` / `--amber-fill`; numbers `--up-txt` in the upper band, `--text` otherwise; sub-score text `--up-txt` / middle per G34 / `--amber-txt`. Band labels "Upper band · 70–100" etc. in `--up-txt`; "No signal · no peer reference"; "Excluded · fails quality screen". Dashboard ring `--mint`, never red. Holdings P&L as a % chip with tooltip. Ladder fills `--up-txt` / `--axis` / `--amber-fill` (±3% band kept); legend swatches the same, radius 4px. "Lightly corroborated" and financial warnings `--amber-txt`.
- **Strings:** add "Upper band · {low}–{high}", "Middle band · {low}–{high}", "Lower band · {low}–{high}", "No signal · no peer reference", "Excluded · fails quality screen", "Unrealised result against your average cost"; remove the six "… range" labels and "Excluded · fails a quality screen".
- **Data and settings impact:** none.
- **Risks and open questions:** bands follow the shared Undervalued threshold; confirm that a changed threshold should move the band label.
- **Tests:** `tests/test_components.py` (score bar, `quality_score_color` 550–556, `_ladder_bar_color` 656, holdings row); `tests/test_data_contracts.py` 121–130; new in `tests/test_compliance_algorithms.py`: `test_band_labels_carry_no_verdict_words`, `test_mos_colour_is_never_red`, `test_only_a_failed_screen_is_red`.
- **How to verify:** Holdings, score card, Screener, Analysis, drawer against the mockup in both themes.
- **Size:** M. **Depends on:** S02.

### S09 · Screener: No signal stocks at the default filters

- **Why:** Screener filter decision; SC-01–SC-03; G20.
- **Files and functions:** `screener.py` page (`_SIGNAL_CHIPS`, `render`).
- **Changes:** keep rows without a fair value; a missing margin passes while Min margin of safety is −20; pills default to none; add the No signal chip ("pending"); chip label per G20.
- **Strings:** none new.
- **Data and settings impact:** none.
- **Risks and open questions:** "{shown} of {total}" now counts unvalued rows.
- **Tests:** `tests/test_pages_screener.py`: visible at defaults, hidden when Min MoS or Min score is raised, default filter empty.
- **How to verify:** mockup Screener (Adyen) vs a pending row in the app.
- **Size:** S. **Depends on:** none.

### S10 · Top bar and user menu

- **Why:** GL-05–GL-08, BR-09; G04, G27.
- **Files and functions:** `shell._topbar_css`, `shell.render_topbar`.
- **Changes:** logo 22px, "u" `--logo-accent`, tagline 10px `--muted`. Nav 13px/500, padding 7px 13px, active `--soft` + `--text`, hover `--line-2`; icon size per G04. Theme toggle 34×34 transparent with `--line` border, `--muted` icon. Menu: name 13px/500, e-mail 11px mono `--muted`, chip per G27 (radius 6px, `--soft`, `--up-txt`); items Settings (`settings`), Methodology (`info`), About Uvalu (`layers`), Admin portal (`shield`), divider, Sign out (`logout`) in `--down-txt`. No "Legal & policies" item.
- **Strings:** add "Free beta" if G27 accepted.
- **Data and settings impact:** none.
- **Risks and open questions:** removing "Legal & policies" leaves footer and Settings as routes; confirm.
- **Tests:** `tests/test_shell.py`.
- **How to verify:** top bar and menu against the mockup in both themes; 920px nav doesn't wrap.
- **Size:** M. **Depends on:** S02, S06.

### S11 · Notices, beta bar, footer and error state

- **Why:** GL-01, GL-02, GL-04, GL-09–GL-12, GL-14; Brand §8 disclosures; G01, G10, G11.
- **Files and functions:** `shell.py` (`render_beta_banner`, `render_footer`, `_FOOTER_CSS`, `render_maintenance`, `render_error_reference`, new `render_peer_rebuild_strip`); `update_notice.py`; `app.py`.
- **Changes:** shared strip style (padding 8px 28px, bottom `--line-2`); update notice and reload prompt on `--panel`, links `--link`, "●" `--up-txt`. Beta bar stays the rounded box (G01, Brand §8: `--soft`, 0.5px `--line`, radius 8px, 11.5px `--muted`) with "Beta" 600 in `--up-txt` and a "Terms →" link in `--link` to `/legal?doc=terms`; the box keeps its own inset inside the page gutter. Order: update, reload, beta, peer strip, error. Peer strip and error box per G10/G11 (box radius 8px). Footer left-aligned per GL-04. Maintenance version line mono `--muted`.
- **Strings:** add "Terms →", the peer-rebuild text, the G11 error text.
- **Data and settings impact:** none.
- **Risks and open questions:** none beyond the gaps.
- **Tests:** `tests/test_shell.py`, `tests/test_update_notice.py`, `tests/test_legal_guards.py::test_footer_carries_disclaimer_producer_and_supervision_note`; new `test_peer_rebuild_strip_shown_only_while_pending`, `test_notice_order`.
- **How to verify:** Tweaks `updateNotice`, `newBuild`, `beta`, `dataState`, `appState`, `environment` against the app in both themes.
- **Size:** M. **Depends on:** S02, S04.

### S12 · Dashboard: header, tiles, chart and score card

- **Why:** DB-07–DB-10, DB-14, DB-15, DB-17; G12, G13.
- **Files and functions:** `dashboard.render`; `components.kpi_card`.
- **Changes:** header with Refresh and Add position; subtitle text; Avg margin of safety value-weighted with "model" delta and "weighted MoS"; chart headline 24px; score-card labels `--muted`.
- **Strings:** new subtitle; add "model", "weighted MoS"; remove "vs model fair value".
- **Data and settings impact:** none.
- **Risks and open questions:** G12 keeps the meter bands.
- **Tests:** `tests/test_pages_dashboard.py`.
- **How to verify:** mockup Dashboard top half.
- **Size:** M. **Depends on:** S04, S05, S08.

### S13 · Dashboard: Holdings, sector allocation, dividends, movers

- **Why:** DB-05, DB-06, DB-11–DB-13, DB-18.
- **Files and functions:** `dashboard.render`; `components.py` (`holdings_row_html`, `_fair_value_bar_html`, new `donut_html`, `mover_row_html`).
- **Changes:** Holdings ticker 13.5px; ladder labels weight 400 with "fv" in `--muted`. Sector card: SVG donut 132px (r 52, stroke 17) with 2px `--panel` gaps between slices (Brand §8 Charts), centre "TOTAL" (10px 0.06em `--muted`) and short total (14px mono), legend list right (gap 6px, 8px swatch radius 4px, 11.5px `--muted` label with ellipsis, mono % in `--text`), palette `ui._DONUT_PALETTE` (top 11 + "Other" above 12). Upcoming dividends: header right "{€k} / yr fwd" 11px mono `--up-txt`; column header "Ex-date · payment" / "Net est." (10px uppercase `--muted`); rows with a 38px date block (15px mono day, 9px uppercase month), name 12.5px, "ex-date · pays {date}" 10.5px mono `--muted` (payment date only when yfinance `dividendDate` ≥ the ex-date, otherwise "ex-date"), net 12.5px mono `--up-txt` + "{gross} gross" 10px `--muted`; five rows. Top movers: ticker 12px mono/500 (64px), name 12px `--muted`, 52×22 diverging bar (up to the right of centre in `--up-txt`, down to the left in `--down-txt`), day chip; 8px rows with `--line-2` dividers; whole row opens the drawer (invisible button, as `db_hold_`). Bottom-row cards stretch to the row height.
- **Strings:** add "Ex-date · payment", "Net est.", "ex-date · pays {date}", "ex-date", "{amount} / yr fwd"; remove "{date} · {yield_pct} yield", "{amount} / yr".
- **Data and settings impact:** payment date from yfinance `dividendDate` when ≥ the ex-date.
- **Risks and open questions:** the donut loses the Plotly hover amount.
- **Tests:** `tests/test_pages_dashboard.py`; `tests/test_components.py`.
- **How to verify:** mockup Dashboard bottom row and Holdings.
- **Size:** M. **Depends on:** S07, S08, S12.

### S14 · Screener and Watchlist layout

- **Why:** SC-03, SC-06–SC-17, WL-01–WL-03, WL-05–WL-07; G03, G28.
- **Files and functions:** `screener.py` and `watchlist.py` pages; `components.stock_row`; `formatting.py` (exchange short codes); `styles.py`.
- **Changes:** `page_header` with Reset filters always shown (outline, `refresh` icon). Signal chips 10.5px/500, share in mono; the "share of covered stocks" note stays visible (see the note below). "Hide positions I own" chip at the end of the filter row (dot + label; on: `--teal` border, `--soft` bg; filters out held tickers). Rank column "#" (32px, right, 12px mono `--muted`) after the star, numbered in the current sort. First column "Company". Exchange short code (PAR, XET, SWX, MIL, AMS, BRU) 9px mono `--muted`, gap 8px. Filter gap 22px. Show more as an outline button (padding 8px 14px, 0.5px `--line`, 12.5px `--muted`) centred in 14px 20px. Slider values `--up-txt`; filter labels `--muted`. Watchlist: `stock_row(show_action=False, show_remove=True)` with "×" in a trailing 32px column (`--muted`, hover `--down-txt`); duplicate message "Already on your watchlist." (G28); page width per G03.
- **Note on the chips:** Brand §8 keeps the note "share of covered stocks"; the mockup has no visible note. Version 1 suggested moving it into a tooltip; with the brand text in place, keep the visible note as it is (no decision needed).
- **Strings:** add "Company" (check existing), "Hide positions I own", "Already on your watchlist.".
- **Data and settings impact:** none.
- **Risks and open questions:** exchange codes replace translated city names (the glossary already keeps exchange names untranslated).
- **Tests:** `tests/test_pages_screener.py`, `tests/test_pages_watchlist.py`.
- **How to verify:** mockup Screener and Watchlist; 920px filter bar wraps by control.
- **Size:** M. **Depends on:** S05, S08, S09.

### S15 · Portfolio: overview, open and closed pages

- **Why:** PF-02–PF-04, PF-07–PF-10, PF-14, PF-15; G26.
- **Files and functions:** `uvalu/pages_/portfolio.py` (overview, open and closed sections); `uvalu/components.py` (`portfolio_open_row` weight bar and YoC colour, `portfolio_dividend_row` compact variant); `uvalu/dialogs.py` (`add_closed_trade_dialog`, `edit_closed_trade_dialog` titles); export label per G26.
- **Changes:** `page_header` on all three pages. Overview: the Open positions card lists every open position (remove the top-5 cut and "Show all"); the Dividends received card gets the header "Position · paid" / "Net / gross" and rows with name + type chip, "{TICKER} · paid {date}" (10.5px mono `--muted`), net 13px mono/500 `--up-txt` and "{gross} gross" (10.5px `--muted`); Dividends (12m) tile sub "net · {gross} gross"; export button "Export CSV". Open full page: no subtitle. Closed full page: no subtitle; title row and card max-width 760px; name column `1fr`. Weight bar `--teal`; YoC ≥ 4% and dividend amounts `--up-txt`. Dialog titles "Add closed trade" / "Edit closed trade" (the Closed page button stays "Add trade").
- **Strings:** add "Position · paid", "Net / gross", "{ticker} · paid {date}", "net · {amount} gross", "Export CSV", "Add closed trade", "Edit closed trade"; remove "Show all {count} position(s)", "Every holding at cost and at today's price. Click a row for its detail; the pencil edits or sells it.", "Realised results of sold positions. To sell a holding, use Sell shares in its Edit dialog on Open positions.", "income received", "Net dividend".
- **Data and settings impact:** none.
- **Risks and open questions:** a long portfolio makes the overview card long; the mockup accepts that.
- **Tests:** `tests/test_pages_portfolio.py` (overview row count, closed-page width, dividend preview columns); `tests/test_dialogs.py` (titles).
- **How to verify:** mockup `startPage=portfolio` overview, open and closed at 1280px in both themes; measure the closed card (760px). 920px: overview table headers stay aligned.
- **Size:** M. **Depends on:** S05, S06.

### S16 · Portfolio: dividends and cash pages

- **Why:** PF-05, PF-06, PF-11–PF-13, PF-15; G26.
- **Files and functions:** `uvalu/pages_/portfolio.py` (dividends section, `_tax_estimate_box`); `uvalu/pages_/cash.py` (`render_page`); `uvalu/components.py` (`dividend_log_row`, `MINT_CHIP_STYLE`, `_CASH_TYPE_STYLE`, `_cash_ledger_row_html`).
- **Changes:** Annual dividend income summary card full width; the tax-estimate box under it, full width (padding 14px 16px, radius 8px, `--panel`, title 13px/500). Export labels "Export log", "Export summary" and "Export CSV" (cash) per G26. Dividend log chips: Special `--amber-bg` / `--amber-txt`; Auto `--soft` / `--up-txt`; unconfirmed pay date `--amber-txt`; nets `--up-txt`. Cash page: `page_header`, "← Back to Portfolio" (S06), "Viewer · read-only" chip (11px mono, outline, radius 6px) before the buttons for Viewers; Income tile `--up-txt`; Dividend and Interest chips `--soft` / `--up-txt`; remove the footnote caption under the ledger.
- **Strings:** add "Export log", "Export summary", "Viewer · read-only"; remove the cash footnote ("Entries can be made in any currency … never goes below zero.").
- **Data and settings impact:** none.
- **Risks and open questions:** the removed footnote explains automatic top-ups; confirm the Add cash transaction dialog subtitle covers it.
- **Tests:** `tests/test_pages_portfolio.py`, `tests/test_pages_cash.py` (Viewer chip, no footnote, chip colours).
- **How to verify:** mockup `startPage=dividends` and `startPage=cash` (Tweak `cashRole` Viewer) in both themes; 920px: the 13 dividend-log columns stay inside the card.
- **Size:** M. **Depends on:** S05, S15.

### S17 · Risk layout

- **Why:** RK-01, RK-02, RK-04–RK-07; G12, G21, G22.
- **Files and functions:** `risk.py` page.
- **Changes:** page header; cash note first; no meter in the gauge card; tier colours `--up-txt` / `--amber-txt` / `#A32D2D`; concentration bars `--teal` / `--amber-fill`; flags `--amber-txt` / `--muted`.
- **Strings:** none. **Data and settings impact:** none.
- **Tests:** `tests/test_pages_risk.py`.
- **How to verify:** mockup `startPage=risk`.
- **Size:** S. **Depends on:** S04, S05.

### S18 · Analysis layout

- **Why:** AN-03–AN-06, AN-08, AN-11, AN-16, AN-18, AN-19; G07, G09, G17.
- **Files and functions:** `uvalu/pages_/analysis.py` (`render`, `_render_model_summary`, `_render_history_and_sensitivity`, `_render_sources_and_producer` layout); `uvalu/components.founder_notice_html`.
- **Changes:** back link inside the header block (margin-bottom 10px); page width per G03. Founder notice: the existing sentence (12px `--muted`) followed by "Conflicts of interest policy →" in `--link`. Fair value tile `--up-txt`; Your position "{n} shares · {value}" 13px/500 sans. Model summary moved to the end, 13.5px `--muted` line-height 1.65, ending with "Generated from the model outputs above; the same text is shown to every user. It is not a recommendation to buy, hold or sell." Row proportions 1 : 1.25 (sub-scores : models) and 1.25 : 1 (financials : checks); history/sensitivity and sources/producer stay 1 : 1. Sensitivity: four stats (Discount rate, Terminal growth, MoS setting, Score setting), rows as a grid (label 1.4fr · fair value 80px · margin of safety 70px), no badge column (G17), note "Fair values are model estimates, not forecasts or price targets. With 2% growth, raising the discount rate from 8% to 9% lowers a dividend-model fair value by about 14%." Badge history footer "Full log with inputs and model version is kept for every badge change."; no "daily" note (G07). Chart 200px. Dividend panel YoC, "automatic" and Auto chip `--up-txt`; no DRIP box (G09). Data-source labels `--muted`.
- **Strings:** add the closing sentence, "Terminal growth", "MoS setting", "Score setting", the sensitivity note, "Full log with inputs and model version is kept for every badge change.", "{count} shares · {value}"; reuse "Conflicts of interest policy →"; remove "Min. margin of safety", "Score threshold", "Every badge change is logged with its inputs and model version." (keep the existing "shared model settings" sentence as a second sentence of the note unless you want it gone).
- **Data and settings impact:** terminal growth from the DDM constant in `screener.py`.
- **Risks and open questions:** the closing sentence is legal wording; include it in the S28 review.
- **Tests:** `tests/test_pages_analysis.py` (card order, four stats, no badge column); new `tests/test_compliance_algorithms.py::test_model_summary_carries_the_no_recommendation_sentence`, `test_founder_notice_links_the_policy`.
- **How to verify:** mockup `startPage=analysis` (TTE.PA), Tweak `founderHolds`, both themes; measure the two-card rows; 920px.
- **Size:** M. **Depends on:** S05, S08.

### S19 · Stock drawer

- **Why:** DR-02, DR-05, DR-06; G23, G24.
- **Files and functions:** `drawer.open_drawer`.
- **Changes:** three tiles; fair value and score `--up-txt`; "View full analysis" full width, divider, records label, outline record buttons; founder notice with the policy link.
- **Strings:** remove "Implied return (est.)" if unused.
- **Tests:** `tests/test_drawer.py`.
- **How to verify:** mockup drawer from a Holdings row.
- **Size:** S. **Depends on:** S08.

### S20 · Settings: Account security and account footer

- **Why:** ST-03–ST-05, ST-12; reference Authentication (Google not in the beta, sessions without location); G27. Two-factor and passkeys are deferred.
- **Files and functions:** `settings.py` page (`set_card_profile`, `set_card_security`, `set_card_sessions`, `_device_label`, `_row_title` usage); `auth.list_sessions` (sign-in method per session, if stored); `styles.py`.
- **Changes:** one "Account security" card (`set-account`). Linked account row: "Linked account · Google", "Sign-in with Google is not available in the beta.", right "Not in the beta" (no Connect while Google is off). Two-factor row keeps its current description and behaviour (deferred). Backup codes and Trusted devices indented 34px on `--panel-2`, texts per ST-12. Passkeys row unchanged (deferred). Active sessions inside the card: device title, meta "Signed in {time} · {method}" / "Last seen {age} · {method}" (no location), "This session", "Sign out everywhere else" as a 12px link top right. Account footer after the last card per G27.
- **Strings:** add "Linked account · {provider}", "Sign-in with Google is not available in the beta.", "Not in the beta", "{used} of {total} unused. Regenerating replaces the old set.", "{count} device(s) skip(s) the code until {date}.", "Signed in {time} · {method}", "Last seen {age} · {method}", "password", "password + 2FA", "This session"; remove "Linked accounts", "Other ways to sign in to this account.", "Sign-in with Google or Microsoft is not available in the beta.", "Available for this workspace.", "{count} unused code(s) remaining.", "{count} device(s) skip(s) the two-factor challenge.", "{device} · signed in {date}", "Current", "This browser", "Security".
- **Data and settings impact:** check whether sessions store the sign-in method and trusted-device expiry; without them, show the date and leave out the method.
- **Risks and open questions:** none.
- **Tests:** `tests/test_pages_settings.py` (sessions inside the card, Google row, footer text); `TestLinkedAccounts` updated.
- **How to verify:** mockup Settings › Account security in both themes.
- **Size:** M. **Depends on:** S05, S07.

### S21 · Settings: Language & region card

- **Why:** ST-14.
- **Files and functions:** `uvalu/locale_ui.py` (`render_card`, `_row`, `_preview`, `_reset`); `uvalu/i18n.py` (number parse helper).
- **Changes:** row descriptions; header right "✓ Saved to your profile" (11.5px `--up-txt`, about 2s after a change) instead of the toast; currency as a segmented control (EUR/USD/GBP/CHF) with an 11px `--muted` status "Follows region · {region}" / "Set manually" and a "Use region default" link (`--link`); date format as three radio cards (Short / Medium / ISO with examples), or the segmented control with the example under it if a radio can't be styled stably (say so in the PR); week-start status line; preview as a `--panel-2` band with a tag chip "{region} · {currency}", five values ("Share price · ASML", "Portfolio total" with "{n} positions", "Change" up and down, "Last updated", "Signal") and a "Try a number" field read in the region format; reset as a right-aligned footer bar with "Return all six settings to the detected defaults?".
- **Strings:** add "Interface text and signal labels. Legal pages stay in English during the beta.", "Numbers, dates and amounts.", "Portfolio totals only, marked ≈. Instruments keep their own currency.", "Tables, charts and exports.", "Timestamps and “last updated”.", "Date pickers and calendar views.", "Follows region · {region}", "From region · {region}", "Set manually", "Use region default", "✓ Saved to your profile", "Share price · {ticker}", "Portfolio total", "Last updated", "Try a number", "Saved as {value}", "Can’t read this number in {region} format.", "Return all six settings to the detected defaults?", "Reset"; remove "Applies to portfolio totals. Individual prices stay in the currency they trade in.", "Total value", "Settings saved", "Reset all language and region settings to their defaults?".
- **Data and settings impact:** none.
- **Risks and open questions:** the number field uses Babel `parse_decimal`, display only.
- **Tests:** `tests/test_i18n_ui.py` (descriptions, status lines, parsing for de-DE, fr-CH, en-GB).
- **How to verify:** mockup Settings › Language & region in both themes while switching region and currency; 920px.
- **Size:** M. **Depends on:** S05.

### S22 · Settings: Display, Target allocation, Import & export, Model settings, Legal

- **Why:** ST-06–ST-09, ST-11, ST-13, ST-15; G14–G16, G18, G19.
- **Files and functions:** `uvalu/pages_/settings.py` (`render` cards, `_threshold_slider`, `_slider_label`); `uvalu/shell.py` (density hook); `uvalu/styles.py` (`[data-density="compact"]`).
- **Changes:** subtitle per G19. Display: Table density row (Compact / Comfortable) writing `density`; extend the compact rule to `scr_row_`, `wl_row_`, `pf_open_row_` (G15). Target allocation: three label-left / control-right rows (textareas max 280px, HHI input 110px, placeholder "0.15"), save right-aligned, no description row. Import & export: two stacked rows with the control on the right; the uploader as a compact, button-sized dropzone (closest stable option; the dropzone is a framework widget) and "Download backup.xlsx"; texts per G16. Model settings: header "Model settings in force" + "Same for every user · model {version}" (11px `--muted`); six read-only rows in two columns (Undervalued: composite score ≥ {n}; Undervalued: margin of safety ≥ {n}%; Cost of equity 3% + β × 5%; Terminal dividend growth {n}%; Quality screen: debt / equity > {n}%; Score weighting {style}) with hints; note "Thresholds and weights are set centrally by Uvalu, so every user sees the same signals. Changes are logged and announced in the app. Methodology →"; for admins the existing sliders below (G14); Benchmark and US toggles last. Legal per G18. Slider values `--up-txt`, hints `--muted`.
- **Strings:** add "Table density", "Row height for holdings and screener.", "Compact", "Comfortable", "Model settings in force", "Same for every user · model {version}", the six labels and hints ("Undervalued: composite score", "And fair value from at least two independent models.", "Undervalued: margin of safety", "Discount of price to model fair value.", "Cost of equity", "Risk-free rate plus beta times equity risk premium.", "Terminal dividend growth", "Multi-stage dividend model, after year 5.", "Quality screen: debt / equity", "Not applied to financials, real estate and utilities.", "Score weighting", "Margin of safety {a} · Risk {b} · Quality {c} · Momentum {d} · Dividend {e}."), the note, "Legal documents", "During the beta these documents are available in English only.", the new subtitle; remove "Model settings & quality screens", "Affects all users · logged", the shared-settings description, "Admin-only — sign in as an Admin to change these.", "Reference weights you set yourself. …", the old subtitle.
- **Data and settings impact:** `density` gets its control back.
- **Risks and open questions:** "Changes are … announced in the app": confirm threshold changes are announced (`record_planned_change`, What's new), otherwise drop "and announced". The cost-of-equity text must match `screener.py` and methodology.md.
- **Tests:** `tests/test_pages_settings.py` (read-only list for non-admins, sliders for admins, density persists, legal card).
- **How to verify:** mockup Settings cards as Admin and as Analyst, both themes; 920px.
- **Size:** M. **Depends on:** S20.

### S23 · Methodology page

- **Why:** ME-02–ME-05; G07, G08, G32.
- **Files and functions:** `uvalu/pages_/help.py` (`_rail`, `_render_cards`, `_signal_legend`); `uvalu/components.support_page` (optional header links).
- **Changes:** links row ("Full methodology →", "Data sources →", "Conflicts of interest →") in the header under the subtitle, 12px `--link`, gap 16px. Card order Badges, Reading the badges, Models, Quality screens, FAQ, Data sources, Conflicts, About; rail adds "About Uvalu". Badges card "Badges · meaning and thresholds" with live numbers (G32); keep the No signal row. Reading the badges: four columns incl. "Coverage today" from `screener.signal_distribution` ("{a} Undervalued · {b} Neutral · {c} Low score · {d} Fails quality screen"), labels 10px uppercase `--muted`, three notes incl. "Sensitivity." (moved from the Badges card). Data-source labels 120px `--muted`. Titles per G07 and G08.
- **Strings:** add "Badges · meaning and thresholds", "Coverage today", the coverage line, "Sensitivity."; remove "Badges · meaning".
- **Data and settings impact:** none.
- **Risks and open questions:** the coverage line fulfils methodology.md's "shown live on this page in the app".
- **Tests:** `tests/test_pages_help.py` (order, rail, coverage line, numbers in definitions); `test_methodology_reports_the_live_thresholds` stays green.
- **How to verify:** mockup `startPage=methodology` in both themes; rail anchors.
- **Size:** M. **Depends on:** S04, S06.

### S24 · Legal and About pages

- **Why:** LG-01–LG-05, AB-01; G02.
- **Changes:** eyebrow row with the print button, title size per G02 (recommended 20px, unchanged), divider 24px 0 6px, padding 30px 44px 40px, body `--muted`, bullets `--link`, English-only note in the rail (11px `--muted`), hover borders `--teal`.
- **Strings:** add "Uvalu · Legal", "During the free beta these pages are available in English only.".
- **Tests:** `tests/test_pages_legal.py`.
- **How to verify:** mockup `startPage=legal`, `about`; print preview.
- **Size:** S. **Depends on:** S04.

### S25 · Sign-in screens: password only in the beta

- **Why:** reference Authentication ("password sign-in only in the beta", "full footer disclaimer, producer and legal links on the sign-in panel", "password reset via admin"); AU-01–AU-08; G06, G07, G29.
- **Files and functions:** `uvalu/authgate.py` (`_render_hero`/hero block, `_render_provider_buttons` and its three callers, lock-out frame, forgot-password frame, sign-in form); `uvalu/oauth.py` (a beta switch, e.g. `providers_enabled()` returning False while `disclosures.BETA`); `styles.py` (`.uv-login-*`).
- **Changes:** no provider buttons and no "or" divider on sign-in, lock-out and invite screens while providers are off (keep the provider-identity screens in code for later). Hero: headline "Find value before the market does." (decided, G06), the descriptive paragraph under it, stats per G07; footer 11px at 60% white with disclaimer, producer line + "Not authorised…", and the six legal links in `#3FBF98` (fixed navy surface) opening `/legal?doc=…`. Lock-out note "The lock applies to password sign-in only." Forgot password: AU-04 text and an outline "Back to sign in". "New to Uvalu?" per G29. Links `--link`; field icons Material `mail` / `lock` in `--muted`. Form title 24px (S04).
- **Strings:** add "During the beta Uvalu doesn’t send emails. Ask your admin to reset your password. They give you a single-use link, valid for 30 minutes.", "Ask for an invite" (G29), "Find value before the market does."; remove "Calculate fair value with five models.", "Uvalu has no automated password reset — ask an admin to send you a one-time reset link from the Admin portal.", "The lock applies to password sign-in only. Providers are unaffected.", "Ask your admin for an invite", "Continue with {provider}" and "NOT CONFIGURED" only if no other screen uses them (they stay for Settings/Admin later: keep).
- **Data and settings impact:** none; OAuth secrets may stay configured but are not offered.
- **Risks and open questions:** a tester who linked Google earlier can no longer sign in with it; confirm every beta account has a password (`auth.has_password`), or give those accounts a reset link before release.
- **Tests:** `tests/test_authgate.py` (no provider buttons while beta, footer links present, texts); `tests/test_oauth.py` (beta switch); `tests/test_legal_guards.py` (footer texts on the sign-in panel).
- **How to verify:** sign out; compare with the main mockup sign-in and Auth frames 01–04, 06 in dark and light.
- **Size:** M. **Depends on:** S02, S04.

### S26 · Admin: security policy, invitation only, providers, order

- **Why:** reference Authentication ("accounts by invitation only (no auto-provision)", Google "Not in the beta" in Admin); AD-01, AD-03–AD-07; G25. The MFA requirement (AD-02) is deferred.
- **Files and functions:** `admin._render_security` (auto-provision toggle, allowed domains, providers list), `_NAV_ITEMS`, `_SECTION_TITLES`, sidebar logo; root `settings.py` (`auto_provision_oauth` default); `auth.oauth_login` (auto-provision branch).
- **Changes:** replace the auto-provision toggle with a fixed row "Account creation — Invitation only. Accounts are never created automatically, because every member must accept the terms and acknowledgements and give an EEA country first." with "Invite only · fixed"; remove the auto-provision branch from `auth.oauth_login` (always refuse an unknown identity) and the `auto_provision_oauth` default. Allowed email domains stay (provider filter for later). The two-factor requirement control stays as it is (deferred). Providers list: Google "NOT CONFIGURED · Not in the beta". Section order per G25; title "System"; logo "u" `--link`; readable text `--muted` (S03).
- **Strings:** none (Admin is English-only).
- **Data and settings impact:** stored `auto_provision_oauth` becomes unused; no migration.
- **Risks and open questions:** none.
- **Tests:** `tests/test_pages_admin.py` (nav order, fixed invite row); `tests/test_auth.py` (unknown provider identity never creates an account even with an allowed domain).
- **How to verify:** `Uvalu Admin.dc.html` and Auth frames 16–17 in dark.
- **Size:** M. **Depends on:** S03.

### S27 · Beta privacy notice

- **Why:** reference Authentication ("the beta privacy notice in `legal-docs.js` no longer describes Google sign-in (apply the same to `docs/legal/policies/beta/privacy-notice.md`)"); G36.
- **Files and functions:** `docs/legal/policies/beta/privacy-notice.md`; `docs/design/legal-docs.js` stays as delivered.
- **Changes:** apply the `legal-docs.js` text (verified diff: drop the Google row in §2, "or use Google sign-in" in §3, the Google controller paragraph, the "If you use Google sign-in…" transfer sentence, the `_streamlit_user` cookie row and the drafting-note mention). Leave the passkey sentences as they are (passkeys deferred). Per G36 add the hash-prefix breach check sentence. Bump the version/date line per the policy README.
- **Strings:** none (legal pages are English-only in the beta).
- **Data and settings impact:** none.
- **Risks and open questions:** legal text; review against the compliance plan (GDPR-1) before merge.
- **Tests:** `tests/test_legal_guards.py::test_beta_texts_say_what_is_true_in_the_beta` (extend: no "Google" in the beta privacy notice while providers are off); `test_every_policy_file_has_a_title_and_version_line`.
- **How to verify:** Legal › Privacy notice in the app against the mockup's Legal page.
- **Size:** S. **Depends on:** S25.

### S28 · Disclosure wording

- **Why:** G05, G35 (legal texts, one review).
- **Files and functions:** `disclosures.py`; `shell.producer_line`; `analysis._render_sources_and_producer`; `help.py` conflicts and About cards.
- **Changes (only what you accept):** producer line "{name}, trading as {trading_as} · {address} · {number} · {contact}" (also on the sign-in footer from S25); producer card lines; Methodology conflicts lines; About card with "Sven Claes, trading as Uvalu", producer line under it, support-refusal line kept.
- **Strings:** add "{name}, trading as {trading_as}", "Produced automatically by {producer} ({number}).", "No payment from the issuer, brokers or data providers. Uvalu has no income during the free beta.", "The founder does not hold {ticker}. A holding of any size would be shown here.", the three conflicts lines; remove the replaced texts.
- **Risks and open questions:** legal review incl. translations (INT-1, INT-4).
- **Tests:** `tests/test_compliance_algorithms.py::test_producer_line_has_name_address_number_contact`; `test_disclosure_texts_are_clean`; `tests/test_legal_guards.py` footer test.
- **How to verify:** footer, sign-in footer, Analysis producer card, Methodology.
- **Size:** S. **Depends on:** S18, S23, S25.

### S29 · Release notes and docs

- **Why:** release process; compliance-plan row (Settings "Market data · EOD" → removed, provenance carries the delay); the beta-bar decision (G01) recorded back in the design reference.
- **Files:** `CHANGELOG.md` (section 6); `docs/design/README.md`; `docs/legal/compliance-implementation-plan.md` line 280; `docs/design/Design reference.md` (beta bar: rounded box per Brand §8, G01; also to be changed in the design project and its mockup); `docs/uvalu-brand-guidelines.md` §6 icon size if G04 goes against the brand; `docs/architecture.md`; `docs/configuration.md` (`auto_provision_oauth`).
- **Tests:** `tests/test_release_tooling.py`, `tests/test_version_ui.py`.
- **How to verify:** About › What's new.
- **Size:** S. **Depends on:** all.

## 5. Not in this plan

- Phone and tablet layouts.
- Settings › Privacy (Export my data, Delete account, Privacy contact).
- Acceptance records, the Settings › Legal acknowledgement row, the invitation form with EEA country and three stored boxes, and the re-acceptance screen (E1, E2; see G30).
- Settings › Plan card.
- Two-factor for admins: enforcement at sign-in, the policy options (no "Off" for admins), the grace period and the Settings text "Mandatory for admin roles." (decided 9 October). Note: the reference's Authentication section lists it as decided; `Design reference.md` should mark it as deferred.
- Passkeys: sign-in, the Settings row in the mockup ("2 registered … Manage") and the passkey sentences in the beta privacy notice, which still say passkeys are available (decided 9 October).
- Outlined wordmark SVG (Brand v1.3 follow-up; artwork, not code).
- Recheck with real translations: price status cut off in the top bar.
- Recheck with real translations: buttons wrapping onto two lines.
- Recheck with real translations: Watchlist column headings running off the table.
- Recheck with real translations: Dashboard and Portfolio tiles with two-line labels.
- Recheck with real translations: Holdings legend breaking into narrow columns.
- Recheck with real translations: two-line Holdings and Screener column headings.
- Recheck with real translations: Screener slider labels pushing the value.

## 6. Release notes draft

```markdown
## [2026.10.N] — 2026-10-DD

The app now follows the updated design and brand guidelines: clearer links
and secondary text in both themes, the same page layout on every screen,
calmer signal colours, and password-only sign-in for the beta. Scores and
signals are unchanged, but the Screener now also lists stocks without a
signal at its default filters. Nothing to do besides restarting with
`run_app.py`.

### Added

- **Screener**: a *No signal* filter, a *Hide positions I own* toggle and a
  rank column.
- **Dashboard**: *Add position* next to *Refresh*; upcoming dividends show
  the payment date where it is known; top movers open the stock.
- **Methodology**: *Coverage today* and the live thresholds next to each
  badge.
- **Settings**: *Table density* is back under Display; *Language & region*
  shows a preview with a number you can try.
- The sign-in screen shows the full disclaimer and links to the legal pages.
- A short notice while signals are being rebuilt after a restart.
- Keyboard focus is shown with a clear outline.

### Changed

- **Links** use a darker green in light theme and a lighter green in dark
  theme, and secondary text is easier to read.
- **Every page title** is the same size; every back link reads *← Back to …*.
- **Methodology & help** is now **Methodology**; in Settings, *Account* is now
  *Account security* and *Portfolio* is now *Target allocation*.
- **Margin of safety**: a negative margin and a price above the model fair
  value are amber; red is kept for a failed quality screen. The fair-value
  bars use green, grey and amber.
- **Score bands** follow the signal thresholds: upper band 70–100, middle
  40–69, lower 0–39.
- **Holdings**: the last column shows your result against your average cost
  as a percentage.
- **Sign-in**: password sign-in only during the beta. Ask your admin to reset
  a forgotten password.
- **Accounts** are created by invitation only.
- **Settings › Account security** is one card with your sessions; Google
  sign-in shows as *Not in the beta*.
- **Privacy notice (beta)** no longer describes Google sign-in.

### Removed

- **Settings › Data & alerts**: the price refresh interval (prices refresh
  every minute during market hours) and the ex-dividend, dividend cut and
  dividend increase badges on the Dashboard.
```

## 7. Suggestions (outside the reference)

- The Dashboard's empty-dividends caption says "in the next 30 days" but the list has no 30-day limit.
- Don't copy the mockup's Watchlist margin formula (against the price) or the Add position dialog's "blocked" cash state.
- `Design reference.md` describes the beta bar as a strip and lists MFA for admins as decided; both now differ from your decisions. Update the reference and the mockup in the design project so the next pass doesn't reintroduce them. Brand §6 icon size (G04) needs the same once decided.
- White text on Signal Teal buttons is 4.2:1 (Brand §4 notes teal is below 4.5:1 for small text). If you want buttons to meet 4.5:1, a darker button fill would need a brand decision.
- Code comments still say "upside" in a few places.
- After S04 and S05, delete the per-screen CSS overrides the shared values replace.
