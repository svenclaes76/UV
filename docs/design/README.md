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
| [`support.js`](support.js) | Runtime the two `.dc.html` files depend on (`<x-dc>` template engine + `DCLogic` base class). Required for the mockups to render standalone in a browser; not meaningful as a design reference on its own. |

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

## Screenshots

The design project also has PNG screenshots of each frame under
`screenshots/` (e.g. `01-analysis.png`, `01-risk.png`, `portfolio.png`).
They weren't pulled into the repo since the `.dc.html` files fully specify
the same visuals and are more useful (interactive, diffable, greppable for
exact hex/spacing values). Pull individual screenshots from the design
project on demand if a quick visual reference is more convenient than
rendering the HTML.
