<!--
Uvalu public page — FREE BETA version (same text as ../accessibility.md; keep both in step).
Uvalu public page. Status: FINAL TEXT for the beta, written 15 October 2026 (AC7, docs/accessibility-review.md A9).
The gaps list must follow docs/open-items.md (Accessibility, P2): update both together, and the date.
"Exempt" refers to the micro-enterprise exemption in the European Accessibility Act (Directive (EU) 2019/882,
art. 4(5)) as transposed in Belgium; counsel to confirm before the paid launch.
Only what was checked in the running app 14–15 October 2026 is claimed as working.
-->

# Accessibility statement

**Version:** beta 1.1 · **Last updated:** 15 October 2026

We want Uvalu to be usable by everyone, including people who use a screen reader, a keyboard instead of a mouse, or a larger text size.

## 1. Our target

Our target is the Web Content Accessibility Guidelines (WCAG) 2.2, level AA.

As a micro-enterprise, Uvalu is not yet required to meet the European Accessibility Act. We aim for the same level anyway, and this page says honestly where we are.

## 2. How we checked

- **13 October 2026:** our own review of the Dashboard and the Screener in light and dark themes, with automated checks for headings, landmarks, button names, page language, page titles and text contrast, and a review of the code behind every screen.
- **14–15 October 2026:** the fixes listed under section 3, each checked in the running app.

No accessibility specialist has tested Uvalu yet. A test with screen readers (NVDA, VoiceOver), keyboard only and 200% zoom is planned before the paid launch.

## 3. What works

- Every page has a heading structure, a main navigation, a main content area and a footer, plus a **Skip to content** link as the first thing you reach with the Tab key.
- Each browser tab shows the page name, and the page language follows the language you chose.
- Buttons say what they do and to which stock, for example "View Investor AB (INVE-B.ST)". The watchlist stars say whether a stock is on your watchlist. Icon names are not read out.
- Every table (Screener, Watchlist, Dashboard and Risk holdings, and the Portfolio page's positions, dividends and cash activity) is a table for screen readers, with column headers, and the Screener says which column it is sorted by.
- The value and price charts are described in one sentence with their figures.
- Loading progress on the Screener and the Watchlist, and the number of Screener results, are announced when they change.
- In our checks, text had a contrast of at least 4.5:1 against its background, in both themes.
- Signals and risk levels are always written out in words, never shown by colour alone. Gains and losses carry a + or − sign.
- Form fields have labels.

## 4. Known gaps

- **Charts.** The charts have a one-sentence summary, but no table view of the underlying data.
- **Narrow screens and zoom.** Uvalu is designed for a desktop window. At 200% zoom or on a phone, some content may need horizontal scrolling. Tablet and phone layouts are planned.
- **Small targets.** Some small buttons, such as the watchlist stars, may be smaller than 24 × 24 pixels.
- **Keyboard focus.** The focus outline on rows that open a stock's details has not yet been checked everywhere.
- **Small text.** Signal labels and some column labels use 10–11 pixel text by design. Use your browser's zoom if they are hard to read.
- **Admin pages.** The administration screens, used only by Uvalu's own staff, have fewer of the fixes above.
- **Languages.** The app is available in English, Dutch, French, German, Italian and Spanish. The legal texts, including this one, are in English only for now.

## 5. Contact

If something in Uvalu is hard to use for you, or you need information in another format, write to **uvalu.app@gmail.com**. Tell us which page you were on and what you were trying to do. We read every message and will tell you how and when we plan to fix it.

If you are not satisfied with our answer, see the Complaints page.
