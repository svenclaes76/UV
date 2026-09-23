# Design reference

Source of truth for Uvalu's visual design. These are static mockups from the
[Claude Design project "Uvalu"](https://claude.ai/design/p/edc1baa4-ffbe-46e8-828c-a545703d9112)
(project id `edc1baa4-ffbe-46e8-828c-a545703d9112`), pulled in via the
`claude_design` MCP so the spec lives in the repo instead of only in the
design tool. All the `fix(design): reset ... to match Uvalu.dc.html spec`
commits on this project diff the app against these files.

| File | What it covers |
|---|---|
| [`Uvalu.dc.html`](Uvalu.dc.html) | Main app — Dashboard, Screener, Portfolio, Risk, Stock Detail, Settings, Help, Watchlist |
| [`Uvalu Admin.dc.html`](Uvalu%20Admin.dc.html) | Admin portal — Users, Data feeds, Backups & restore |
| [`Uvalu Auth.dc.html`](Uvalu%20Auth.dc.html) | Authentication — sign in/failure/throttle states, invite acceptance, password recovery, TOTP challenge, Settings → Security, Admin → Users/Security. From a separate Claude Design handoff session (not the `edc1baa4-ffbe-46e8-828c-a545703d9112` project the two files above came from), built for the auth overhaul on `feature/auth-overhaul-m1`; see [`docs/archive/uvalu-auth-implementation-plan.md`](../archive/uvalu-auth-implementation-plan.md) for the original design rationale (note: it's the pre-build proposal, not a frame-by-frame mapping — the shipped implementation deviates from it in several places, e.g. the JSON user store instead of a SQL table) and [`docs/architecture.md`](../architecture.md) for how the shipped auth system actually works. |
| [`Uvalu Dividend Management.dc.html`](Uvalu%20Dividend%20Management.dc.html) | Dividend Management v2 — Portfolio → Dividend log (summary tiles, 13-column event log, annual income summary), Add/Edit dividend modal (declaration/ex/record/payment dates, gross/share, foreign WH, type, frequency, Gross → Foreign WH → BE 30% → Net preview), open-positions income/yield/YoC columns, Stock Detail "Dividend & income" panel, Dashboard upcoming-dividends card, dividend alert settings. From the separate `Uvalu Dividend Management-handoff.zip` Claude Design handoff (not the `edc1baa4-ffbe-46e8-828c-a545703d9112` project), built for `feature/dividend-management-v2`; requirements in the bundle's `uploads/Uvalu - Dividend Management Requirements.md`. **Deliberate deviations in the shipped app** (per user review, Sep 2026 — don't "fix" these back to the mockup): no "Import from market data" button (the import runs automatically once per session), the log download sits next to Add dividend as "Export", no declaration/record-date sub-lines or "· frequency" suffix in log rows, the annual summary card is full width with an "Export" button, and there is **no "Withholding by domicile" card**. |
| [`support.js`](support.js) | Runtime the `.dc.html` files depend on (`<x-dc>` template engine + `DCLogic` base class). Required for the mockups to render standalone in a browser; not meaningful as a design reference on its own. |

`Uvalu-brand-guidelines.md` lives at [`docs/uvalu-brand-guidelines.md`](../uvalu-brand-guidelines.md)
(kept alongside the other product docs, not duplicated here) and is the same
content as the design project's `uploads/uvalu-brand-guidelines.md`.

## How to use this

- Open a `.dc.html` file directly in a browser to see the intended design —
  it's a self-contained interactive mockup, not just a static screenshot.
- Treat these files as **read-only reference**, not code to import into the
  Streamlit app. They define CSS tokens (`--bg`, `--teal`, `--mint`, spacing,
  radii, etc.), layout, and copy that `uvalu/styles.py`, `uvalu/shell.py`,
  and `uvalu/components.py` should match — but the app is native Streamlit,
  not a port of this HTML/JS.
- When the mockup changes upstream (new frame, spacing tweak, copy change),
  re-pull the changed file(s) from the same Claude Design project via the
  `claude_design` MCP (`get_file` with the path above) and overwrite the
  local copy, so this directory keeps tracking the live design rather than
  drifting into its own fork.

## Design System artifact

A [Claude Design System artifact](https://claude.ai/artifact/DL2qE8DNyMZ6R7Exacv5wQ) built
from the files in this directory plus `docs/uvalu-brand-guidelines.md` — tokens (colour,
type, spacing, radius, shadow, border), and live component previews for the main app,
Admin portal and auth flow. It's derived from these files, not a second source of truth:
if the mockups or brand guidelines change, re-derive the affected tokens/components there
rather than editing it independently. Private to the Claude account that created it; not
checked into the repo since its value (live previews, the interactive index) only works on
claude.ai.

## Screenshots

The design project also has PNG screenshots of each frame under
`screenshots/` (e.g. `01-analysis.png`, `01-risk.png`, `portfolio.png`).
They weren't pulled into the repo since the `.dc.html` files fully specify
the same visuals and are more useful (interactive, diffable, greppable for
exact hex/spacing values). Pull individual screenshots from the design
project on demand if a quick visual reference is more convenient than
rendering the HTML.
