# Prompt: implementation plan for aligning Uvalu with the design reference

Paste everything below the line into your coding tool, run from the root of `svenclaes76/UV` (branch `master`).

---

You are preparing an implementation plan. **Do not change any code, tests, translations or docs in this task.** Read, assess and write one file: `docs/design/implementation-plan.md`. I will review that plan before any work starts.

## Sources of truth

1. `docs/design/Design reference.md` is the design reference. Where it conflicts with code, comments, `docs/design/README.md` or older design files, the reference wins.
2. The mockups it points to: `docs/design/Uvalu.dc.html` (main app), `docs/design/Uvalu Admin.dc.html` and `docs/design/Uvalu Auth.dc.html`. Read them as source: the template markup holds the layout and inline styles, and the logic class at the bottom holds the data and state rules. If you can open them in a browser (they need `support.js` and `legal-docs.js` next to them), use that to confirm positions, but take values from the source. Each screen has a `data-screen-label`; Tweaks props (`environment`, `updateNotice`, `newBuild`, `appState`, `dataState`, `founderHolds`) switch states.
3. Brand: `docs/uvalu-brand-guidelines.md` v1.3 for tokens, type, spacing, radii and components. Where it disagrees with the mockup on a value, flag it under "Gaps needing a decision".
4. Legal constraints: `docs/legal/compliance-implementation-plan.md`, `docs/legal/policies/beta/*.md` and `uvalu/compliance/disclosures.py`. Never plan wording that conflicts with them. Signals are Undervalued / Neutral / Low score / Fails quality screen / No signal, and never read as personal advice.

## Scope

**In scope:** desktop (about 920px and wider), light and dark themes, English source strings plus the five other languages' catalogues for any string you add, rename or remove.

**Out of scope, do not plan:** everything under "Deferred to later implementation" in the reference (phone and tablet layouts, Privacy self-service, acceptance records and the Settings › Legal row, Plan card), and the "Check with real translations" list. Mention them once in a "Not in this plan" section.

## What to do

### 1. Assess

Compare the code with the reference, screen by screen: Dashboard, Screener, Watchlist, Portfolio (overview, open, closed, dividends, cash), Risk, Analysis, Settings, Methodology, Legal, About, sign-in and invitation, Admin (Users, Data feeds, Backups & restore, System, Security), and the global elements (top bar, user menu, beta banner, footer, notices, environment marker, maintenance and error states).

For each difference, record the file and function, what the code does, and what the reference shows. Sort each one into a category:

- **Must change:** the reference's "Decisions built into the reference", "Label changes for the code" and "Code removals" sections. These are already decided.
- **Layout:** structure, position, typography, colour or spacing differs from the mockup, at one of the three levels in Layout fidelity below.
- **Gap:** the reference shows it and the code doesn't, or the reverse, and it isn't covered by a decision.
- **Matches:** list these briefly so I can see what was checked.

Items that must be in the plan, at a minimum:

- Labels: "Methodology & help" → "Methodology"; Settings "Account" → "Account security"; Settings menu "Portfolio" → "Target allocation".
- Remove Settings › Data & alerts (price refresh interval, ex-dividend, cut/suspension and increase alerts, weight threshold). Keep Dividend withholding as its own section `set-withholding` between Target allocation and Import & export. Trace every reader of `refresh`, `alert_ex_div`, `alert_dividend_size`, `alert_div_cut` and `alert_div_increase`, and say what happens to each (fixed default or removal).
- Settings order: Language & region, Account security, Display, Target allocation, Dividend withholding, Import & export, Model settings, Legal. Privacy and Plan are deferred.
- "Margin of safety", never "Upside" (Holdings, Watchlist, Screener column, Dashboard tile "Avg margin of safety").
- A negative margin of safety and a price above model fair value are amber, not red. Red is only for a failed quality screen.
- Score bands at 70 and 40 (Upper 70–100, Middle 40–69, Lower 0–39), matching the Undervalued and Low score thresholds.
- Holdings last column: P&L against average cost.
- All page titles 24px; all back links "← Back to …".
- Screener: let a missing margin of safety through while the margin filter is at its default (`uvalu/pages_/screener.py`, the `fillna(-999)` line), so No signal stocks are visible.
- Colour tokens and components per `docs/uvalu-brand-guidelines.md` v1.3 (update that file from the design project first): add `--link` and use it for link text; `--amber-txt`/`--amber-bg`/`--amber-fill`; badge token pairs; ladder fills up / neutral (`--axis`) / amber on `--uv-track`; `--faint` never for readable text; `warning` symbol in `_stale_chip_html`; beta "Beta" label in `--up-txt`; radii rounded to 4/6/8/12px; `:focus-visible` ring; supporting pages left-aligned with a 32px column gap. Icons: Material Symbols (outlined) everywhere, as in the mockups. The guideline's own "Code follow-ups" list is in scope.
- States the code has that the reference now shows: No signal, peer-reference rebuild, stale-price "oldest …" chip, founder-holds notice, Show more. Check that each one matches the mockup's wording and placement.

#### Layout fidelity

Compare the layout as well as content and behaviour. The mockups use inline styles, so values can be read from the source. Read them; don't estimate from screenshots. Some mockup values are compromises made for the preview (for example column widths tuned for 920px), so treat them as intent, not as hard specs, when they conflict with a clean shared style.

Check at **1280px** in both themes. Spot-check **920px** only for wrapping, overflow and grid changes.

Sort every layout difference into one of three levels:

**Must match**: report every difference.
- **Structure and order:** which cards, sections, rows and table columns exist, and in what order. Card positions in the grid: which sit side by side, which are full width, and the rough proportions.
- **Text position:** where each label, value, chip, badge, link and button sits relative to its neighbours. Examples: the legend on the Holdings title row, the provenance line under the title, Methodology → at the end of that line, status text under a segmented control.
- **Typography:** font family (sans or mono), size, weight, case (sentence case versus uppercase), colour token, and alignment (numbers right-aligned in tables).
- **Colour tokens:** text, fill, border and background tokens in both themes, including the separate text tokens for mint, amber and teal.
- **Page frame:** the max-width of each page type, the section rail and content widths on supporting pages, and the back link and title block.

**Should match**: report only differences larger than **4px**, or a clearly different visual rhythm.
- Padding inside cards, card headers and rows; gaps between cards and rows; margins around titles, subtitles and the provenance line.
- Line height, letter spacing, row height, border radius, badge and chip sizes, button padding, icon size.

**Accept the framework**: don't report these unless the difference is clearly visible to a user.
- The internal spacing and sizes of Streamlit widgets (inputs, selects, sliders, toggles, file uploader, dialogs), focus rings, and spacing Streamlit adds between elements.

How to fix:
- Fix spacing and type through a small set of **shared values in `uvalu/styles.py`** (a spacing scale, card and card-header styles, title and body text styles) and shared helpers in `uvalu/components.py`, not with one-off overrides per screen.
- Prefer stable selectors (`st-key-…` containers the app owns) over Streamlit's internal class names, which change between versions. If an exact match needs fragile internals, propose the closest stable value instead and say how big the visible difference is.

How to report:
- Per screen, list the **5 most visible differences first**, then the rest grouped by level.
- Use the category **Layout** in the assessment tables, with the level and the mockup and code values side by side, e.g. `Must match · title 24px/500 (mockup) vs 22px/500 (code)`.

### 2. Plan

Group the work into small, independently shippable steps. Each step should be one pull request of a size I can review in under 30 minutes. Order the steps by dependency first, then by user impact. Put shared foundations (colour tokens, label strings, shared spacing and card styles in `uvalu/styles.py` and `uvalu/components.py`) before the screens that use them. Do the shared layout values first, then group the remaining layout fixes per screen, Must match items before Should match, so each screen can be checked against its mockup in one go.

For each step give:

- **ID and title**, e.g. `S03 · Settings: remove Data & alerts`
- **Why:** the reference section or legal ID it implements
- **Files and functions** to change, and anything to delete
- **Changes:** concrete, at the level of "replace X with Y in function Z". No code. For layout, give the target values from the mockup (e.g. "card header padding 14px 20px, title 15px weight 500, sentence case").
- **Strings:** each source string added, renamed or removed, and the catalogues to update
- **Data and settings impact:** stored settings that become unused, migrations, defaults
- **Risks and open questions:** anything you could not decide from the sources. Don't guess; ask.
- **Tests:** existing tests affected (`tests/`), and new tests to add, especially for legal wording (`tests/test_compliance_algorithms.py`)
- **How to verify:** what to compare against which mockup screen and Tweak state, in both themes. For layout steps, a side-by-side check at 1280px of positions, text styles and the spacing values to measure, plus a 920px spot-check for wrapping.
- **Size:** S (under 2 hours), M (half a day) or L (a day or more). Split anything larger than L.
- **Depends on:** step IDs

### 3. Write `docs/design/implementation-plan.md`

Use this structure:

1. **Summary:** at most 10 lines: number of steps, total size and the three biggest risks. Below it, a small table with the count of Must match and Should match layout differences per screen.
2. **Assessment:** a table per screen with columns Item · Category (Must change / Layout / Gap / Matches) · Code location · Mockup value · Code value.
3. **Gaps needing a decision:** each with a recommendation and the alternative. I decide these before work starts.
4. **Steps:** in order, using the fields above.
5. **Not in this plan:** the deferred items and the translation checks, one line each.
6. **Release notes draft:** a `CHANGELOG.md` entry in the existing style, for when all steps are done.

## Rules

- Write in plain, factual English. Name files and functions exactly.
- If the reference and a legal document disagree, flag it under "Gaps needing a decision". Don't resolve it yourself.
- Don't propose redesigns or improvements beyond the reference. Put any you think are important in a short "Suggestions" list at the end, clearly separated.
- When done, reply with the path of the plan and the summary only.
