# Accessibility review

13 Oct 2026 · First pass in the role of expert profile [10](experts/10-accessibility-specialist.md): an accessibility specialist checking WCAG 2.2 AA / EN 301 549 and the European Accessibility Act. There is no separate persona file for this role.

**Method:** automated checks in the running app (master `4d8273b`, Dashboard and Screener, light and dark theme) using in-page scripts for headings, landmarks, accessible names, language, page titles and text contrast. Plus the brand guidelines' own rules.

**Not done:** testing with a real screen reader (NVDA, VoiceOver), a full keyboard-only pass, or 200% zoom and reflow. Those are the specialist's job, and this review doesn't replace them.

## Conclusion

- **Legal obligation today: low.** The European Accessibility Act exempts micro-enterprises that provide services. Uvalu has fewer than 10 people and less than €2 million turnover, so it is exempt (Directive 2019/882 art. 4(5); settled). The exemption ends as the business grows, and a public accessibility statement is good practice anyway.
- **Real users: medium–high.** Visually, the app is in good shape: high-contrast text, signal and risk labels that never rely on colour alone, focus rules in the brand guidelines. But for a **screen-reader user** the structure is nearly missing:
  - no headings and no landmarks
  - tables built from `div`s
  - 50 buttons called "★" and 25 called "View"
  - icon names read aloud ("light_mode", "expand_more")

  Most of this sits in shared components, so a few fixes in `uvalu/components.py` and `uvalu/shell.py` cover every screen.

| # | Finding | WCAG | Severity |
|---|---|---|---|
| A1 | No headings or landmarks: page titles are `div`s | 1.3.1, 2.4.6, 2.4.1 | High |
| A2 | Lists and tables have no table semantics; row buttons have no context | 1.3.1, 2.4.6, 4.1.2 | High |
| A3 | Icon names are read aloud as part of button names | 4.1.2, 2.5.3 | Medium |
| A4 | Every page is `lang="en"` and titled "uvalu" | 3.1.1, 2.4.2 | Medium |
| A5 | Primary button text below 4.5:1; very small text | 1.4.3 | Medium |
| A6 | Charts have no text alternative | 1.1.1 | Medium |
| A7 | Loading and results aren't announced | 4.1.3 | Low–medium |
| A8 | Focus outlines removed in 13 CSS rules: verify the replacements | 2.4.7, 2.4.11 | Low (verify) |
| A9 | No accessibility statement or feedback route | EAA annex, good practice | Low |

## A1. Headings and landmarks (high)

**Evidence.**

- **Dashboard:** 0 `h1`, `h2` or `h3` elements, and one element with `role="heading"`. The page title "Portfolio overview" is a `div.uv-page-title`. Section titles ("Score & risk", "Holdings · price vs fair value", "Upcoming dividends") are styled text.
- **No landmarks:** no `main`, no `nav` (the top navigation isn't marked up as navigation), and no skip link.

**Impact.** Screen-reader users move through a page by headings and landmarks. Without them, every page is one long run of text and buttons.

**Fix.**

- Render the page title as `<h1>` and the card or section titles as `<h2>`, in the shared helpers that already draw them (`uv-page-title`, the card title helpers). Keep the class for styling.
- Wrap the top navigation in `<nav aria-label="Main">`.
- Add a "Skip to content" link targeting the page title.

## A2. Tables and row buttons (high)

**Evidence.**

- The Screener, Dashboard Holdings and Risk "contribution by holding" are grids of `div`s. No `table` element, and no `role="table"`, `row` or `cell`.
- On the Screener: **50 buttons named "★"** (watchlist stars, with no stock name and no on/off state) and **25 buttons named "View"**. On the Dashboard: six "View details".

**Impact.** A screen reader can't connect "+86,1%" to "Margin of safety", or "★" to a company. A user tabbing through hears "star, star, star… View, View, View".

**Fix.**

- Give each row button its stock: `aria-label="Add Investor AB to watchlist"` with `aria-pressed`, and `aria-label="View Investor AB"`.
- Mark the grids up as `role="table"` with `role="row"`, `role="columnheader"` and `role="cell"`, or render a visually hidden real `<table>` next to the visual grid. Indicate the sort column with `aria-sort`.

## A3. Icon names read aloud (medium)

Accessible button names include the Material Symbols ligature text: **"light_mode"** or **"dark_mode"** (the theme toggle, twice), **"SC expand_more"** (the account menu), "add Add position", "refresh Refresh".

**Fix.**

- Put `aria-hidden="true"` on icon spans.
- Give icon-only buttons a real label: "Switch to dark theme", "Account menu for Sven Claes".

## A4. Page language and titles (medium)

- `<html lang="en">` on every page, whatever language the user picked. A Dutch or French screen-reader user hears their language read with English pronunciation (3.1.1).
- `<title>` is "uvalu" on every page (`app.py` sets `page_title="uvalu"`), so browser tabs and history can't be told apart (2.4.2).

**Fix.**

- Set `document.documentElement.lang` from the active locale on each render, through the same small script mechanism the app already uses.
- Set a page title per page: "Screener · Uvalu", "Risk · Uvalu", and so on, translated.

## A5. Contrast and text size (medium)

The text-contrast scan found **one failure, repeated:** the primary button ("Add position") uses white text on Signal Teal `#1A8C6E`, which measures **4.18:1** at 12.5px. Normal-size text needs 4.5:1 (1.4.3). The brand guidelines themselves say Signal Teal is "not for small text: 4.2:1 on white".

**Fix:** use the darker `--link` teal for primary-button fills, or a shade that reaches 4.5:1 with white. All other sampled text passed in both themes.

**Size.** Signal badges are 10.5px, and the uppercase small labels are 10–11px. That's a deliberate brand decision (kept in v1.3), and size isn't a WCAG AA criterion on its own. But at 10.5px, low-vision users will zoom, and the layout must then reflow. See "Not tested".

## A6. Charts (medium)

The Plotly charts (portfolio value over time, price against fair value) and the risk gauge have no text alternative. The gauge has `role="img"`; check it has a name.

**Fix.** Give each chart a one-sentence summary as its accessible name or as visible text, for example "Portfolio value €23,662, +7.5% over the past year". Where the data matters, add a "Show as table" option.

## A7. Status messages (low–medium)

"Loading the screening universe… 0/2665 companies scored", "Rebuilding the peer reference…" and "2033 of 3942 stocks pass your filters" change on screen without being announced. **Fix:** put them in an `aria-live="polite"` region (`role="status"`), so a screen-reader user hears when results arrive and how many match.

## A8. Focus (low, verify)

The app's CSS has 34 `:focus-visible` rules, and 13 rules that set `outline: none` or `0` on focus. The brand guidelines require a 2px teal or mint ring that is never removed without a replacement. A keyboard pass should confirm each of the 13 has its replacement, especially the invisible full-row overlay buttons in Holdings and Risk. Their focus must be visible on the row.

## A9. Accessibility statement (low)

There is none. Even while exempt, add a short statement to the Help or legal pages:

- the target (WCAG 2.2 AA)
- known gaps (this list)
- a contact (support@uvalu.app)
- the date

It costs an hour, and the EAA expects one once Uvalu is no longer exempt.

## What is right

- **Signals and risk bands always carry text,** never colour alone. P&L carries a sign.
- **Text contrast** passes everywhere except the primary button. The brand palette was built with contrast ratios in mind.
- **Form inputs have labels:** Search, Sector, Market, Min score, Min margin of safety.
- **Focus rules exist** in the brand guidelines and the CSS.

## Not tested, for the specialist

- NVDA and VoiceOver on the Dashboard, Screener, Analysis, Risk, the sign-in and two-factor forms, and the dialogs (add position, cash).
- Keyboard-only: focus order, dialogs trapping and returning focus, the stock drawer.
- **200% zoom and 320px reflow (1.4.10).** This will probably fail, because tablet and phone layouts are parked (open item P2).
- Target size 24×24 px (2.5.8) for the stars and small icon buttons.

## Recommended changes, in order of value

1. **Headings and landmarks** in the shared page and card title helpers, plus nav and skip link (AC1).
2. **Row buttons with names and state,** plus table semantics for the Screener, Holdings and Risk grids (AC2).
3. **Icons hidden from screen readers,** icon buttons labelled (AC3).
4. **`lang` from the locale** and a title per page (AC4).
5. **Primary button contrast** (AC5).
6. **Chart summaries** and live regions for loading and result counts (AC6).
7. **An accessibility statement,** then the specialist's screen-reader, keyboard and zoom audit (AC7).

Items 1–5 live mostly in `uvalu/components.py`, `uvalu/shell.py` and `uvalu/styles.py`, so they fix every screen at once. Add a test that fails when a new row button has no `aria-label`.
