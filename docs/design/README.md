# Design reference

Source of truth for Uvalu's visual design. These are static mockups from the
[Claude Design project "Uvalu"](https://claude.ai/design/p/edc1baa4-ffbe-46e8-828c-a545703d9112)
(project id `edc1baa4-ffbe-46e8-828c-a545703d9112`), pulled in via the
`claude_design` MCP so the spec lives in the repo instead of only in the
design tool. All the `fix(design): reset ... to match Uvalu.dc.html spec`
commits on this project diff the app against these files.

**Start with [`Design reference.md`](Design%20reference.md).** It lists which file is the reference for each screen, the design decisions built into it, label changes and removals for the code, items deferred to a later release, and what to recheck once real translations are in. Where this README and `Design reference.md` disagree, `Design reference.md` wins.

| File | What it covers |
|---|---|
| [`Design reference.md`](Design%20reference.md) | Reference per screen, decisions, code changes, deferred items. Read this first. |
| [`Uvalu.dc.html`](Uvalu.dc.html) | Main app: Dashboard, Screener, Watchlist, Portfolio (overview, open and closed positions, Dividends, Cash), Risk, Analysis, Settings (incl. Language & region and Account security), Methodology, Legal, About, sign-in and invitation sign-up, version notices and states. Cash Management and Dividend Management are merged into this file. Tweaks switch states (environment, update notice, new build, error and maintenance, data states, founder holds). |
| [`Uvalu Admin.dc.html`](Uvalu%20Admin.dc.html) | Admin portal: Users, Data feeds, System, Backups & restore |
| [`Uvalu Auth.dc.html`](Uvalu%20Auth.dc.html) | Authentication: sign in/failure/throttle states, invite acceptance, password recovery, TOTP challenge, backup-code and passkey dialogs, Admin → Users/Security. Settings → Account security now lives in `Uvalu.dc.html`. From a separate Claude Design handoff session (not the `edc1baa4-ffbe-46e8-828c-a545703d9112` project), built for the auth overhaul on `feature/auth-overhaul-m1`; see [`docs/archive/uvalu-auth-implementation-plan.md`](../archive/uvalu-auth-implementation-plan.md) for the original design rationale (the pre-build proposal, not a frame-by-frame mapping; the shipped implementation deviates from it in several places, e.g. the JSON user store instead of a SQL table) and [`docs/architecture.md`](../architecture.md) for how the shipped auth system actually works. |
| [`support.js`](support.js) | Runtime the `.dc.html` files depend on (`<x-dc>` template engine + `DCLogic` base class). Required for the mockups to render standalone in a browser; not meaningful as a design reference on its own. |
| [`legal-docs.js`](legal-docs.js) | The beta legal texts shown on the Legal page of `Uvalu.dc.html`. Required for that page to render. |

The separate `Uvalu Dividend Management.dc.html` and `Uvalu Cash Management.dc.html` mockups were removed; their screens are part of `Uvalu.dc.html`. Their history is in git.

`Uvalu-brand-guidelines.md` lives at [`docs/uvalu-brand-guidelines.md`](../uvalu-brand-guidelines.md)
(kept alongside the other product docs, not duplicated here) and is the same
content as the design project's `uploads/uvalu-brand-guidelines.md`. Its signal labels (BUY / MONITOR / AVOID / VETO) are out of date; the legal wording in `Design reference.md` applies.

## Deliberate deviations in the shipped app

These were decided after user review. Don't "fix" them back to an older mockup. `Uvalu.dc.html` already shows them.

**Dividends** (Sep 2026):
- No "Import from market data" button; the import runs automatically once per session.
- The log download sits next to Add dividend as "Export".
- No declaration/record-date sub-lines or "· frequency" suffix in log rows.
- An unconfirmed (auto-imported) pay date is shown in amber with a tooltip instead of "· confirm".
- The annual summary card keeps the mockup's left-hand width; its button is labelled "Export".
- No "Withholding by domicile" card.
- The Add/Edit dividend dialogs and CSV export have no declaration date, record date or frequency: the dialogs ask only ex-date and payment date, then shares / per share / foreign WH, then type.

**Cash** (23 Sep 2026):
- Buy/Sell are never blocked by an insufficient balance. The shortfall is covered by an automatic, linked top-up deposit instead of a red "blocked" state.
- The `§` spec-note blocks from the handoff were annotations and are not rendered (they are removed from the mockups).

`Design reference.md` lists the later decisions (signals, colours, Settings order, labels, removals).

## How to use this

- Open a `.dc.html` file directly in a browser to see the intended design.
  It's a self-contained interactive mockup, not just a static screenshot. Keep
  `support.js` and `legal-docs.js` next to it.
- Treat these files as **read-only reference**, not code to import into the
  Streamlit app. They define CSS tokens (`--bg`, `--teal`, `--mint`, the text
  tokens `--mint-txt`, `--amber-txt`, `--teal-txt`, spacing, radii, etc.),
  layout, and copy that `uvalu/styles.py`, `uvalu/shell.py` and
  `uvalu/components.py` should match. The app is native Streamlit, not a port
  of this HTML/JS.
- When the mockup changes upstream (new frame, spacing tweak, copy change),
  re-pull the changed file(s) from the Claude Design project and overwrite the
  local copy, together with `Design reference.md`, so this directory keeps
  tracking the live design rather than drifting into its own fork.

## Design System artifact

A [Claude Design System artifact](https://claude.ai/artifact/DL2qE8DNyMZ6R7Exacv5wQ) built
from the files in this directory plus `docs/uvalu-brand-guidelines.md`: tokens (colour,
type, spacing, radius, shadow, border), and live component previews for the main app,
Admin portal and auth flow. It's derived from these files, not a second source of truth:
if the mockups or brand guidelines change, re-derive the affected tokens/components there
rather than editing it independently. It predates the October 2026 colour and label
changes, so check it against `Design reference.md`. Private to the Claude account that
created it; not checked into the repo since its value (live previews, the interactive
index) only works on claude.ai.

## Screenshots

The design project no longer keeps PNG screenshots. The `.dc.html` files fully
specify the visuals and are more useful (interactive, diffable, greppable for
exact hex/spacing values).
