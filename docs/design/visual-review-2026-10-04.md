# Visual review: all screens (4 Oct 2026)

Branch `feature/legal-compliance-algorithms`, working tree as of 4 Oct 2026 (M1 compliant algorithms
wired in, legal footer, legal page, beta banner). Nothing is implemented yet. This is a plan to review.

**How it was checked.** The app ran through `_dev_entry.py` in the in-app browser. Every screen was checked
at **1024 px** (laptop) in dark theme, the Dashboard also at **1440 px**, in **light theme** and at
**375 px** (phone). Spacing was measured in the DOM, not judged from screenshots alone. Screenshots
are in [`visual-review-2026-10-04/`](visual-review-2026-10-04/) and referenced as `[NN]` below.

**Priority key.** P0 = something is visibly wrong or broken · P1 = the changes you asked for ·
P2 = polish and consistency · P3 = larger structural work.
**Effort.** S = under 1 h · M = half a day · L = a day or more.

---

## Contents

1. [Your four requests](#1-your-four-requests)
   - 1.1 Legal footer
   - 1.2 Signal provenance line ("Signals computed …")
   - 1.3 Legal page
   - 1.4 Settings page
2. [Issues across all screens (design system)](#2-issues-across-all-screens-design-system)
3. [Findings per screen](#3-findings-per-screen)
4. [Suggested implementation order](#4-suggested-implementation-order)
5. [Questions to decide before implementing](#5-questions-to-decide-before-implementing)

---

## 1. Your four requests

### 1.1 Legal footer — P1, S

**Now** (`uvalu/shell.py:429` `render_footer`, CSS at `shell.py:414`) [03]:

- The disclaimer paragraph is capped at `max-width: 980px`. At 1440 px it stops about two-thirds of the
  way across, while the producer line below it runs the full width, so the two lines look unrelated.
- The six links are left-aligned. Each has the same `gavel` icon, so the row reads as six identical
  icons with text.
- "Not directed at residents of the United Kingdom, the United States or Switzerland." sits on its
  own line, as part of the links row.
- On short pages (empty Analysis, Watchlist while loading) the footer floats in the middle of the
  screen [13] instead of sitting at the bottom.

**Proposal:**

```
──────────────────────────────────────────────────────────────────────────────── 0.5px line, full width
Uvalu is an analysis tool. Scores, fair values and signals are model outputs based on public data and
are the same for every user. They are not personal investment advice … Decisions are your own.
                                                        ↑ full width, 11.5px muted, left-aligned
Uvalu · Sven Claes, Pol Heynsstraat 7, 2200 Herentals, Belgium · enterprise number: registration
pending · support@uvalu.app · Not authorised or supervised by the FSMA as an investment firm.
                                                        ↑ full width, 11px faint, left-aligned

      Terms of use · Privacy notice · Methodology · Data sources · Conflicts of interest · Complaints
                                                        ↑ centred, 11px teal, "·" separators, no icons
```

Changes:

1. Remove `max-width:980px` from the disclaimer `<div>` (`shell.py:436`) so both text lines use the full
   content width. Add `text-wrap: pretty` so the last line doesn't end on one short word.
2. Centre the link row: in `_FOOTER_CSS` add `justify-content: center` to `.st-key-uv_footer_links`. Also
   centre the Streamlit wrapper of each link: `.st-key-uv_footer_links > div { flex: 0 0 auto; }`. Without
   that, Streamlit's flex children stretch and the row stays left-aligned.
3. Remove the `gavel` icons from the footer links. Use a faint `·` separator instead (CSS `::after` on
   each link except the last). The gavel comes from the page's own icon (`app.py:108`,
   `icon=":material/gavel:"`), which `st.page_link` inherits. Hide it inside the footer
   (`.st-key-uv_footer_links [data-testid="stIconMaterial"] { display:none }`), or render the links as
   plain `<a href="/legal?doc=…" target="_self">` in one markdown block, which also makes centring trivial.
4. Shorten the last link label in the footer only, to "Complaints". The page itself keeps the full title
   "Complaints & Consumer Mediation Service".
5. **Remove the NOT_DIRECTED line** (`shell.py:446-447`). Legal note, so this stays compliant:
   - INT-5 and INT-6 (in *Legal Requirements for Launch*) ask for the statement **in the terms**. They
     don't require it in the footer, so removing it from the footer is fine.
   - But the Terms (`docs/legal/policies/beta/terms-of-use.md:49` and the launch version, line 42) only
     say *"live in a country of the European Economic Area (EEA)"*. That excludes the UK, US and CH
     implicitly but doesn't name them. **In the same change, add an explicit sentence to both Terms
     files**, e.g. under eligibility: *"Uvalu is not directed at residents of the United Kingdom, the
     United States or Switzerland."*
   - Update `tests/test_legal_guards.py:139`. It asserts the sentence is in the footer: move that
     assertion to a test on the Terms file.
   - Keep the `NOT_DIRECTED` constant in `disclosures.py` if the sign-up/invite flow will show it later.
     Otherwise delete it, and run the usual `pybabel extract/update/compile` so the msgid leaves the
     catalogues. Watch for the fuzzy-match gotcha from the M1 work.
6. Keep the footer at the bottom on short pages: give the main block container
   `min-height: calc(100vh - <header>)` with `display:flex; flex-direction:column`, and the footer
   `margin-top:auto`.
7. Optional: end the link row with a faint `v2.0.1 · beta` version marker. It helps with support
   questions ("which version were you on?").

### 1.2 Signal provenance line — P1, M

**Now** (`uvalu/components.py:132-183`, `_provenance_div` / `list_provenance_html` /
`signal_provenance_html`). It appears on the Dashboard holdings [02], Screener [04], Watchlist [06],
the drawer [14] and the Analysis header [16].

What's wrong with it visually:

- It is one long **monospace** run-on line, 11px faint, that wraps unpredictably (Screener: 2 lines;
  drawer: "delayed" wraps on its own). Monospace is meant for numbers, but here it is used for prose.
- Timestamps use the short numeric format (`4/10/2026 14:15`). The *"fetched 12/09/2026 09:50 to
  4/10/2026 14:15"* range is hard to read, and it hides the real message: **some prices are 3 weeks old**.
- The coverage list *"3% Undervalued · 44% Neutral · 9% Low score · 44% Fails quality screen"* is a
  distribution shown as a text string.
- Spacing differs per screen. Watchlist: 0 px between the line and the table [06]. Analysis: 0 px
  between the line and the KPI cards [16]. Screener: it sits between the subtitle and "Reset filters" [04].

**Constraints to keep** (from your requirements): REC-4 / DATA-3 (when computed, price time, labelled
delayed), REC-5 (Methodology link next to every signal), REC-10 (share per signal category). These have
to stay **visible next to the signals**, so the fix is to make them compact. A tooltip alone isn't enough.

**Proposal: one shared "provenance bar" component, used on every screen with signals.**

```
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ ⓘ Model M1   ·   Signals 4 Oct 2026, 14:15   ·   Prices delayed, 12 Sep – 4 Oct  ⚠ 3 weeks   Methodology → │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
Coverage  ▕██▏▕███████████████▏▕███▏▕███████████████▏
          3% Undervalued   44% Neutral   9% Low score   44% Fails quality screen     (Screener only)
```

Details:

1. **Layout.** One row, `display:flex; justify-content:space-between; align-items:center`. Facts on the
   left, "Methodology →" pushed to the right. Separators are faint `·` with 10px gaps. Optionally add a
   very subtle container (`background: var(--soft); border: 0.5px solid var(--line); border-radius: 8px;
   padding: 6px 12px`), the same treatment as the beta banner, so it reads as one information strip.
2. **Typography.** Labels in the sans stack, 11.5px muted. Only the values (`M1`, dates) in mono, 11px.
   This follows the brand rule "numbers are monospace, prose is not".
3. **Dates.** Use the user's *Medium* date format (`4 Oct 2026, 14:15`) from `uvalu.i18n`, not the short
   numeric one. Add a full timestamp with time zone as a `title=` tooltip.
4. **Price range.**
   - All prices from the same day: "Prices delayed, as of 14:15".
   - A range: "Prices delayed, 12 Sep – 4 Oct". Drop the times; the tooltip has them.
   - Oldest price more than N days old (e.g. 3 trading days): add an **amber staleness chip**
     "⚠ oldest 3 weeks". It links to, or explains, which tickers are stale. Today that information is
     buried in the middle of a sentence.
5. **Coverage (REC-10), Screener only.** Show it as a **100 % stacked bar** (6px high, 160–240px wide),
   using the signal colours, with the four percentages as a legend under it. Better still, also put the
   counts **inside the signal filter pills**: `Undervalued 104 · Neutral 1 515 · Low score 310 · Fails
   quality screen 1 513`. Then the coverage is part of the filter instead of a separate sentence. On the
   Dashboard and Watchlist, leave coverage out (as now).
6. **One position on every screen.**
   - List screens: directly **above the table**, inside the table card's header area, replacing the
     loose line between title and table. On the Dashboard, the legend row (Below/Near/Above model fair
     value) moves to the same strip, right-aligned, instead of wrapping under it.
   - Drawer and Analysis header: one line under the ticker/name, 8px above the KPI cards (now 0px).
7. **Responsive.** Under 768px the facts wrap per item, never inside an item: `white-space:nowrap` on
   each `<span>`. "Methodology →" goes on its own line.
8. **Implementation.** Replace `_provenance_div` with a `provenance_bar_html(parts, *, coverage=None,
   stale_days=None)` that returns the structured markup. `list_provenance_html` and
   `signal_provenance_html` keep their signatures, so the callers don't change. Unit tests in
   `tests/test_legal_guards.py` check the strings; keep the same msgids where you can, or update the
   tests and catalogues together.

Alternative if you want it even quieter: a single "ⓘ Data & model" chip with the date that opens a
popover with the full provenance. **Not recommended** for signals (see REC-4/5/10 above: it must be
visible with the signal). It would be fine for the Portfolio and Risk pages, which show no signals.

### 1.3 Legal page — P1, M

**Now** (`uvalu/pages_/legal.py`) [26]:

| # | Issue | Fix |
|---|---|---|
| L1 | "Complaints & Consume…" is **cut off** in the left nav. The nav column is `[1, 3.4]`, too narrow for the longest title. | Let the nav labels wrap (`white-space:normal` on the page-link `p`), or widen to `[1.3, 3.4]`. Better: build the nav as a custom list (see L3). |
| L2 | The active document is marked with a text prefix `"● "`. It shifts the label and looks like a bug. | Real active state: teal 2px left border, `var(--soft)` background, text in `var(--text)`. Inactive items in muted text without a pill border. |
| L3 | Every nav item has the same `gavel` icon in a pill. That is visually heavy and carries no information. | Either no icons, or one distinct Tabler outline icon per document: `file-text` (Terms), `shield-lock` (Privacy), `math-function` (Methodology), `database` (Data sources), `scale` (Conflicts), `message-report` (Complaints). |
| L4 | The nav **scrolls away**. The Terms page is about 4 000 px long, and after the first screen the left column is empty. | `position: sticky; top: <header height + 16px>` on the nav column. |
| L5 | No table of contents inside long documents. | Build an "On this page" list from the `##` headings (anchor links), under the document nav in the sticky column. Gives quick access to "4. What Uvalu is not". |
| L6 | The document header is a faint breadcrumb "UVALU · LEGAL · FREE BETA" plus a bold "Version: … Effective from: …" sentence. | A proper header block: H1 title, then a row of chips **`Beta 1.0`**, **Effective: opening of the free beta**, **Last updated 3 Oct 2026**, and on the right **Print / Save as PDF** (browser print with a print stylesheet that hides header, nav and footer). |
| L7 | The reference-language note ("Reference language: English. You may rely on …") sits under the nav at 15 px body size, the same weight as the content. | Move it into the document header as an 11.5px caption, and only show it when the UI language ≠ English (with the translation-fallback notice). |
| L8 | The translation-fallback notice uses Streamlit's default blue `st.info`, which is off-brand. | Use the app's notice style (the one on the Risk page: 0.5px border, ⓘ icon, muted text). |
| L9 | "← Back" always goes to the Dashboard, even when the user came from a badge's "Methodology →" link on the Screener. | Store the referring page before switching (`_legal_back_to`), and label it after the target ("← Back to screener"). Default to the Dashboard. |
| L10 | Reading measure: the body column at 1440 px gives ~95 characters per line. | Cap the document text at `max-width: 72ch` inside the card. Headings: H2 18px/500 with 32px top margin. Lists: 6px between items. |
| L11 | The footer below repeats the same six links. | On the legal page, mark the current document in the footer links (teal-to-text colour), or hide the footer link row on this page only. |
| L12 | Phone width: the two-column layout squeezes. | Under 768px, replace the nav column with a document `selectbox`, or horizontally scrolling chips above the document. |
| L13 | The legal page is only reachable from the footer and from badge links. | Add a "Legal & policies" item to the user menu (next to "Methodology & help"), and a "Legal" section at the bottom of Settings (Terms, Privacy, data export/erasure request contact). |
| L14 | Documents don't link to each other in-app (e.g. Methodology → Data sources). | Rewrite relative links like `data-sources.md` to `/legal?doc=data` when rendering (one `re.sub` in `render()`). |

### 1.4 Settings page — P1, M–L

**Now** (`uvalu/pages_/settings.py`) [20]–[25]. One long column, about 3 700 px, nine cards.

**Bugs to fix first (P0):**

| # | Issue | Screenshot |
|---|---|---|
| S1 | **Dividend withholding grid breaks out of its card.** The labels (Euronext Brussels …) start flush on the card edge (x = card border, not card padding), and the right-hand input sticks out past the card's right edge. | [24], [25] |
| S2 | **The preview badge still says `BUY`.** The M1 compliant swap renamed the signals ("Undervalued", "Neutral", …). The Language & region preview wasn't updated. This is a compliance-visible leftover. | [20], [21] |
| S3 | **"Maandag / Zondag"** for the first day of the week in an English UI. The region format (Belgium, Dutch) leaks into the *labels*. Labels should be in the UI language; only the formats follow the region. See also G8. | [20] |
| S4 | **The "Screening style" description is clipped** by the next row's divider ("…Income to dividends." is cut). | [22] |
| S5 | **The "Price refresh interval" description collides** with the next row ("Ex-dividend alerts"): 0 px gap. | [24] |
| S6 | **The Language row has no top padding** under the section header divider, and labels are top-aligned while the selects are vertically centred (Language, Region format, Time zone, Display currency). | [20] |

**Structure (P1):**

1. **Section navigation.** Two columns: a sticky left list of sections and the content on the right.
   Alternatively use `st.tabs`. Suggested grouping, in this order (things users change most often first):
   - **Account**: profile card (name, email, role; now at the very bottom [25]), password,
     two-factor, passkeys, linked accounts, active sessions, sign out.
   - **Language & region**
   - **Display**: theme, benchmark overlay.
   - **Portfolio**: target allocation, HHI ceiling, dividend withholding.
   - **Data & alerts**: refresh interval, ex-dividend / cut / increase alerts.
   - **Import & export**
   - **Model settings** (admin only), shown last and visually separated, see 5.
   - **Legal**: links to the six documents (L13).
2. **Same page gutter as other pages.** Settings content is indented ~18px more than the beta banner
   and every other page (title at x=37 vs x=19) [20]. Remove the extra inner padding, or apply it to
   every page the same way.
3. **One row component.** Label + description on the left, control on the right, **vertically
   centred**, `min-height: 56px`, 12px vertical padding, 0.5px divider. Description 12px muted, max
   2 lines. This fixes S4, S5 and S6 in one place.
4. **One save model.** The subtitle says "Changes apply immediately", but Target allocation has a
   "Save target allocation" button, and the withholding inputs have no visible save at all. Pick one:
   - autosave everywhere, with a small "Saved ✓" confirmation per row/section (toast), **or**
   - an explicit Save per card, shown as a sticky bar *"Unsaved changes · Discard · Save"* when
     something is dirty.

   I recommend autosave for toggles and selects and explicit Save for free-text (targets, withholding),
   because a half-typed value shouldn't apply.
5. **Model settings (shared, admin only).** These change signals for *every* user, and Methodology
   publishes them, so they deserve a distinct look:
   - an amber "Affects all users · logged" chip in the section header, and a link "View change log";
   - remove the **duplicate value** (header shows `500%` and the slider thumb label shows `500`):
     keep the header value, hide the thumb label;
   - help text is now 15px muted with a ~30px gap under the slider [22]: make it 12px, directly
     under the label (above the slider);
   - show min/max tick labels on the sliders (e.g. "10 % … 50 %"), so "never below 10 %" is visible.
6. **Clean up user-facing copy and roadmap leaks:**
   - remove the **"PHASE 3"** chip next to Passkeys [21]. If passkeys aren't available in the beta,
     show "Not available in the beta" and disable "Manage";
   - "Linked accounts · One row per configured provider" plus two rows "Not configured for this
     workspace · Unavailable" is developer copy. If no provider is configured, show one line:
     "Sign-in with Google or Microsoft is not available in the beta", or hide the block;
   - "Include US-listed names" is a disabled toggle without explanation [22]. Add "Not available:
     the beta covers European exchanges only", or hide it (it also fits the not-directed-at-US stance).
7. **Controls:**
   - Date format radio list and First-day-of-week radios → **segmented controls**, like Theme and
     Refresh interval, so the page uses one control style for small fixed choices.
   - Target allocation textareas: the placeholder text ("Technology 25 / Healthcare 15") looks like
     real values. Lower its contrast. Better: a small structured editor (sector select + % input
     rows, "+ Add", a running total "Total 40 % · 60 % unallocated").
   - "Concentration ceiling (HHI) 0 = use the default": a magic 0 is unclear. Use an empty field with
     placeholder "Default (0,10 / 0,18)", or a "Use default" toggle.
   - Withholding inputs: add a `%` suffix and validate 0–100. Optionally show the treaty default as
     placeholder.
   - "Reset to defaults" is a bare text button floating under the preview [21]. Make it a tertiary
     button aligned right in the card footer, with a confirm.
8. **Import & export:** "Upload … replaces all existing portfolio data" is destructive but looks like
   any other action. Put it in a "danger zone" style (red-outline button, confirmation dialog listing
   what will be replaced). Hide Streamlit's default "200MB per file • XLSX" and write "Excel (.xlsx)".
9. **Duplicate sign-out.** "Sign out" appears under Active sessions *and* on the profile card at the
   bottom. Keep one: the current-session row's "Sign out", and move the profile card to the top of
   the Account section.
10. **Card spacing.** Cards are 12px apart. The brand guide says 24px card-to-card (`xl`). Use 16–24px
    consistently, and the same section-header style (11px uppercase muted, 0.06em tracking) everywhere.

---

## 2. Issues across all screens (design system)

These show up on several screens. Fix them once in `uvalu/components.py` / `uvalu/shell.py` CSS and
every page benefits.

| # | Pri | Issue | Where seen | Proposal | Effort |
|---|---|---|---|---|---|
| G1 | **P0** | **First render shows wrong values instead of a loading state.** On first load the Dashboard showed *composite score 0 / 100 "Lower range of the model scale"*, risk *35*, and every holding *"No signal"*. Seconds later: 42 / 100, risk 36, real signals. Watchlist shows an empty bordered box [05]; Risk shows only the two notices [09]. | Dashboard, Watchlist, Risk | Keep the skeleton (already used on the Score & risk card) until the scored frame is ready. Never render a computed number from an empty frame. Check `_load_portfolio_scored` callers: a missing score must be `None` → skeleton/"—", never `0`. | M |
| G2 | **P0** | **"Fails quality screen" badge is invisible in dark theme.** The veto style is navy `#0D1F3C` on a navy card, so only the white text shows and the pill disappears [02]. In light theme it is a proper navy pill [29]. "No signal" looks disabled; "Undervalued" is a bright near-white pill that shouts in dark mode [04]. | All lists, drawer, Analysis | Define dark-theme badge tokens: tint background at ~16 % alpha + semantic text (e.g. Undervalued `rgba(29,214,164,.14)` / `#1DD6A4`). For the veto-style badge in dark: `#1E293B` background + 0.5px `rgba(245,247,250,.25)` border + white text. Same height, padding and radius (6px) for all. | S |
| G3 | P2 | **Bright white bar tracks.** The empty part of the fair-value ladders, score bars, sub-score bars and the drawer's model bars is pure white. That makes it the brightest element on the dark screen [02][04][17]. | Dashboard, Screener, Watchlist, Drawer, Analysis | Track = `var(--soft)` or `rgba(255,255,255,.08)`; only the fill carries colour. The fair-value marker stays a thin light tick. | S |
| G4 | P2 | **Inconsistent signed money format:** `+€ 126,60` vs `€ -86,01` (Dashboard), `€ −108` (Portfolio), `€ -4.873` in the page text vs `€ −4.873` rendered. | Dashboard, Portfolio, Drawer | One helper `fmt_signed_money()`: sign **before** the symbol, true minus `−`: `+€ 126,60` / `−€ 86,01`. Use it in every P&L / return cell. | S |
| G5 | P2 | **Raw data names.** ALL-CAPS names ("INVESTOR AB CLASS B", "MAUREL ET PROM"), share-class suffixes left on ("MBB SE I", "TUI AG N", "Cigna Group, The R", "CEOTRONICS AG I"). The same company is shown differently per widget ("MELEXIS" in Upcoming dividends vs "Melexis NV" in Holdings). | Screener, Watchlist, Dashboard | A `display_name()` cleaner: strip trailing ` I`, ` N`, ` R`, ` A`; fix "X, The" → "The X"; title-case names that are all caps (keep short acronyms like SE, NV, AG, SA, ABB). Use the same name source in every widget. | M |
| G6 | P2 | **Cards in one row have unequal heights** (Dashboard: Sector / Dividends / Movers [03]; Portfolio: Closed / Dividends [08]). **Column ratios change per row** on Analysis (45/55, 55/45, 100, 50/50), so the gutters zig-zag [17][18]. | Dashboard, Portfolio, Analysis | Stretch cards in a row to equal height (`align-items: stretch` on the horizontal block + `height:100%` on the bordered containers). Use one grid: 50/50 or 7/5 consistently per page. | S–M |
| G7 | P2 | **Captions and footnotes at body size, outside the card padding.** The Risk contribution footnote "Percent contribution to portfolio variance…" is 15px and starts at the card edge (x=19 vs card content x=35) [12]. The same happens with the factor-loading footnote [11], the Analysis "Weighted components…" and Assumptions footnote [17][18]. | Risk, Analysis | One `caption` style: 11.5–12px, `var(--faint)`, inside the card padding, 12px top margin. | S |
| G8 | **P0** | **Dutch words in an English UI.** "closed **mei** 2026" (Portfolio closed positions [08]), "**mei** 2025" (Analysis dividend history chart [18]), "Maandag / Zondag" (Settings [20]). The region format "Belgium (Dutch)" sets the *language* of month and day names. | Portfolio, Analysis, Settings | Format with UI language + region conventions (e.g. Babel locale `en_BE`: English month names, Belgian number/date order). Only the numeric order follows the region. | S–M |
| G9 | **P0** | **Truncation and numbers wrapping mid-value at 1024 px.** "€ 109,⏎20", "€ 228,4⏎2" in Portfolio [08]. Headers cut off: "AVG MARGIN OF SAF…", "MARGIN OF S…", "SHAR…", "INCOME 12…", "YOC N…", "NET DIV…". KPI sublabel "of total value · n…", Top movers names "Econocom G…", Admin role select "Ad" [27]. | Dashboard, Screener, Watchlist, Portfolio, Admin | `white-space: nowrap` on all numeric cells (must-have). Shorter header labels at < 1200 px (Margin of safety → "MoS", Income 12m → "Inc. 12m"), with the full name in a tooltip. Give the KPI sublabels a second line instead of ellipsis. This is related to the parked "1024px tables" backlog item. | M |
| G10 | P2 | **Red used for non-veto states.** The brand reserves red for avoid/veto. It is also used for Sharpe "Suboptimal", the "Largest sector" bar, "Above reference" observations, and the risk-contribution bars of quality-failing names [10][11][12]. | Risk | Caution states → amber (`#C98A3A` / tint). Red only for real breaches you define as such. | S |
| G11 | P2 | **Repeated disclaimers on the same screen.** Risk shows the VaR/CVaR estimate warning at the top *and* again in the Risk observations footnote [09][12]. Analysis "Producer & conflicts" repeats the footer's producer line + "Not authorised…" [19]. | Risk, Analysis | Keep one per screen where the requirements need it near the figures. Remove the footnote copy, or the top banner (check DIS-x mapping in the compliance plan before removing). In "Producer & conflicts", keep only the stock-specific lines (founder position, no issuer payment) and link the rest. | S |
| G12 | P2 | **Page header actions are placed differently on each page.** Dashboard: "Refresh" top right. Portfolio: Export + Add position top right. Screener: "Reset filters" bottom left under the provenance [04]. Settings / Legal / Analysis: "← Back" tertiary buttons with different labels, and Settings content is indented differently. | All | One `page_header(title, subtitle, actions=[…])` helper: title + subtitle left, actions right-aligned on the title baseline. Back link always above the title, same style. | M |
| G13 | P3 | **Phone width (375 px) is broken.** Horizontal overflow: the page is 554 px wide (holdings table), so the signal badge is cut. The top nav loses Portfolio and Risk (no overflow menu). The header takes ~190 px before content [31]–[33]. | All | Bottom tab bar or hamburger under 768 px. Tables → stacked "card rows" (ticker + signal on line 1, price/MoS/value on line 2). Related to the parked "tablet layout" backlog item. | L |
| G14 | P2 | **Footer floats mid-screen on short pages** [13]. | Analysis empty, any loading page | See 1.1 item 6. | S |
| G15 | P2 | **Default Streamlit blue `st.info`** for the empty Analysis state ("No stock selected…") [13] and the legal translation notice. Large blue text, off-brand. | Analysis, Legal | Use the app's own notice component. Empty state per brand voice: icon + "No stock selected." + secondary line + a "Go to screener" button. | S |
| G16 | P2 | **Placeholders look like values.** "TTE.PA" / "TotalEnergies" in the Watchlist add form [06], the target textareas in Settings [23]. | Watchlist, Settings | Placeholder colour `var(--faint)` at ~45 % opacity. Prefix with "e.g." | S |
| G17 | P2 | **Composite score headline in mint for a neutral statement.** "Middle range of the model scale" / "Lower range…" is in the positive/brand colour. The ring is teal at any value. | Dashboard, Analysis | Headline in `var(--text)`. Ring colour from the composite bands (as `quality_score_color` does for sub-scores). | S |
| G18 | P2 | **Market status at < 1100 px is just a dot** without a label (the "Market closed · 14:28" text is hidden) [01]. | Header | Keep a short label ("Closed") or add a tooltip on the dot. | S |

---

## 3. Findings per screen

### Dashboard [01]–[03], [29], [30]

| # | Pri | Finding | Proposal |
|---|---|---|---|
| D1 | P2 | Score & risk card: ~50px empty gap between the risk bar and the Beta / Volatility / Max drawdown row [01]. | Distribute with `justify-content: space-between`, or move the three stats directly under the bar. |
| D2 | P2 | "Portfolio value over time" headline shows `€ 23.708 +559,4 % All` next to KPI "Total return −15,5 %". Two very different "returns" on one screen. The +559 % is value vs the first data point and includes deposits. | Show the money-weighted return for the selected range, or label it "vs first value (incl. deposits)". Or drop the % chip. |
| D3 | P2 | KPI "Current value" shows a red `−24,6 %` chip with no label (vs what? cost?). | Add "vs cost" to the sublabel, same pattern as "incl. dividends" on Total return. |
| D4 | P2 | Sector allocation: the donut is small (~70px) with unreadable %-labels overlapping it, inside a ~240px-tall card with a large empty area [03]. | A larger donut (140–160px) with no labels on the ring. Put the % in the legend ("Real Estate 32,2 %"), or use a horizontal 100 % bar + legend list. |
| D5 | P2 | Holdings legend row (Below / Near / Above model fair value) wraps onto its own line under the provenance. | Move into the provenance strip, right-aligned (see 1.2). |
| D6 | P2 | Upcoming dividends: company names in raw caps ("CEOTRONICS AG I", "TUI AG N"); the yield shows 16,47 % for Care Property (check the calculation basis). | G5 names. Check the yield basis (gross vs net, per-payment annualised?). |
| D7 | P2 | Top movers: the ticker column in faint mono duplicates the name, and the names are truncated. | Show either ticker or name (name with the ticker on hover), and give the name column the space. |

### Screener [04]

| # | Pri | Finding | Proposal |
|---|---|---|---|
| SC1 | P2 | Filter card: the "SIGNAL" label sits ~4px lower than "SEARCH" and "SECTOR". The Min score slider is ~50px wide; row 2 leaves the right half empty. | Use one label component (same top margin). Two rows on a 4-column grid: Search · Signal · Sector · Market / Min score · Min MoS (sliders ≥ 200px). |
| SC2 | P2 | "Reset filters" floats left between the provenance and the filter card. | Move it into the filter card header (right), as a tertiary button, shown only when filters differ from the defaults. |
| SC3 | P2 | 125 rows rendered at once (page ~9 300px), no sticky header. | Paginate (25 + "Show 25 more"), and make the table header sticky. |
| SC4 | P2 | The exchange label next to the ticker ("Milan") is 9px faint mono, hard to read. | 10.5px muted sans, or a small country flag/code chip ("IT"). |
| SC5 | P2 | Signal counts aren't visible in the filter pills. | Show the counts in the pills (see 1.2 item 5). |

### Watchlist [05], [06]

| # | Pri | Finding | Proposal |
|---|---|---|---|
| W1 | P0 | While loading: an empty bordered box under the provenance, no skeleton [05]. | Skeleton rows (G1). |
| W2 | P2 | 0px gap between the provenance line and the table card [06]. | 8–12px (part of 1.2). |
| W3 | P2 | Rows are grouped by exchange (Paris, then Milan, then Frankfurt), not sorted by score or MoS. No column sort. | Default sort by composite score, with clickable headers, as on the Screener. |
| W4 | P2 | **Score number colours look inconsistent**: two rows with score 75 (EQS.PA teal, TRI.PA white), and 72/74 white while 76 is teal. | Check which band function colours the watchlist score. It should match the Screener (`quality_score_color`). |
| W5 | P2 | BC.MI shows P/E `0,0` and MoS `+100,0 %`; TPG0.DE P/E `0,5`. | Show "—" for P/E ≤ 0 or missing EPS. Cap or flag MoS = 100 % (fair value without a price basis?). |

### Portfolio [07], [08]

| # | Pri | Finding | Proposal |
|---|---|---|---|
| P1 | **P0** | Dividends received: amounts wrap mid-number ("€ 109,⏎20"); Closed positions: "€ 228,4⏎2" [08]. | `white-space:nowrap` + right-aligned numeric columns (G9). |
| P2 | **P0** | "closed **mei** 2026" (Dutch month) [08]. | G8. |
| P3 | P2 | Cash balance card: Deposit and Withdraw are stacked, with different widths; large empty area; "Last entry 27/07/2026 · dividend" wraps under the amount [07]. | Buttons side by side, same width, aligned with the bar's right end. Amount + last entry on one line, or give the left column a min-width. |
| P4 | P2 | Open positions shows 5 rows and only an expand icon (↗) top right as the way to see the other 11. | Add a "Show all 16 positions" text link under the 5th row. |
| P5 | P2 | Closed positions / Dividends received have different heights; "SHAR…" and "NET DIV…" headers truncated. | G6, G9. |

### Risk [09]–[12]

| # | Pri | Finding | Proposal |
|---|---|---|---|
| R1 | P0 | While loading, only two notices show (amber warning + info), no skeleton [09]. | G1. |
| R2 | P2 | Two notices stacked above the content in different styles (amber-bordered warning, plain info box) [10]. | One combined notice: a warning line plus a muted second line for the cash note with "View cash activity". Or move the cash note into the risk-score card. |
| R3 | P2 | The risk-contribution table has **no title** (header row starts straight after the cards) [11]. The "FLAG" header sits far right while the flags render left in their column. | Title "Risk contribution by holding". Left-align the FLAG header with its content. |
| R4 | P2 | Concentration card: large empty bottom half (stretched to the Factor card's height) [11]. | Add the HHI gauge or the country concentration bar here (the note already mentions Belgium 61 %), or let the factor card be the full row. |
| R5 | P2 | Factor labels "Mkt-RF, SMB, HML, RMW, CMA, WML" are jargon; the footnote "\|loading\| > 1.5 = concentrated factor bet" is technical. | Lead with the plain label ("Market sensitivity") and show the code as a small mono chip. Rewrite the footnote in plain words. |
| R6 | P2 | Risk observations: two rows for AED.BR say the same thing ("changed from Medium to High" + "position risk rating High"). "Sharpe … (was −0,28 at 4/10/2026)" compares with the same value on the same day. | De-duplicate per ticker. Hide the "since last report" comparison when the previous report is the same day/value. |
| R7 | P2 | Dashboard showed risk score **35**, Risk page **36** on first load (later both 36). | Part of G1: same source, no stale value. |

### Stock drawer [14], [15]

| # | Pri | Finding | Proposal |
|---|---|---|---|
| DR1 | P2 | "SIX-MODEL FAIR VALUE" heading but five rows (no DCF row), and "basis · 2 of 6 models". | Always list all six models (DCF with "—"/reason), or rename the heading to "Model fair values". |
| DR2 | P2 | Fair value `€ 35,82` in mint (positive colour) while the price is double it (MoS −116 %). | Fair value in neutral text. Colour only the MoS. |
| DR3 | P2 | "Exchange —" for SYENS.BR, though Brussels is known elsewhere (ticker suffix, Analysis header). | Fall back to the suffix → exchange map. |
| DR4 | P2 | "YOUR RECORDS · NOTHING IS EXECUTED" label has 0px gap above the buttons, and the buttons touch the drawer's bottom edge [15]. | 8px label gap; sticky action footer with 16px padding and a top divider. |
| DR5 | P2 | Provenance wraps mid-phrase ("…12:31, delayed"). | 1.2. |

### Analysis [13], [16]–[19]

| # | Pri | Finding | Proposal |
|---|---|---|---|
| A1 | P2 | Empty state uses default blue `st.info` [13]. | G15: brand empty state + "Open screener" button. |
| A2 | P0 | Header shows composite **0 "Lower range"** for SYENS.BR, while the drawer correctly says **"excluded"** (fails quality screen). | Show "Excluded · fails quality screen" in the header, not 0. |
| A3 | P2 | "← Back to dashboard" even when opened from the Screener / Watchlist / Risk. | Remember the origin page (same as L9). |
| A4 | P2 | Provenance hugs the KPI cards (0px gap). | 1.2. |
| A5 | P2 | Model summary (the plain-language sentence) is the **last** card on the page. | Move it right under the header / KPI row. It's the best orientation text on the page. |
| A6 | P2 | Badge history row: date, badge and "score 0 · margin of safety −117 % · model M1" are misaligned (badge floats, meta indented under it), with a big empty area below [18]. | A proper timeline row: date (mono) · badge · meta on one baseline. Card height = content. |
| A7 | P2 | Quality screen checks: "Dividend covered by earnings  — · at risk: payout 774%" has a stray "— ·". | Drop the empty value before the separator. |
| A8 | P2 | Data sources card: the "No data quality flags" line sits on the card's bottom edge (no bottom padding) [19]. | Standard card padding. |
| A9 | P2 | Column ratios change per row (G6). | One grid. |

### Admin [27]

| # | Pri | Finding | Proposal |
|---|---|---|---|
| AD1 | P2 | Role select truncated to "Ad". | Min-width 110px, or plain text + edit icon. |
| AD2 | P2 | "Last active 2026-10-04 11:06" is ISO (ignores the user's date format) and sits ~6px below the row's centre line. | Use `fmt_datetime`, vertically centre. |
| AD3 | P2 | "All systems operational" wraps onto 2 lines in the header. | `white-space:nowrap`, or a shorter "Operational". |

### User menu [28]

| # | Pri | Finding | Proposal |
|---|---|---|---|
| U1 | P2 | Email is an underlined link (mailto to yourself), role "Admin" is plain text, "Sign out" is a small underlined link with no icon or divider. | Email in muted text, role as a chip. Sign out as a menu item with a `logout` icon after a divider. |
| U2 | P2 | No route to the legal pages or the language from the menu. | Add "Legal & policies" (L13). Optionally a language quick-switch. |

---

## 4. Suggested implementation order

Each step is a self-contained commit or PR. Run the full test suite and a visual check with
`/run-uvalu` after each.

1. **P0 fixes, one PR (≈ 1 day).** G1 (loading states / no fake 0s, incl. A2, R7), G2 (dark badges),
   G8 (locale leaks: mei, Maandag), G9 numeric `nowrap` (P1), S1 (withholding grid), S2 (`BUY` preview
   → current signal labels), legal nav truncation (L1).

   **Status 4 Oct 2026: done, not committed.** G1: `uvalu.data.peer_reference_pending()`; while the
   universe's peer reference is still building, the Dashboard KPI, Score & risk card and holdings show
   their skeleton, and `load_portfolio_risk` waits (its cache key now includes the reference version).
   Risk paints a shimmer before the blocking call. A2: Analysis header shows "—" plus "Excluded · fails
   a quality screen" (new msgid; FR/DE/IT/ES/NL fuzzy drafts to confirm in Poedit). G2: dark-theme
   badge overrides in `styles.py`. G8: `i18n.names_locale()`: month/day words in the UI language,
   pattern from the region (explicit `locale=` unchanged). P1/G9 (numeric cells only): right-aligned mono cells never wrap
   (`styles.py`); the header truncation part of G9 is still open. S1, S2, L1 done. W1 (empty Watchlist box) could not be
   reproduced on a warm start; re-check after a cold start.
2. **Footer (1.1), ≈ 1–2 h.** Including the Terms sentence and the test move for NOT_DIRECTED.
   Small and self-contained, and it touches legal texts, so keep it its own commit.

   **Status 4 Oct 2026: done, not committed.** Items 1–6. Text lines stay left-aligned (question 1,
   recommended option). The optional version marker (item 7) is not done.
3. **Provenance bar (1.2), ≈ ½ day.** New component + the five call sites + Screener pill counts.

   **Status 4 Oct 2026: done, not committed.** `provenance_bar_html` / `coverage_bar_html` /
   `fair_value_legend_html` in `components.py`. Items 1–8, with a staleness chip after 72 h (the same
   rule as the stock page's data flag). Pill counts are over the stocks with a fair value (what the
   table can show). The coverage bar keeps REC-10's share over all covered stocks. Existing msgids are
   kept; new ones: "Coverage", "oldest {age}", "{count} price(s) is/are more than 72 hours old.".
4. **Legal page (1.3), ≈ ½–1 day.** L2–L14.

   **Status 4 Oct 2026: done, not committed.** L2 (active state), L3 (no icons), L4 (sticky column),
   L5 ("On this page" from the `##` headings), L6 (header block with title, chips and a print button;
   the breadcrumb is gone), L7 (reference-language note only outside English), L8 (app notice style),
   L9 ("← Back to {page}", the last page visited in this session), L10 (72ch measure, H2 rhythm),
   L11 (current document marked in the footer), L12 (phone: section list and print hidden), L13 (user
   menu entry; the Settings "Legal" section comes with 1.4). L14 is moot: no document links to another yet.
   Print stylesheet checked by applying its rules on screen (the browser tool can't open a print
   dialog). Worth one real print or "Save as PDF" test in Chrome.
5. **Settings (1.4), ≈ 1–1½ days.** Row component + section nav first (fixes S4–S6), then the save
   model, the copy cleanup and the controls.

   **Status 4 Oct 2026: done, not committed.** Sticky section nav; page on the standard gutter.
   Order: Language & region first (kept first for i18n spec S-06), then Account (profile card with
   Sign out, Security, Sessions), Display, Portfolio, Data & alerts, Import & export, Model settings,
   Legal. Row fixes: first row under each header, centred labels (the markdown container's -16px
   margin was the cause), 4-option controls stacked under their description. Save model: autosave for
   choices, explicit Save for targets and withholding (new). Model card: "Affects all users · logged"
   chip, duplicate thumb value hidden, help text under the label. Copy: no "PHASE 3"; linked
   accounts show only offered providers (else a beta line); the US toggle explains why. Controls:
   segmented date format and week start, HHI empty = default, withholding labels with "(%)",
   placeholders faint app-wide (G16). Import: confirm step listing what the file holds, in a danger
   box; the uploader resets afterwards (this also fixes the re-import loop the old test had to stub).
   Not done: a structured target editor (the textareas stay), slider min/max ticks, a "View change
   log" link (no change-log page exists yet).
6. **Design-system polish, ≈ 1 day.** G3–G7, G10–G12, G14–G18. Mostly CSS/helpers in `components.py`
   and `shell.py`.

   **Status 4 Oct 2026: done, not committed.**
   - G3: dark `--uv-track` tint.
   - G4: the minus goes in front of the symbol in every symbol-first format (`-€ 86,01`); the
     hand-written "−" prefixes now go through `fmt_money`.
   - G5: `uvalu.formatting.display_name` applied in all row helpers, the Dashboard dividends and movers,
     the drawer and Analysis; names are also HTML-escaped.
   - G6: Analysis rows are 50/50. Equal heights on the Dashboard bottom row and the Portfolio
     closed|dividends row were left off: both were turned off on earlier request, because they left
     empty space under the shorter card.
   - G7: one caption style inside cards; the risk-contribution note is inset.
   - G10: concentration bars and "Above reference" are amber, "Notice" is muted. Sharpe/metric
     sub-labels keep the risk scale's colours, since they share the gauge's single source of truth
     (v1.5.1).
   - G11: the Risk footnote no longer repeats DIS-3's sentence from the top warning. Analysis
     "Producer & conflicts" is unchanged (REC-1 producer identity on the stock page).
   - G12: Analysis back link via `nav.back_target`.
   - G14, G16: done earlier.
   - G15: Analysis empty state with an "Open the screener" button.
   - G17: composite headline in text colour, ring coloured by band.
   - G18: a one-word market status below 1200px.
   - G9 remainder left as is: KPI and table-header labels truncate with a tooltip on purpose, so tiles
     keep one shape in every language.
7. **Per-screen polish.** The remaining D/SC/W/P/R/DR/A/AD/U rows.

   **Status 4 Oct 2026: done, not committed.**
   - Dashboard: D2 "{range} · incl. deposits", D3 "unrealised · incl. … cash", D4 donut full width with
     % in the legend, D7 movers show the name (ticker as tooltip).
   - Screener: SC1 filters top-aligned, sliders fixed-width and grouped; SC2 Reset only when filters
     differ from the defaults; SC3 25 rows + "Show 25 more", sticky column header (card
     `overflow:clip`); SC4 exchange label 10.5px muted.
   - Watchlist: W3 sorted by composite score; W4 score banding on the rounded value; W5 P/E ≤ 0 (or
     shown as 0,0) → "—".
   - Portfolio: P3 cash card buttons side by side, same width; P4 "Show all N positions".
   - Risk: R3 table title; R5 plain factor names with the code as a chip and a plain-words footnote;
     R6 no plain "rating High" note when the transition note already says it (risk.py).
   - Drawer: DR1 "Model fair values"; DR2 fair value neutral (also the Analysis hero); DR3 exchange
     from the ticker suffix (`uvalu.formatting.exchange_label`, one shared map); DR4 spacing around
     the record buttons.
   - Analysis: A5 model summary under the price cards; A6 badge history date and badge on one line;
     A7 no stray "— ·"; A8 last block of a card no longer sits on its edge.
   - Admin: AD1 wider role column; AD2 last active via `fmt_datetime`, row cells centred; AD3 status
     on one line.
   - User menu: U1 plain email, role chip, Sign out as an icon menu item.

   Not done:
   - D1 (the stats footer is bottom-aligned on purpose, so the two cards share a row height).
   - D6 yield basis (a data question, not styling).
   - R2 (the DIS-3 warning stays its own box).
   - R4 (country was left out of the Concentration bars on purpose; it shows as the flag banner).
   - SC "FLAG" header (already aligned with its column).
   - W1 (not reproduced).
8. **Phone layout (G13), separate project.** Merge with the parked "tablet layout" backlog item.

   **Status 5 Oct 2026: parked in the backlog** as its own item next to the tablet layout. Not started.

---

## 5. Questions to decide before implementing

1. **Footer "first line".** I read "first line with info on Uvalu" as the disclaimer paragraph
   ("Uvalu is an analysis tool…"), which is the one capped at 980px. The plan makes both text lines
   full width either way. Should the two text lines stay left-aligned (recommended: easier to read)
   or also be centred like the links?
2. **NOT_DIRECTED.** OK to add the explicit UK/US/CH sentence to the Terms (beta + launch) when it is
   removed from the footer? That keeps INT-5/INT-6 covered.
3. **Provenance.** Visible compact strip (recommended, keeps REC-4/5/10 visible) or the quieter
   chip-with-popover? Do you want the staleness chip, and from how many days?
4. **Settings navigation.** Sticky left section list (recommended for desktop) or `st.tabs`?
5. **Save model in Settings.** Autosave for toggles/selects + explicit Save for free text
   (recommended), or explicit Save everywhere?
6. **Company name cleaning (G5).** Fine to title-case all-caps names in the display layer (it doesn't
   touch stored data)?
