# Implementation plan: replace the old logo with the Consensus logo

11 October 2026. Prepared on `feature/design-reference-round-3` at `6ee2369`, after logo prompt 1 (`3cd4b8b`). No code was changed for this plan.

**Sources of truth, in order:** `docs/design/logo-consensus-spec.md`; the lockups in the mockups (`Uvalu.dc.html` top bar and sign-in panel, `Uvalu Admin.dc.html` sidebar, `Uvalu Auth.dc.html` sign-in panel and admin frame); the generated files in `assets/logo/` (built by `tools/build_logo.py`).

**Decided (11 October 2026, Sven Claes):**
- **Wordmark typeface:** outlined Inter 500, as in `assets/logo/`. The app never sets the wordmark as live text and never loads Inter.
- **Light theme:** the top bar shows the **light lockup in the light theme** (navy rings and wordmark, teal lens and final u) and the dark lockup in the dark theme. The Admin portal and the sign-in panel are dark-only surfaces and always show the dark lockup.

## 1. Where the old logo is used

| # | File and function | What it does now | What it should do |
| --- | --- | --- | --- |
| U1 | `app.py`, `st.set_page_config(page_icon="favicon.svg")` (line 38) | Browser tab icon from the root `favicon.svg`: the old V-stroke mark (white V, mint base circle and ring, navy tile, radius 16) | `page_icon="assets/logo/uvalu-mark-small-32.png"` (small mark, the spec's rule for 32px and below) |
| U2 | `favicon.svg` (repo root) | Old mark, only read by U1 | Delete; history keeps it |
| U3 | `uvalu/shell.py` `render_topbar`, `col_logo` (lines ~361–368) | Live-text wordmark: 22px/500, −0.03em, final u in `var(--logo-accent)`; "value engine" tag 10px uppercase `--muted`, gap 9px, `align-items:baseline` | Inline SVG lockup, mark height 26px, `align-items:center`, gap 13px to the tag; colours follow the theme (light lockup in light, dark in dark) |
| U4 | `uvalu/shell.py` `_topbar_css` (line ~258), `.uv-logo-tag` | Hides the tag below 1100px | Keep (the lockup is 86px wide, the logo column 190px) |
| U5 | `uvalu/authgate.py` `_render_brand_panel` (lines ~241–246, inside `.uv-login-brand`; called by the sign-in, lock-out, invitation, reset and two-factor screens) | Live-text wordmark 24px/500 `#F5F7FA`, final u `var(--mint)`; tag 10px `rgba(245,247,250,0.4)`, gap 9px | Dark lockup, mark height 48px, gap 23px to the tag, `align-items:center` |
| U6 | `uvalu/pages_/admin.py` sidebar header (lines ~1571–1579) | Live-text wordmark 20px, final u `var(--link)`; "admin" tag 9.5px, gap 9px, padding-left 8px | Dark lockup, mark height 24px, gap 12px to the tag; padding unchanged |
| U7 | `uvalu/styles.py` lines ~1948–1955 | `.uv-logo`, `.uv-logo-wordmark`, `.uv-logo-accent` (`#1A8C6E`), `.uv-logo-sub`: the old sidebar logo, used nowhere now | Delete |
| U8 | `uvalu/styles.py` `:root` / `[data-theme="light"]` (lines ~45–59) | `--logo-accent` (`#1DD6A4` dark, `#1A8C6E` light) with a comment naming the wordmark's final u | Keep `--logo-accent` (lens and final u); add `--logo-ring` (`#FFFFFF` dark, `#0D1F3C` light), as in `Uvalu.dc.html`; update the comment |
| U9 | `docs/uvalu-brand-guidelines.md` §3 Logo (Wordmark, Logo mark, Variants, Don'ts) and §10 App icon (Specifications, Construction) | V-stroke mark, base circle and enclosing ring; "until the master exists, the app sets it in the primary type stack"; favicon "32×32px ICO / SVG"; icon "~55% of canvas width"; v1.3 code follow-up "outlined wordmark SVG" | Rewrite from the spec (step L4); version 1.4 |
| U10 | `.streamlit/config.toml` `enableStaticServing = true`; `static/` | Serves only `static/version.json` (public, no sign-in); `.gitignore` ignores `static/version.json` | No change (see L1: the favicon goes through `page_icon`, the lockups are inline SVG) |
| U11 | `docs/version-management-plan.md` line 324 | "check that `favicon.svg` etc. don't need to" go in `static/` | No change (historical plan; the answer stays "no") |
| U12 | `docs/design/uvalu-brand-guidelines.md` | Older copy of the guidelines with the V-stroke text | No change: superseded by `docs/uvalu-brand-guidelines.md` (`docs/design/README.md` says so); leave as history |
| U13 | Catalogues: `msgid "value engine"` (context "next to the uvalu logo"), "admin" is not translated | Tag texts beside the wordmark | Unchanged; the logo itself has no translatable text |

Checked and not affected: the tests (no test asserts the old wordmark markup or `favicon.svg`; `tests/test_version_ui.py` only checks `enableStaticServing`), the Material-icon inline SVGs in `authgate.py` (line 654) and `admin.py` (line 152), `README.md`, `docs/architecture.md`.

## 2. Decisions behind the steps

**`st.logo` or the custom top bar?** The custom top bar. The app already draws its own sticky top bar (`shell.render_topbar`) and leaves Streamlit's header empty and transparent, with no sidebar navigation; `st.logo` puts the image in Streamlit's own header/sidebar slot, which this app doesn't use, and can't sit next to the "value engine" tag at the mockup's sizes. The Admin portal and sign-in panel are custom markup too.

**How the lockup reaches the page.** Inline SVG markup in `st.markdown`, built by a small helper from the generated files:
- `uvalu/logo.py` reads `assets/logo/uvalu-lockup-dark.svg` once (cached), keeps its `viewBox` and paths, and returns `<svg role="img" aria-label="Uvalu" height="{h}" width="{w}" …>` at a given mark height (width = height × viewBox width ÷ 64).
- **Top bar (theme-following):** the helper swaps the two fills for tokens: `#FFFFFF` → `var(--logo-ring)`, `#1DD6A4` → `var(--logo-accent)`. With `--logo-ring` `#0D1F3C` and `--logo-accent` `#1A8C6E` in `[data-theme="light"]`, the rendered top bar is exactly `uvalu-lockup-light.svg`; in dark it is exactly `uvalu-lockup-dark.svg` (same paths, same colours; a test checks this). The colour follows the theme switch with no rerun, like the rest of the app.
- **Admin and sign-in (dark only):** the dark lockup's literal colours.
- Why not `<img src>` from `static/`: everything in `static/` is public and the README promises only `version.json` lives there; `<img>` can't switch colour by token; and a data-URI image per rerun is heavier than ~2 KB of inline paths.
- Why not `st.image`: it can't sit inline next to the tag in one flex row.

**Favicon.** `page_icon` with a PNG path: Streamlit reads the file and serves it as the tab icon itself, so no static serving or `<head>` tag is needed. The other rasters (`apple-touch-icon.png`, `icon-192/512.png`, `og-image.png`, `favicon.ico`) have no use in the Streamlit app (no custom `<head>`, no manifest); they stay in `assets/logo/` for a future landing page or docs site. `.gitignore`: no change.

**`aria-label`.** "Uvalu": the screen reader reads the name as it is written in running text (brand §3/§9). It is the brand name, so it is not translated (`locales/README.md`: brand and provider names stay) and needs no catalogue entry. The generated files say `aria-label="uvalu"`; L1 changes `tools/build_logo.py` to "Uvalu" and regenerates, so files and app agree.

## 3. Steps

One pull request each, in this order.

### L1 · Favicon from the small mark

- **Why:** spec, Usage rules ("Browser favicon: small mark, dark tile, 16 and 32 px") and Implementation in the app, step 2.
- **Files and functions:** `app.py` (`st.set_page_config`); delete `favicon.svg`; `tools/build_logo.py` (`_svg` default label "Uvalu"); regenerate `assets/logo/`; `tests/test_logo_assets.py`.
- **Changes:** `page_icon="assets/logo/uvalu-mark-small-32.png"`; remove the root `favicon.svg`; label "uvalu" → "Uvalu" in the builder, rerun `python tools/build_logo.py`.
- **Strings:** none.
- **Tests:** new test: `app.py` sets `page_icon` to an existing file in `assets/logo/` and `favicon.svg` is gone; `test_svgs_are_up_to_date_with_the_builder` keeps the regenerated files honest; add an assertion that every SVG has `aria-label="Uvalu"`.
- **How to verify:** start the app (`run_app.py` and the dev entry) and check the tab icon in Chrome with the browser in light and in dark mode (the navy tile reads on both); also check that the sign-in screen shows it (the page config runs before the auth wall). This closes the spec's last open item ("check the favicon on a real browser tab").
- **Size:** S. **Depends on:** —

### L2 · Logo helper and the top-bar lockup (theme-following)

- **Why:** spec, Usage rules ("Sidebar or header logo: main mark in lockup, dark or light by theme, mark height 24–32 px"); decision "light lockup in the light theme"; `Uvalu.dc.html` top bar (`<svg height="26" width="86" viewBox="0 0 212 64">`, gap 13px, tag 10px uppercase `--muted`).
- **Files and functions:** new `uvalu/logo.py` (`lockup_svg(height, *, theme_tokens: bool) -> str`, file read cached with `functools.lru_cache`); `uvalu/shell.py` `render_topbar` (`col_logo` markup); `uvalu/styles.py` (`--logo-ring` in `:root` and `[data-theme="light"]`, comment on the logo tokens); `tests/test_logo.py` (new), `tests/test_shell.py`, `tests/test_styles.py` (token list).
- **Changes:**
  - `lockup_svg(26, theme_tokens=True)`: the dark lockup's paths with fills mapped to `var(--logo-ring)` / `var(--logo-accent)`, `height="26"`, width from the viewBox (≈ 85.5px), `style="display:block;flex:none;"`.
  - Top-bar wrapper: `display:flex;align-items:center;gap:13px;` (was baseline / 9px); the "value engine" span keeps class `uv-logo-tag`, 10px, `letter-spacing:0.14em`, uppercase, `--muted`, nowrap.
  - Tokens: `--logo-ring:#FFFFFF` (dark), `--logo-ring:#0D1F3C` (light).
- **Strings:** none ("value engine" unchanged).
- **Risks:** the logo column is 190px (`_LOGO_PX`); 85.5 + 13 + the tag (~90px at 10px tracked uppercase) fits in English; in longer tag translations the existing `.uv-logo-tag` rule hides the tag below 1100px, and the tag already uses `nowrap`. Check de/fr at 1280px with `?lang=de`.
- **Tests:**
  - `lockup_svg` output has no `<text>`, has `role="img"` and `aria-label="Uvalu"`, height 26 and the viewBox of `uvalu-lockup-dark.svg`.
  - With the light token values substituted, the markup's fills equal `uvalu-lockup-light.svg` (`#0D1F3C` rings and wordmark, `#1A8C6E` lens and final u); with the dark values, `uvalu-lockup-dark.svg`.
  - `--logo-ring` in both theme blocks of `GLOBAL_CSS` with those values.
  - `render_topbar` renders the SVG and no `uval<span`.
- **How to verify:** 1280px in both app themes side by side with `Uvalu.dc.html` (Tweaks theme dark / light): mark 26px high, wordmark baseline and the tag centred on the bar, 13px gap, light lockup on the white bar, dark lockup on navy; theme toggle switches the colours. 920px: the tag is hidden, logo and nav fit without overlap.
- **Size:** M. **Depends on:** L1 (aria-label in the files).

### L3 · Admin sidebar and sign-in panel

- **Why:** spec, Usage rules ("Sign-in and onboarding: main mark in lockup, dark, mark height 48–64 px"); `Uvalu Admin.dc.html` sidebar (`height="24"`, gap 12px, "admin" tag 9.5px); `Uvalu.dc.html` / `Uvalu Auth.dc.html` sign-in panel (`height="48"`, gap 23px, "value engine" tag 10px `rgba(245,247,250,0.4)`).
- **Files and functions:** `uvalu/pages_/admin.py` sidebar header (`st.markdown` at ~1572); `uvalu/authgate.py` `_render_brand_panel`; `tests/test_authgate.py`, admin page test.
- **Changes:** Admin: `lockup_svg(24, theme_tokens=False)` (dark colours), wrapper `display:flex;align-items:center;gap:12px;padding-left:8px;`, tag unchanged. Sign-in: `lockup_svg(48, theme_tokens=False)`, wrapper `gap:23px;align-items:center`, tag unchanged; the panel's `position:relative;z-index:2` stays. All five sign-in-type screens call `_render_brand_panel`, so one change covers them.
- **Strings:** none.
- **Tests:** sign-in AppTest: the brand panel contains the SVG with `height="48"` and no `uval<span`; admin page AppTest: the sidebar contains the SVG with `height="24"`.
- **How to verify:** sign out (or `run_app.py`) and compare the sign-in panel with `Uvalu.dc.html` sign-in at 1280px (mark 48px, 23px gap, tag 40% white); open the lock-out and invitation states; Admin portal vs `Uvalu Admin.dc.html` (mark 24px, 12px gap, tag "ADMIN" 9.5px). Both are dark-only, so one theme.
- **Size:** S. **Depends on:** L2 (helper).

### L4 · Brand guidelines v1.4: logo and app icon

- **Why:** spec, Design system update; the v1.3 code follow-up "outlined wordmark SVG" is done.
- **Files and functions:** `docs/uvalu-brand-guidelines.md` §3 Logo, §10 App icon, Changes, version line.
- **Changes:**
  - §3: the Consensus mark and its meaning (rings = independent valuation models, lens = where they agree, the only filled shape; plain geometry, no arrows or charts); two weights (main above 32px, small at 32px and below) with the geometry table; the lockup (Inter 500 outlined, 0.875 × H, −0.03 em, 0.1875 × H gap, x-height centred, final u accented); the colour table (dark / light / monochrome, each two inks; mint never on light); clear space = height of the lowercase u; usage by size (favicon, header, sign-in, app/PWA icons, social image, print); the Don'ts from the spec; "Never redraw or recolour a mark by hand: use the files in `assets/logo/`, generated by `tools/build_logo.py`". The wordmark rule changes from "until the master exists, the app sets it in the primary type stack" to "the app uses the outlined lockup (`uvalu/logo.py`)". Add: the top bar follows the theme (light lockup on light), Admin and sign-in always dark.
  - §10: icon tiles radius 22% (14 at 64), main mark at 75% of the tile, small mark at 84% (94% at 16px); favicon = small mark, ICO 16/32/48 plus the 32px PNG; app/PWA icons 180, 192, 512 (main mark tile); construction text from the spec (replaces the V-stroke text and "~55% of canvas width").
  - Changes: **v1.4 — 11 Oct 2026**: Consensus logo replaces the V-stroke mark; outlined wordmark; files and build script; v1.3's wordmark follow-up done. Version line → 1.4.
- **Strings:** none.
- **Tests:** none (doc).
- **How to verify:** read-through against the spec; every number in §3/§10 matches `tools/build_logo.py`.
- **Size:** S. **Depends on:** L1–L3 (it describes the app as built).

### L5 · Clean-up

- **Why:** spec, "Search the codebase for the old mark … and replace every hit"; old files kept in git history only.
- **Files and functions:** `uvalu/styles.py` (delete `.uv-logo`, `.uv-logo-wordmark`, `.uv-logo-accent`, `.uv-logo-sub` and their comment header if nothing else under it is used); `docs/open-items.md` (close D1).
- **Changes:** as above; grep once more for `uval<span`, `V-stroke`, `favicon.svg` and `.uv-logo-` (except `.uv-logo-tag`) and expect no hits outside `docs/design/` history files and `docs/archive/`.
- **Strings:** none.
- **Tests:** `tests/test_styles.py`: `GLOBAL_CSS` has no `.uv-logo-wordmark`; a repo grep test that no `uvalu/*.py` contains `uval<span`.
- **How to verify:** full test suite; one screen pass (Dashboard, Settings, Admin, sign-in) in both themes to see nothing lost its styling.
- **Size:** S. **Depends on:** L2, L3.

**Total:** 5 steps, 4 small and 1 medium, about 8 hours.

## 4. Open decisions

From the spec's Open decisions:
- **Wordmark typeface:** decided, outlined Inter 500.
- **Light-theme lockup:** decided, light lockup in the light theme (top bar); Admin and sign-in stay dark.
- **Final export check:** still open. The files exist; the favicon still has to be checked on a real browser tab in light and dark browser themes (done in L1's verification).

## 5. Release notes draft

`CHANGELOG.md`:

```markdown
### Changed

- **New logo.** The Consensus mark (two rings for independent valuation
  models, a filled lens where they agree) with the outlined "uvalu" wordmark
  replaces the V-stroke mark in the top bar, the Admin portal, the sign-in
  screen and the browser tab. The top bar uses the light lockup in the light
  theme and the dark lockup in the dark theme. The files live in
  `assets/logo/` and are generated by `tools/build_logo.py`; brand guidelines
  v1.4 describe them.

### Removed

- The old `favicon.svg` and the unused `.uv-logo-*` styles.
```

`RELEASE_NOTES.md` (subscribers): under **Improved**, "**A new Uvalu logo**: two rings for independent valuation models, and the lens where they agree — the idea behind every fair value you see."
