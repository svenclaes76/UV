"""Global CSS injected once per run into the main app frame."""
import streamlit as st

GLOBAL_CSS = """
  /* ── Brand tokens ────────────────────────────────────────────────────────── */
  :root {
    --uv-mint:        #1DD6A4;
    --uv-navy:        #0D1F3C;
    --uv-pos-bg:      #E8F5F0;
    --uv-pos-txt:     #0F6E56;
    --uv-cau-bg:      #FDF0E8;
    --uv-cau-txt:     #854F0B;
    --uv-neg-bg:      #FCEAEA;
    --uv-neg-txt:     #A32D2D;
    --uv-muted:       #5F5E5A;
    --uv-track:       #EEF1F5;
    --uv-mono:        "SF Mono","Fira Code","Cascadia Code",ui-monospace,Menlo,monospace;
  }

  /* Bar tracks (fair-value ladders, score/sub-score bars, weights): the
     light-surface #EEF1F5 above was used in dark theme too, which made the
     empty part of every bar the brightest thing on the navy screen. Only the
     fill carries colour; the track is a faint tint (visual review G3). */
  html:not([data-theme="light"]) { --uv-track: rgba(245,247,250,0.10); }

  /* ── Design-mockup tokens (dark-navy top bar/shell + card surfaces) ────────
     Namespaced separately from the --uv-* set above so existing components
     keep working unchanged while new raw-HTML screens (top bar, Dashboard,
     Admin portal, ...) adopt these directly, matching Uvalu.dc.html /
     Uvalu Admin.dc.html. [data-theme="light"] is set on <html> by
     uvalu/shell.py from Streamlit's own active theme (theme_colors()), the
     same source Plotly charts already used — not a separate per-user
     setting, so native widgets and these tokens always agree. */
  :root {
    --bg:#0A1730; --panel:#0E2143; --panel-2:#0B1D3D; --soft:rgba(29,214,164,0.05);
    --line:rgba(255,255,255,0.08); --line-2:rgba(255,255,255,0.05);
    --text:#F5F7FA; --muted:rgba(245,247,250,0.55); --faint:rgba(245,247,250,0.30);
    --teal:#1A8C6E; --mint:#1DD6A4; --navy:#0D1F3C;
    /* AC5: fill behind white button text. Signal Teal is 4.2:1 with white;
       this is the light --link teal, 5.3:1, and 3:1+ against both themes' backgrounds. */
    --primary-fill:#167A60; --primary-fill-hover:#12664F;
    --up-bg:rgba(29,214,164,0.14); --up-txt:#1DD6A4;
    --down-bg:rgba(163,45,45,0.26); --down-txt:#F0A6A6;
    --amber-bg:rgba(214,158,29,0.16); --amber-txt:#E0B94D; --amber-fill:#C98A3A;
    --grid:rgba(255,255,255,0.06); --axis:rgba(245,247,250,0.5);
    --tile:#0B1D3D; --shadow:0 1px 2px rgba(0,0,0,0.4);
    /* Brand v1.3: link text (Signal Teal is 4.2:1 on white, too low for
       small text), the badge fills that have no semantic token of their own,
       and the top-bar lockup's two inks (uvalu/logo.py): --logo-ring for the
       rings and wordmark, --logo-accent for the lens and the final "u". */
    --link:#3FBF98; --logo-accent:#1DD6A4; --logo-ring:#FFFFFF;
    --veto-bg:#1E2D4A; --veto-line:rgba(245,247,250,0.18); --nosig-bg:rgba(245,247,250,0.07);
  }
  [data-theme="light"] {
    --bg:#EAEEF3; --panel:#FFFFFF; --panel-2:#F5F7FA; --soft:rgba(29,214,164,0.055);
    --line:rgba(13,31,60,0.10); --line-2:rgba(13,31,60,0.06);
    --text:#0D1F3C; --muted:#5F5E5A; --faint:rgba(13,31,60,0.38);
    --up-bg:rgba(15,110,86,0.11); --up-txt:#0F6E56;
    --down-bg:rgba(163,45,45,0.11); --down-txt:#A32D2D;
    --amber-bg:#FDF0E8; --amber-txt:#854F0B; --amber-fill:#C98A3A;
    --grid:rgba(13,31,60,0.08); --axis:#5F5E5A;
    --tile:#F5F7FA; --shadow:0 1px 3px rgba(13,31,60,0.08);
    --link:#167A60; --logo-accent:#1A8C6E; --logo-ring:#0D1F3C;
    --veto-bg:#0D1F3C; --veto-line:transparent; --nosig-bg:rgba(128,128,128,0.15);
  }

  /* Keyboard focus (brand §7): 2px ring, teal on light, mint on dark. Only
     :focus-visible, so a mouse click doesn't draw it. */
  :focus-visible { outline: 2px solid var(--mint) !important; outline-offset: 2px !important; }
  [data-theme="light"] :focus-visible { outline-color: var(--teal) !important; }
  /* No motion for people who ask for none (brand §7 Loading). */
  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { animation: none !important; transition: none !important; }
  }

  /* ── Buttons and segmented controls: one label size (design reference,
     buttons 12.5px, primary 500, 16px icon with a 7px gap). Streamlit 1.60
     puts the label in its own <p> with a 14px size and its own colour, so a
     size or colour set on a button never reached the text. The label now
     inherits from its button; :where() keeps these rules at the lowest
     specificity, so every keyed override below (and its own `button p`
     rules) still wins. */
  :where(button[data-testid^="stBaseButton-"], button[data-testid="stPopoverButton"]) { font-size: 12.5px !important; }
  :where(button[data-testid="stBaseButton-primary"],
         button[data-testid="stBaseButton-secondary"],
         button[data-testid="stPopoverButton"],
         button[data-testid="stBaseButton-primaryFormSubmit"],
         button[data-testid="stBaseButton-secondaryFormSubmit"]) {
    min-height: 34px !important; padding: 6px 13px !important; gap: 7px !important;
  }
  :where(button[data-testid="stBaseButton-tertiary"]) { min-height: 34px !important; }
  :where(button[data-testid="stBaseButton-primary"],
         button[data-testid="stBaseButton-primaryFormSubmit"]) { font-weight: 500 !important; }
  /* AC5 (docs/accessibility-review.md): primary buttons are filled with
     --primary-fill so the white label reaches 4.5:1. Keyed overrides (the
     red danger button) are more specific and still win. */
  button[data-testid="stBaseButton-primary"],
  button[data-testid="stBaseButton-primaryFormSubmit"] {
    background-color: var(--primary-fill) !important; border-color: var(--primary-fill) !important;
    color: #fff !important;
  }
  button[data-testid="stBaseButton-primary"]:hover:not(:disabled),
  button[data-testid="stBaseButton-primaryFormSubmit"]:hover:not(:disabled) {
    background-color: var(--primary-fill-hover) !important; border-color: var(--primary-fill-hover) !important;
  }
  :where(button[data-testid^="stBaseButton-"], button[data-testid="stPopoverButton"], button[data-variant]) :where([data-testid="stMarkdownContainer"], [data-testid="stMarkdownContainer"] p) {
    font-size: inherit !important; font-weight: inherit !important; color: inherit !important;
    font-family: inherit !important;
  }
  :where(button[data-testid^="stBaseButton-"]) :where([data-testid="stIconMaterial"]) { font-size: 16px !important; }
  /* Outline buttons read --muted and turn --text on hover (the mockups'
     Export CSV, Deposit, Save … buttons). Streamlit colours the button's
     inner wrapper itself, so its descendants inherit explicitly. */
  :where(button[data-testid="stBaseButton-secondary"],
         button[data-testid="stBaseButton-secondaryFormSubmit"], button[data-testid="stPopoverButton"]) { color: var(--muted) !important; }
  :where(button[data-testid="stBaseButton-secondary"],
         button[data-testid="stBaseButton-secondaryFormSubmit"], button[data-testid="stPopoverButton"]):where(:hover:not(:disabled)) {
    color: var(--text) !important; border-color: var(--teal) !important;
  }
  :where(button[data-testid="stBaseButton-secondary"],
         button[data-testid="stBaseButton-secondaryFormSubmit"], button[data-testid="stPopoverButton"]) :where(*) { color: inherit !important; }

  /* ── Subheader spacing ───────────────────────────────────────────────────── */
  [data-testid="stHeadingWithActionElements"] { margin-top: 0.5rem !important; margin-bottom: 0.15rem !important; padding: 0 !important; }
  [data-testid="stHeadingWithActionElements"] h3 { margin: 0 !important; padding: 0 !important; font-size: 1.1rem !important; line-height: 1.3 !important; }

  /* ── Page transitions ────────────────────────────────────────────────────── */
  .block-container { animation: uvFadeIn 0.18s ease; }
  @keyframes uvFadeIn { from { opacity: 0; } to { opacity: 1; } }

  /* ── Loading skeletons (components.loading_skeleton_html, skeleton_*_html)
     — shown while a cold fundamentals cache is still being fetched, so a
     page paints its shape immediately instead of a bare "no data" line.
     Matches the "Loading Patterns" design concept. ────────────────────────── */
  @keyframes uvShimmer { 0% { background-position: -420px 0; } 100% { background-position: 420px 0; } }
  .uv-skel-bar {
    height: 13px; border-radius: 6px;
    background: var(--line-2);
    background-image: linear-gradient(90deg, var(--line-2) 0px, var(--line) 60px, var(--line-2) 120px);
    background-size: 420px 100%;
    animation: uvShimmer 1.25s ease-in-out infinite;
  }
  /* Spinner ring (components.spinner_html/refresh_spinner_inline_html) and the
     top-of-viewport refresh sweep (components.refresh_top_bar_html) — the
     "already showing real data, just re-fetching" half of the same design,
     as opposed to the skeleton bars above (nothing to show yet). uvRing also
     drives the topbar's price-freshness dot (uvalu/shell.py) when the feed
     is genuinely live, not delayed/stale/closed. */
  @keyframes uvSpin { to { transform: rotate(360deg); } }
  @keyframes uvFadeOutLate { 0%, 80% { opacity: 1; } 100% { opacity: 0; } }
  .uv-saved-note { animation: uvFadeOutLate 2.5s ease forwards; }
  .st-key-set_i18n_currency_default button { min-height: 0 !important; padding: 0 !important; }
  .st-key-set_i18n_currency_default button p { font-size: 11px !important; color: var(--link) !important; }
  @keyframes uvRing { 0% { box-shadow: 0 0 0 0 rgba(29,214,164,0.45); } 100% { box-shadow: 0 0 0 8px rgba(29,214,164,0); } }
  @keyframes uvBar { 0% { left: -30%; } 100% { left: 110%; } }
  /* components.skeleton_rows()'s hairline row divider — a native st.columns()
     row can't take a border via raw HTML the way skeleton_holdings_row_html's
     CSS-grid string can, so each row is its own st-key-uv_skel_row_<caller>_N
     container styled here instead (same idiom as stock_row's own
     st-key-scr_row_ rule). Matches every real row class's own treatment
     (scr_row_/wl_row_/pf_open_row_/etc.) property-for-property — including
     the same margin-top cancellation of Streamlit's default inter-sibling
     gap — so a skeleton row list sits exactly where its real rows will. */
  [class*="st-key-uv_skel_row_"] {
    border-bottom: 0.5px solid var(--line-2) !important; padding: 12px 20px !important;
    margin-top: -16px !important; min-height: 67px !important;
  }

  /* ── Chrome cleanup ──────────────────────────────────────────────────────── */
  [data-testid="stDecoration"] { display: none !important; }
  header[data-testid="stHeader"] { background: transparent !important; border-bottom: none !important; }

  /* ── Layout ──────────────────────────────────────────────────────────────── */
  .block-container {
    padding-top: 0 !important; padding-bottom: 0.5rem !important; max-width: 100% !important;
    padding-left: 1.5rem !important; padding-right: 1.5rem !important;
  }
  /* Brand §7: 18px between a page's sections (Streamlit's default is 16px). */
  .block-container > [data-testid="stVerticalBlock"] { gap: var(--uv-section-gap) !important; }
  /* AC1: the page body sits in app.py's uv_main container (role="main"),
     one level down; same gap between its sections. */
  .block-container .st-key-uv_main { gap: var(--uv-section-gap) !important; }
  /* AC1: "Skip to content", the first focusable element (uvalu/a11y.py);
     off-screen until it has keyboard focus. */
  .uv-skip {
    position: fixed; left: 16px; top: -60px; z-index: 1000000;
    padding: 8px 14px; border-radius: 6px; border: 0.5px solid var(--line);
    background: var(--panel); color: var(--link); font-size: 13px; font-weight: 500;
    text-decoration: none;
  }
  .uv-skip:focus { top: 12px; outline: 2px solid var(--link); outline-offset: 2px; }

  /* ── Invisible helper elements (localStorage-sync iframes, theme/density
     scripts) render nothing but still occupy a full row-gap in Streamlit's
     vertical block — collapse them out of flow so they don't push visible
     content (esp. the sticky top bar, uvalu/shell.py) down the page. */
  [class*="st-key-uv_hidden_util"] {
    position: absolute !important; width: 0 !important; height: 0 !important;
    overflow: hidden !important; padding: 0 !important; margin: 0 !important;
  }
  /* Streamlit wraps every st.container() in its own flex-item div (a
     "stLayoutWrapper") one level up from the st-key-* class above; that
     wrapper still counts as a flex item and eats a row-gap even though its
     (now absolutely-positioned) child has collapsed to zero size. Removing
     it from the box tree entirely is what actually closes the gap. */
  div:has(> [class*="st-key-uv_hidden_util"]) { display: contents !important; }

  /* ── Mockup canvas background — every page now sits on --bg, matching the
     top bar (uvalu/shell.py) and the raw-HTML mockup-token cards each screen
     is adopting (Dashboard first, Phase 3.1) ──────────────────────────────── */
  section[data-testid="stMain"] { background: var(--bg) !important; }

  /* ── Dashboard Holdings card — one seamless panel (title+description+
     legend header, column-header row, then flat divider-separated rows)
     matching Uvalu.dc.html's "Holdings · price vs fair value" table exactly
     (overflow:hidden, no outer padding — each inner section owns its own
     padding instead). Deliberately NOT part of the st-key-db_card_ shared
     substring rule below since that one applies a uniform 18px padding,
     which this card's row-divider layout doesn't want. */
  .st-key-db_holdings_card {
    background: var(--panel) !important; border-color: var(--line) !important;
    border-radius: 12px !important; box-shadow: var(--shadow) !important;
    overflow: hidden !important; padding: 0 !important;
  }
  .st-key-db_holdings_header {
    padding: 16px 20px 14px !important; border-bottom: 0.5px solid var(--line-2) !important;
  }
  .st-key-db_holdings_colheader {
    padding: 7px 20px !important; border-bottom: 0.5px solid var(--line-2) !important;
    /* Same Streamlit height-underestimation as the db_hold_ rows below (see
       that rule's comment) — the header's own markdown grid measured
       shorter than its real content, so once row0 was pulled flush against
       it (0px gap, by design), row0's divider visibly crossed through the
       header's own overflowing label text. min-height stops the box from
       under-reporting. Tightened to 30px (from 34px) to match the same
       target used for Portfolio's pf_col_header — 7px 20px padding + this
       row's ~16px label content lands there. */
    min-height: 30px !important;
    /* This colheader is a SEPARATE sibling st.container() from
       db_holdings_header right above it (the title+legend row) — same
       "second bordered/padded block stacks the default ~16px gap on top of
       its own box" issue already fixed for Portfolio's pf_col_header_open_ov
       (confirmed there via getBoundingClientRect: 16px dead gap sitting
       above an otherwise-correct 30px header box, making the whole header
       area read as ~46px). Cancel it here too so the header reads as a
       clean 30px instead of ~46px. */
    margin-top: -16px !important;
  }
  [class*="st-key-db_hold_"] {
    position: relative !important; padding: 12px 20px !important;
    border-bottom: 0.5px solid var(--line-2) !important;
    border-radius: 0 !important; background: transparent !important;
    /* Each row is its own st.container(), and Streamlit puts a default
       ~16px gap between every sibling in a vertical block — so on top of
       each row's own divider (border-bottom above), there was a visible
       16px dead strip both above the column header's first row and between
       every consecutive pair of rows. The mockup has rows flush against
       each other, separated only by that divider line, so cancel the gap
       directly with a negative top margin (confirmed live: no wrapper/
       display:contents trick needed here, a plain margin on the row's own
       keyed element closes the gap to exactly 0px). */
    margin-top: -16px !important;
    /* Each row's content is one raw CSS Grid built by components.py's
       holdings_row_html() (Uvalu.dc.html's fixed-px grid-template-columns,
       which st.columns()'s ratio-only widths can't replicate), rendered via
       a single st.markdown() call. Streamlit's frontend reliably
       under-estimates that markdown element's own height for layout
       purposes — this specific 43px-tall grid consistently sized as ~27px
       internally, immune to align-items/display:contents overrides
       anywhere in the wrapper chain, whether the source HTML was written
       single- or multi-line, and whether it shared the row with a real
       st.button or not (ruling out the button-column split, unequal-height
       centering, and markdown-newline-counting as the cause — this is a
       Streamlit-internal estimate CSS can't correct at its source). A
       plain min-height floor on the row itself is the reliable fix: content
       taller than 67px still grows the row normally, it just stops
       Streamlit from rendering it 16px too short. */
    min-height: 67px !important;
    /* The row's own grid (see holdings_row_html()'s align-items:center)
       only centers cells *relative to each other* — it does nothing for
       the grid's position within this outer row box, whose height comes
       from the min-height floor above, not from the grid's own ~43px
       content height. Streamlit's default stVerticalBlock is a
       flex-direction:column container with no justify-content override,
       so the grid (the only element left in normal flow — the drawer
       button below is position:absolute) stacked at the box's top edge,
       leaving the leftover ~24px as dead space below instead of split
       above/below — reading as "content pinned high, not vertically
       centered" in the row. justify-content:center on the column's main
       axis (vertical, since flex-direction is column) fixes that; the
       align-items:center rule for st.columns()-based rows elsewhere in
       this file doesn't apply here since it targets the cross axis of a
       row-direction flex, not this column-direction one. */
    display: flex !important; flex-direction: column !important; justify-content: center !important;
  }
  /* justify-content:center above centers the row's flex CHILD box, not the
     grid's real rendered content — and that child (Streamlit's own
     `stElementContainer` wrapper around the markdown grid, the only thing
     left in normal flow once the drawer button below goes position:absolute)
     is exactly the element hit by the height-underestimate bug documented
     above: it reported 27px while the real grid inside it (overflow:visible)
     rendered its full 43px, spilling out the bottom uncounted. Centering a
     27px box in the 67px row put its top at +20px/bottom gap +4.5px once the
     real 43px content is accounted for — visually "pinned high", not fixed
     by justify-content alone. Giving the wrapper itself a min-height
     matching the grid's real content height makes the flex box and the
     visual content agree, so centering the box actually centers the
     content (confirmed live via getBoundingClientRect: top/bottom gaps both
     12px afterward, matching the row's own 12px vertical padding exactly). */
  [class*="st-key-db_hold_"] > [data-testid="stElementContainer"]:not(:has(button)) {
    min-height: 43px !important;
  }
  [class*="st-key-db_hold_"]:hover { background: var(--soft) !important; }
  /* The drawer-click button is invisible and absolutely positioned over the
     *entire* row — matching the mockup's own cursor:pointer-on-the-whole-
     row behavior (not just a small icon) — and since position:absolute
     removes it from normal flow, it can't contribute any height of its own
     to the row (which would otherwise reintroduce the same under-
     estimation problem via a second competing element). */
  [class*="st-key-db_hold_"] [data-testid="stElementContainer"]:has(button) {
    position: absolute !important; inset: 0 !important; margin: 0 !important; z-index: 1;
  }
  [class*="st-key-db_hold_"] [data-testid="stElementContainer"]:has(button) button {
    width: 100% !important; height: 100% !important; opacity: 0 !important;
    border: none !important; background: transparent !important; padding: 0 !important;
    cursor: pointer;
  }

  /* ── Dashboard section cards — chart/conviction row + bottom row (sector
     allocation, upcoming dividends, top movers), matching the mockup's
     `background:var(--panel);border:0.5px solid var(--line);border-radius:
     12px;box-shadow:var(--shadow)` card treatment. Shared substring selector
     (same convention as st-key-db_hold_ above) so one rule covers all five
     cards instead of one per key. */
  [class*="st-key-db_card_"] {
    background: var(--panel) !important; border-color: var(--line) !important;
    border-radius: 12px !important; box-shadow: var(--shadow) !important;
    padding: 18px !important;
  }
  /* Cards sharing a row (chart+conviction, sector/dividends/movers) stretch
     to the row's tallest card instead of each hugging its own content
     height — matches the mockup's align-items:stretch grid rows. Streamlit's
     st.columns() defaults vertical_alignment to "top" (align-items:
     flex-start), so this must be opted back in explicitly for these rows.
     align-items:stretch on the row only fixes the *column*'s cross-axis
     size (stColumn correctly grows to the row height) — but stColumn is
     itself a column-direction flex container, so its own children's HEIGHT
     is the main axis, controlled by flex-grow, not align-items. The direct
     generated wrapper around each card (Streamlit's unstable-classed
     "stLayoutWrapper" div) defaults to flex:0 1 auto (no grow), so it still
     shrinks to content height even though its column parent is tall enough
     — must opt that wrapper into flex-grow too. Also pins the horizontal
     gap between these card columns to 16px, matching the KPI row's own
     st.columns(4) default gap (that row isn't a db_card_* card row itself,
     so it never got the override below) and the page's own vertical
     rhythm between card rows (see db_gap_N below) — confirmed live as the
     preferred spacing in both directions. st.columns' own gap= param only
     accepts size keywords (xxsmall..xxlarge), not a raw px value, hence
     the override here. */
  [data-testid="stHorizontalBlock"]:has([class*="st-key-db_card_"]) {
    gap: 16px !important;
  }
  [class*="st-key-db_card_"] { width: 100% !important; }
  /* Both card rows stretch to a shared row height (the conviction card's
     beta/volatility footer relies on that via the margin-top:auto rule
     below). The bottom row (sector allocation/upcoming dividends/top
     movers) used to size each card to its content because the old
     dividends/movers lists were much shorter than the donut; with the
     design reference v1.3 rows (five dividends, six movers, a 132px donut)
     the three are close in height and the mockup stretches them. */
  [data-testid="stHorizontalBlock"]:has([class*="st-key-db_card_chart"]),
  [data-testid="stHorizontalBlock"]:has([class*="st-key-db_card_sector"]) {
    align-items: stretch !important;
  }
  [data-testid="stLayoutWrapper"]:has(> [class*="st-key-db_card_chart"]),
  [data-testid="stLayoutWrapper"]:has(> [class*="st-key-db_card_conviction"]),
  [data-testid="stLayoutWrapper"]:has(> .st-key-db_card_sector),
  [data-testid="stLayoutWrapper"]:has(> .st-key-db_card_dividends),
  [data-testid="stLayoutWrapper"]:has(> .st-key-db_card_movers) {
    flex: 1 1 auto !important;
  }
  .st-key-db_card_chart, .st-key-db_card_conviction,
  .st-key-db_card_sector, .st-key-db_card_dividends, .st-key-db_card_movers { flex: 1 1 auto !important; }
  /* Top movers rows: 8px rows with --line-2 dividers; the whole row opens
     the drawer through an invisible button laid over it (as db_hold_). */
  [class*="st-key-db_mover_"] {
    position: relative !important; padding: 8px 0 !important; margin-top: -16px !important;
    border-bottom: 0.5px solid var(--line-2) !important; min-height: 39px !important;
    display: flex !important; flex-direction: column !important; justify-content: center !important;
  }
  .st-key-db_mover_0 { margin-top: 0 !important; }
  [class*="st-key-db_mover_"]:last-child { border-bottom: none !important; }
  [class*="st-key-db_mover_"]:hover { background: var(--soft) !important; }
  [class*="st-key-db_mover_"] [data-testid="stMarkdownContainer"] { margin: 0 !important; }
  [class*="st-key-db_mover_"] [data-testid="stElementContainer"]:has(button) {
    position: absolute !important; inset: 0 !important; margin: 0 !important; z-index: 1;
  }
  [class*="st-key-db_mover_"] [data-testid="stElementContainer"]:has(button) button {
    width: 100% !important; height: 100% !important; opacity: 0 !important;
    border: none !important; background: transparent !important; padding: 0 !important; cursor: pointer;
  }

  /* ── Dashboard "Conviction & risk" card — "Full analysis →" as a plain
     teal text link, matching Uvalu.dc.html's `<div style="color:var(--teal);
     cursor:pointer">Full analysis →</div>` (no button chrome) instead of a
     boxed tertiary button. */
  .st-key-db_conv_full_analysis button {
    background: transparent !important; border: none !important; box-shadow: none !important;
    color: var(--link) !important; font-size: 11px !important; padding: 0 !important;
    min-height: unset !important; height: auto !important; text-decoration: none !important;
    justify-content: flex-end !important;
  }
  .st-key-db_conv_full_analysis button:hover { color: var(--text) !important; }
  /* One line in every language ("Vollständige Analyse →"): the link's
     column sizes to the link, the title takes the rest. */
  [data-testid="stColumn"]:has(> [data-testid="stVerticalBlock"] > .st-key-db_conv_full_analysis) {
    flex: 0 0 auto !important; width: auto !important;
  }
  .st-key-db_conv_full_analysis button p { white-space: nowrap !important; }
  /* Beta/Volatility/Max-drawdown row pinned to the card's bottom edge —
     matches the mockup's `margin-top:auto` on this section (Uvalu.dc.html
     ~line 407), which keeps it flush with the card's bottom even when the
     row's grid partner (the taller value-chart card, stretched to match via
     align-items:stretch above) leaves extra space above it. Targets the
     generated wrapper div one level up (Streamlit's own flex item in this
     container's flex column), not the st-key-* element itself — same
     "wrapper is the real flex item" pattern as [[uvalu-streamlit-flex-css-gotchas]]. */
  div:has(> [class*="st-key-db_conv_metrics"]) { margin-top: auto !important; }

  /* KPI strip — Streamlit's own height estimate for a kpi_card()'s raw-HTML
     markdown under-measures its real rendered height by exactly 16px
     (confirmed live: row reported 99.5px, cards actually 115.5px tall) —
     same class of bug hit repeatedly for the Holdings rows/column header.
     With the row itself reporting short, the *next* section rendered
     flush against the overflowing cards instead of with the normal 16px
     gap. A plain min-height floor on the row is the reliable fix here too. */
  .st-key-db_kpi_row { min-height: 116px !important; }

  /* Dashboard section spacers (KPI row → chart row → Holdings → bottom
     row) — each pair of sections is separated by a 4px st.container
     spacer, but Streamlit's own default 16px block-gap applies on *both*
     sides of it too (16 + 4 + 16 = 36px total), overshooting the page's
     16px rhythm used everywhere else (KPI/card-row horizontal gaps,
     Holdings row dividers). Collapsing the spacer's own generated wrapper
     via display:contents promotes the spacer itself to be the real flex
     item, so a negative margin on it can pull the two surrounding 16px
     gaps in directly — confirmed live (getBoundingClientRect measurement)
     that -8px lands on exactly 16px. */
  div:has(> [class*="st-key-db_gap_"]) { display: contents !important; }
  [class*="st-key-db_gap_"] { margin-top: -8px !important; margin-bottom: -8px !important; }

  /* ── Dashboard chart legend row — full-width top divider above the
     Portfolio-value/Amount-invested swatches and the benchmark toggle
     chips, matching Uvalu.dc.html's legend border-top (previously only
     spanned the legend's own column, not the chip toggles beside it). */
  .st-key-db_chart_legend_row {
    border-top: 0.5px solid var(--line-2) !important;
    padding-top: 10px !important; margin-top: 6px !important;
  }

  /* ── Dashboard value-chart range control — Streamlit's native
     st.segmented_control ships as edge-to-edge buttons with no shared
     track (each button individually bordered, only the group's first/last
     corners rounded), quite different from Uvalu.dc.html's rangesArr spec
     (uvalu_dc.html ~line 2137-2138): a padded `background:var(--panel-2);
     border-radius:8px;padding:3px` track holding 3px-gapped mono-font
     segments, the active one lifted with `background:var(--panel);
     box-shadow:var(--shadow)` instead of a teal tint. Restyled directly
     rather than swapping widgets — st.pills doesn't support the
     always-one-selected semantics this range picker needs the way
     segmented_control's default does. */
  .st-key-db_range [data-testid="stButtonGroup"] {
    display: flex !important; gap: 3px !important;
    background: var(--panel-2) !important; border-radius: 8px !important; padding: 3px !important;
  }
  .st-key-db_range button[data-variant="segmented_control"] {
    border: none !important; border-radius: 6px !important; box-shadow: none !important;
    background: transparent !important; color: var(--muted) !important;
    font-family: var(--uv-mono) !important; font-size: 11.5px !important; font-weight: 500 !important;
    padding: 5px 11px !important; min-height: unset !important;
  }
  .st-key-db_range button[data-variant="segmented_control"][aria-checked="true"] {
    background: var(--panel) !important; color: var(--text) !important; box-shadow: var(--shadow) !important;
  }

  /* ── Dashboard benchmark toggle chips (S&P 500 / Euro Stoxx 50) — same
     idea as the range control above: st.pills' default look (fully
     rounded 9999px pill, gray fill, 14px sans text) doesn't match
     Uvalu.dc.html's benchChip spec (uvalu_dc.html ~line 2140): a 6px
     rounded chip, 11px text, transparent/muted when off and a teal
     border + var(--soft) tint + full-text color when on. */
  .st-key-db_bench_pills button[data-variant="pills"] {
    border-radius: 6px !important; padding: 4px 9px !important; font-size: 11px !important;
    background: transparent !important; border: 0.5px solid var(--line) !important; color: var(--muted) !important;
  }
  .st-key-db_bench_pills button[data-variant="pills"]:is([aria-pressed="true"], [aria-checked="true"]) {
    background: var(--soft) !important; border-color: var(--teal) !important; color: var(--text) !important;
  }

  /* ── Table density (Settings → Display → Table density) ──────────────────
     Only affects card-based row lists built from raw HTML/st.container (e.g.
     Dashboard's holdings rows) — native st.dataframe tables render to a
     canvas (glide-data-grid) whose row height is set in Python per call and
     can't be restyled from CSS, so this intentionally doesn't touch them. */
  /* Compact rows (Settings › Display › Table density, G15): Dashboard
     holdings, Screener, Watchlist and Portfolio open positions. */
  [data-density="compact"] [class*="st-key-db_hold_"],
  [data-density="compact"] [class*="st-key-scr_row_"]:not([class*="_name_cell"]):not([class*="_action"]):not([class*="_remove"]):not([class*="_view"]),
  [data-density="compact"] [class*="st-key-wl_row_"]:not([class*="_name_cell"]):not([class*="_action"]):not([class*="_remove"]):not([class*="_view"]),
  [data-density="compact"] [class*="st-key-pf_open_row_"]:not([class*="_edit"]):not([class*="_view"]):not([class*="uv_hidden_util"]) {
    padding-top: 6px !important; padding-bottom: 6px !important; min-height: 55px !important;
  }

  /* ── Analysis page cards (chart, sub-scores, six-model, financials,
     hard-veto checks, value thesis) — same `background:var(--panel);
     border:0.5px solid var(--line);border-radius:12px;box-shadow:var(--shadow)`
     panel treatment as the Dashboard's db_card_ rows above, matching
     Uvalu.dc.html's Analysis screen where every section below the hero row
     sits in its own bordered/shadowed panel instead of directly on the page
     background. Same shared-substring-selector convention as db_card_. */
  [class*="st-key-an_card_"] {
    background: var(--panel) !important; border-color: var(--line) !important;
    border-radius: 12px !important; box-shadow: var(--shadow) !important;
    padding: 18px 20px !important;
  }
  /* Same horizontal-rhythm fix as the db_card_ rows: pin the two-card rows
     (sub-scores|six-model, financials|hard-veto) to the app's standard 16px
     gap and stretch both cards to the row's tallest, instead of Streamlit's
     default top-aligned/content-height columns. */
  [data-testid="stHorizontalBlock"]:has([class*="st-key-an_card_"]) {
    align-items: stretch !important; gap: 16px !important;
  }
  [data-testid="stLayoutWrapper"]:has(> [class*="st-key-an_card_"]) {
    flex: 1 1 auto !important;
  }
  [class*="st-key-an_card_"] { flex: 1 1 auto !important; width: 100% !important; }
  /* The last block in a card kept Streamlit's markdown margin-bottom:-16px,
     so its text sat on the card's bottom edge (Data sources' flag line). */
  [class*="st-key-an_card_"] [data-testid="stElementContainer"]:last-child [data-testid="stMarkdownContainer"] {
    margin-bottom: 0 !important;
  }

  /* Same class of bug as the Holdings-row/KPI-strip height underestimation
     above: Streamlit's own layout estimate for these two raw-HTML blocks
     (the ticker/score header, the 4-card hero grid) under-reports their real
     rendered height, so the visible content overflows past the flex item's
     box and eats straight into the next section's 16px gap — confirmed live
     via getBoundingClientRect (header short by 8px, hero row short by
     exactly 16px). A min-height floor matching the real measured height is
     the same fix used there. */
  .st-key-an_header_row { min-height: 88px !important; }
  .st-key-an_hero_row   { min-height: 93px !important; }

  /* ── Screener/Watchlist filter panel — one bordered/shadowed card holding
     every filter control, matching Uvalu.dc.html's filter-bar spec
     (`background:var(--panel);border:0.5px solid var(--line);border-radius:
     12px;box-shadow:var(--shadow);padding:16px 18px`) instead of native
     widgets sitting bare on the page background. */
  .st-key-scr_filter_panel {
    background: var(--panel) !important; border-color: var(--line) !important;
    border-radius: 12px !important; box-shadow: var(--shadow) !important;
    padding: 16px 18px !important;
    /* Pinned to the real filter row's measured height (98px live: 64px
       content + 16px top/bottom padding) so the loading-skeleton panel
       (components.skeleton_filter_bar_html, shorter shimmer controls) and
       the real filled panel always render at the exact same height —
       fixing the container directly instead of hand-matching two very
       different child DOM trees (shimmer bars vs. real widgets). */
    min-height: 98px !important;
  }
  /* Filter row — each filter sized to its own content with a fixed 32px
     gap between, matching Uvalu.dc.html's flex-wrap filter bar instead of
     st.columns' equal-share ratios (which stretched a short "All sectors"
     select to the same width as the whole signal-chip group). Streamlit
     gives every child of a horizontal container `flex:1 1 0%;width:100%`
     by default (same gotcha as the header buttons row) — pinning each
     child's own generated wrapper to `flex:none;width:auto` is what
     actually lets it shrink to content instead of stretching. */
  .st-key-scr_filter_row { gap: 22px !important; }
  .st-key-scr_filter_row > [data-testid="stLayoutWrapper"] {
    flex: none !important; width: auto !important;
  }
  /* Search/Sector/Market wrap native widgets that stretch to 100% of
     their own container by design (a text input/select has no natural
     "shrink to content" size the way a button or slider track does), so
     unlike the other filters they need an explicit fixed width rather
     than relying on content-sizing. */
  .st-key-scr_search_wrap { width: 184px !important; }
  [class*="st-key-scr_select_"] { width: 140px !important; }
  /* Search input — background/border/radius match the mockup's search box.
     No leading icon: it forced 34px of left padding on the input, pushing
     typed text noticeably further right than the Sector/Market selects'
     own text (~13.5px from their own left edge, measured live) — matching
     that offset directly reads as more consistent than a decorative icon. */
  .st-key-scr_search_wrap div[data-testid="stTextInput"] > div {
    background-color: var(--panel-2) !important; border: 0.5px solid var(--line) !important;
    border-radius: 8px !important;
  }
  .st-key-scr_search_wrap div[data-testid="stTextInput"] input {
    font-size: 13px !important; padding-left: 14px !important;
  }
  /* Signal-chip / held-position toggle groups — same restyle as the
     Dashboard's benchmark chips (db_bench_pills above), but grouped inside
     a shared track (`background:var(--panel-2);border-radius:8px;
     padding:3px`) matching Uvalu.dc.html's scr.signalChips spec exactly.
     Streamlit 1.60 renders st.pills as button[data-variant="pills"] inside
     a role="toolbar" (multi-select) or role="radiogroup" (single) div,
     the selected ones marked aria-pressed / aria-checked="true" (the old
     stBaseButton-pills test ids and BaseWeb button-group are gone, so the
     rules here had silently stopped matching). The chip-track look and the
     flex/no-wrap behaviour belong on that inner group div. */
  .st-key-scr_signal_pills :is([role="toolbar"], [role="radiogroup"]) {
    display: flex !important; align-items: center !important;
    background: var(--panel-2) !important; border-radius: 8px !important;
    padding: 3px !important; gap: 3px !important; flex-wrap: nowrap !important;
    /* Matches the Search input / Sector/Market select's own height (40px,
       measured live) exactly — this group was naturally 2px shorter, which
       under the filter row's shared vertical alignment shifted the whole
       Signal block (label included) by that same 2px relative to every
       other filter's label, even though each block's own label sits flush
       at its own top. */
    min-height: 40px !important;
  }
  .st-key-scr_signal_pills button[data-variant="pills"] {
    border: none !important; border-radius: 6px !important; box-shadow: none !important;
    background: transparent !important; color: var(--muted) !important;
    font-size: 10.5px !important; font-weight: 500 !important;
    padding: 6px 8px !important; min-height: unset !important;
    white-space: nowrap !important;
  }
  .st-key-scr_signal_pills button[data-variant="pills"] p { font-size: 10.5px !important; font-weight: 500 !important; }
  /* "Hide positions I own": one toggle chip, a dot before the label; on =
     --teal border on --soft. */
  .st-key-scr_hide_owned button[data-variant="pills"] {
    border: 0.5px solid var(--line) !important; border-radius: 8px !important; background: transparent !important;
    color: var(--muted) !important; min-height: 40px !important; padding: 0 12px !important; box-shadow: none !important;
  }
  .st-key-scr_hide_owned button[data-variant="pills"] p { font-size: 12px !important; }
  .st-key-scr_hide_owned button[data-variant="pills"]::before {
    content: ""; width: 7px; height: 7px; border-radius: 50%; background: var(--line); margin-right: 8px; flex: none;
  }
  .st-key-scr_hide_owned button[data-variant="pills"]:is([aria-pressed="true"], [aria-checked="true"]) {
    border-color: var(--teal) !important; background: var(--soft) !important; color: var(--text) !important;
  }
  .st-key-scr_hide_owned button[data-variant="pills"]:is([aria-pressed="true"], [aria-checked="true"])::before { background: var(--teal); }
  .st-key-scr_signal_pills button[data-variant="pills"]:is([aria-pressed="true"], [aria-checked="true"]) {
    background: var(--panel) !important; color: var(--text) !important; box-shadow: var(--shadow) !important;
    font-weight: 500 !important;
  }
  /* Sector/Market selects — match the mockup's panel-2 select chrome. Both
     keyed containers share this rule so the two boxes always stay the same
     size (screener.py gives both columns equal width for the same reason). */
  [class*="st-key-scr_select_"] div[data-baseweb="select"] > div {
    background: var(--panel-2) !important; border-color: var(--line) !important;
    border-radius: 8px !important; font-size: 12.5px !important;
  }
  /* An open select's option list is as wide as its box, so the 140px
     Sector filter clipped long names in every language ("Communication S…",
     nl "Defensieve consumptiegoeder…"). The list is portalled to <body>,
     so this can't be scoped to the screener; it only widens the open list
     of selects narrower than 260px (the longest sector name, nl, renders at
     ~220px). The virtualised rows carry inline widths copied from the box
     and aren't re-measured, hence the second rule. */
  [data-testid="stSelectboxVirtualDropdown"] {
    width: max(var(--trigger-width), 260px) !important;
  }
  [data-testid="stSelectboxVirtualDropdown"] [role="presentation"] {
    width: 100% !important;
  }
  /* Min score / min margin-of-safety sliders — the current value is shown
     inline next to the label (custom markdown row, see screener.py) instead
     of Streamlit's floating drag-thumb bubble; the native min/max tick
     labels beneath the track aren't part of the mockup's minimal spec. */
  .st-key-scr_score_slider [data-testid="stSliderTickBar"],
  .st-key-scr_mos_slider [data-testid="stSliderTickBar"],
  .st-key-scr_score_slider [data-testid="stSliderThumbValue"],
  .st-key-scr_mos_slider [data-testid="stSliderThumbValue"] {
    display: none !important;
  }
  .st-key-scr_score_slider [data-baseweb="slider"],
  .st-key-scr_mos_slider [data-baseweb="slider"] { padding-bottom: 0 !important; }
  /* The "min margin of safety" column is made wider than "min score" purely
     so its longer label ("Min margin of safety" + "-20%") fits on one line
     at typical viewport widths — but the slider TRACK itself must stay the
     same length as Min score's regardless (a wider column would otherwise
     stretch it, since a bare st.slider fills 100% of its container). A
     fixed `width` (not `max-width` — that only caps, it doesn't equalize
     two containers of different sizes) on both pins them to the same 150px
     track independent of either column's width; the label row above is
     free to use the full (wider) column. */
  .st-key-scr_score_slider [data-baseweb="slider"],
  .st-key-scr_mos_slider [data-baseweb="slider"] { width: 150px !important; }
  /* Streamlit's slider no longer carries data-baseweb="slider", so the rule
     above stopped applying and Min score shrank to its 72px label. Fixed
     container widths instead (same track length for both); the two sit in
     one group (scr_slider_group) so they wrap together. */
  .st-key-scr_score_slider { width: 170px !important; }
  .st-key-scr_mos_slider { width: 190px !important; }
  .st-key-scr_slider_group { gap: 32px !important; width: auto !important; flex: none !important; }

  /* The name column's stColumn wrapper reported only 28px tall live while
     its actual markdown content (ticker+exchange line, company-name line)
     rendered at 44px — the same "Streamlit under-reports a raw-HTML
     markdown block's real height" bug hit repeatedly building the
     Dashboard's holdings rows. The row's vertical_alignment="center" math
     runs against that wrong, smaller number, so instead of centering the
     44px block in the row it top-anchored it at the column's (too-short)
     reported top, letting the text overflow almost to the row's very
     bottom instead of sitting centered with even space above and below.
     A min-height matching the true measured content size is the same fix
     used there. */
  [data-testid="stColumn"]:has([class*="_name_cell"]) { min-height: 44px !important; }
  /* Same bug, same fix, five more times: the score/upside/price/P-E/yield
     columns each reported only 4-5px tall live while their real content
     (a 13px number, or plain 12.5px text) rendered at 20-21px — confirmed
     live via getBoundingClientRect on each column vs its innermost markdown
     div. Centering math run against that wrong number visibly pushed every
     one of these five cells ~8px below the row's true center (score/price
     measured 8px off; the ticker/name block, whose own height IS reported
     correctly, stayed correctly centered) — only the star and name cell
     happened to already have height-reporting fixes; these five never did.
     These are the row's 4th-through-8th columns (star=1st, name=2nd,
     signal=3rd) in both callers, so :nth-child(n+4) reaches exactly this
     group without needing five separate keyed containers. */
  [class*="st-key-scr_row_"] [data-testid="stColumn"]:not(:has([class*="_name_cell"])),
  [class*="st-key-wl_row_"] [data-testid="stColumn"]:not(:has([class*="_name_cell"])) {
    min-height: 21px !important;
  }
  /* Watchlist "×": --muted, --down-txt on hover. */
  [class*="st-key-wl_row_"] [class*="_remove"] button p { color: var(--muted) !important; font-size: 16px !important; }
  [class*="st-key-wl_row_"] [class*="_remove"] button:hover p { color: var(--down-txt) !important; }

  /* ── Screener/Watchlist results table — one seamless panel (column-header
     row, then flat hairline-divided rows), matching Uvalu.dc.html's results
     table exactly instead of Streamlit's individually-boxed/gapped
     st.container(border=True) rows — same overflow:hidden/no-padding/
     row-divider convention as the Dashboard's db_holdings_card above. */
  .st-key-scr_table_card {
    background: var(--panel) !important; border-color: var(--line) !important;
    border-radius: 12px !important; box-shadow: var(--shadow) !important;
    /* clip, not hidden: same rounded clipping, but no scroll container, so
       the column header below can stick to the top of the page. */
    overflow: clip !important; padding: 0 !important;
    /* No margin-top cancellation here, unlike scr_row_'s below. This used to
       carry a -16px pull for an observed 32px double gap against
       scr_filter_panel — but that gap's real cause was a phantom sibling
       (a bare <style> injection between them, now fixed at the source with
       the uv_hidden_util wrapper in uvalu/pages_/screener.py, same as
       uvalu/shell.py's topbar CSS injection), not a genuinely doubled
       normal gap. The loading-skeleton branch never had that phantom
       sibling, so this same hack was over-cancelling ITS already-correct
       16px gap down to 0px — same class of blanket-copy drift already
       caught once for pf_panel_title_ (see that rule's comment). */
  }
  .st-key-scr_col_header {
    padding: 7px 20px !important; border-bottom: 0.5px solid var(--line-2) !important;
    background: var(--panel) !important;
  }
  /* Sticky column header while scrolling the results (visual review SC3) —
     on its wrapper, whose parent is the whole table card. */
  [data-testid="stLayoutWrapper"]:has(> .st-key-scr_col_header) {
    position: sticky !important; top: 0 !important; z-index: 3 !important;
  }
  /* Each sort button's wrapper (.stButton, display:block by default) reported
     26px tall against the button's own real 16px content — not padding or
     margin (both computed 0), but the *inline-level* button (Streamlit
     renders it display:inline-flex) sitting inside .stButton's inherited
     25.6px line-height and getting positioned by default baseline vertical-
     align within that line box, adding ~10px of invisible space around it.
     Confirmed live: header measured 48px total (11px+11px padding + 26px
     inflated button-wrapper) despite every visible label being a uniform
     16px tall. Forcing the wrapper to flex+center sidesteps the whole
     line-height/baseline mechanism — same fix class as Portfolio's panel-
     title button, different root cause (inline-baseline vs. a broken
     content-height estimate) landing on the same "force flex centering on
     the real flex-item wrapper" fix. Brings the header down to a clean
     30px matching pf_col_header/db_holdings_colheader. */
  .st-key-scr_col_header .stButton {
    display: flex !important; align-items: center !important; line-height: normal !important;
  }
  /* The loading-skeleton column header (screener.py's cold-cache branch)
     reuses this same scr_col_header container but fills it with plain
     st.markdown label divs instead of the real st.button headers above —
     so it never gets the .stButton height-normalizing rule and hits the
     same "stColumn under-reports a raw markdown block's real height" bug
     fixed elsewhere in this file (name_cell/score/price/pe/dy columns):
     confirmed live, the column reported ~15px tall while its own 16px
     label text actually rendered past that, overflowing into the first
     skeleton row pulled up right underneath (margin-top:-16px above) and
     visibly crossing the header text. :not(:has(.stButton)) scopes this
     to exactly the skeleton's bare-markdown columns, leaving the real
     button-based header (already correct at 31px) untouched. */
  .st-key-scr_col_header [data-testid="stColumn"]:not(:has(.stButton)) {
    min-height: 17px !important;
  }
  /* Watchlist "Add ticker" form — same card treatment as the rest of the
     app (Screener's scr_filter_panel) instead of st.form()'s plain default
     bordered box (transparent background, generic gray border, 8px radius,
     no shadow — confirmed live). st.form() doesn't expose its own key as a
     "st-key-*" class, so the wrapper container above is the real hook. */
  .st-key-wl_add_form_wrap [data-testid="stForm"] {
    background: var(--panel) !important; border-color: var(--line) !important;
    border-radius: 12px !important; box-shadow: var(--shadow) !important;
    padding: 16px 18px !important;
  }
  .st-key-wl_add_form_wrap [data-testid="stTextInput"] > div {
    background-color: var(--panel-2) !important; border: 0.5px solid var(--line) !important;
    border-radius: 8px !important;
  }
  .st-key-wl_add_form_wrap [data-testid="stTextInput"] input { font-size: 13px !important; }
  /* Filled teal submit button — the design's one filled CTA per screen:
     compact 8px 13px padding and 12.5px text instead of Streamlit's default
     button sizing (which, combined with the column stretching to fill its
     share of the row, rendered much larger/wider than every other button
     in the app). */
  .st-key-wl_add_form_wrap [data-testid="stFormSubmitButton"] button[kind="primaryFormSubmit"] {
    background: var(--primary-fill) !important; border: none !important; color: #fff !important;
    border-radius: 8px !important; padding: 8px 13px !important; font-size: 12.5px !important;
    height: auto !important; min-height: unset !important; width: auto !important;
  }
  .st-key-wl_add_form_wrap [data-testid="stFormSubmitButton"] button[kind="primaryFormSubmit"]:hover {
    background: var(--mint) !important; color: var(--navy) !important;
  }
  /* Shrinking the button off width="stretch" left it flush against the
     left edge of its column instead — that column is wider than the
     button needs (it shares the same 1-of-6 ratio as the other two fields'
     wider columns), leaving ~128px of dead space to the button's right
     (confirmed live). justify-content:flex-end alone didn't fix it: the
     column's real flex ITEM is its generated stVerticalBlock wrapper
     (`flex:1 1 0%;width:100%` by default — the same "wrapper stretches to
     fill" gotcha hit repeatedly elsewhere in this app), which was still
     stretching to the column's full width regardless of the column's own
     justify-content, so the button rendered flush-left *within* that
     full-width wrapper. Pinning the wrapper to its own content width is
     what actually lets flex-end push it to the right. */
  .st-key-wl_add_form_wrap [data-testid="stColumn"]:has([data-testid="stFormSubmitButton"]) {
    display: flex !important; justify-content: flex-end !important;
    /* The button's column sizes to the button (one line, any language or
       window width); Ticker and Company name share the rest. */
    flex: 0 0 auto !important; width: auto !important;
  }
  .st-key-wl_add_form_wrap [data-testid="stFormSubmitButton"] button p { white-space: nowrap !important; }
  /* ...and the two fields keep their 1.5 : 3.8 split of what is left (with
     their percentage flex-basis they pushed the button onto its own row
     below ~1100px). */
  .st-key-wl_add_form_wrap [data-testid="stColumn"]:nth-child(1) { flex: 1.5 1 0% !important; min-width: 0 !important; }
  .st-key-wl_add_form_wrap [data-testid="stColumn"]:nth-child(2) { flex: 3.8 1 0% !important; min-width: 0 !important; }
  .st-key-wl_add_form_wrap [data-testid="stColumn"]:has([data-testid="stFormSubmitButton"]) > div {
    flex: none !important; width: auto !important;
  }

  /* Watchlist's own table card/header — same panel treatment as Screener's
     scr_table_card/scr_col_header (this page had never been given it; its
     header was still bare st.columns with no card/hairline, and the
     Upside/Price/P-E/Yield labels had no right-alignment at all, sitting
     ~94px off from their own right-aligned data cells below, confirmed
     live). No margin-top pull here — Watchlist's table isn't preceded by
     a bordered panel like Screener's filter bar, so there's no matching
     32px double-gap to correct for. */
  .st-key-wl_table_card {
    background: var(--panel) !important; border-color: var(--line) !important;
    border-radius: 12px !important; box-shadow: var(--shadow) !important;
    overflow: hidden !important; padding: 0 !important;
  }
  .st-key-wl_col_header {
    padding: 7px 20px !important; border-bottom: 0.5px solid var(--line-2) !important;
    /* Its columns are plain single-line <div> labels (no sortable button
       chrome the way Screener's header has) — Streamlit's own internal
       height estimate for them came back as literally 0px live (same
       under-reporting bug as the name-cell fix above), so the row's real
       23px was just its padding, not real content. min-height both fixes
       that and matches Screener's own header height — 30px, tightened from
       48px on 2026-07-20 once scr_col_header's own real inflation (a
       baseline/line-height issue on its sort buttons, not a deliberate
       design height) was found and fixed; keep these two in sync. */
    min-height: 30px !important;
  }
  /* :not(...) exclusions matter here: the row's OWN class is
     "st-key-scr_row_<idx>_<ticker>", but its NESTED sub-containers
     (star/remove buttons, the name-cell click target, and the invisible
     view button living *inside* that cell) are keyed as "<that same
     string>_action"/"_remove"/"_name_cell"/"_view" — so their class ALSO
     contains "st-key-scr_row_" as a substring and would otherwise pick up
     this same divider/padding/background/position:relative too. Two
     distinct symptoms were traced to this: a second, shorter hairline
     directly under just the star+name area (the name-cell picking up the
     row's own border-bottom), and — worse — the invisible view-button's
     own container (normally `position:absolute` via the name-cell overlay
     rule below) had ITS position knocked back to `relative` by this rule's
     *higher* selector specificity (three-plus :not()s beats a plain
     descendant selector), pulling it back into normal flow and inflating
     the whole row to ~116px. Forgetting "_view" here after already adding
     "_action"/"_name_cell"/"_remove" is exactly how the second bug crept
     back in — any *new* per-row sub-container key needs adding here too. */
  [class*="st-key-scr_row_"]:not([class*="_name_cell"]):not([class*="_action"]):not([class*="_remove"]):not([class*="_view"]),
  [class*="st-key-wl_row_"]:not([class*="_name_cell"]):not([class*="_action"]):not([class*="_remove"]):not([class*="_view"]) {
    position: relative !important; padding: 12px 20px !important;
    border-bottom: 0.5px solid var(--line-2) !important;
    border-radius: 0 !important; background: transparent !important; cursor: pointer;
    /* Cancels the ~16px default vertical gap Streamlit puts between every
       sibling container in the block (including right after the column
       header), matching the Dashboard holdings rows' identical fix. */
    margin-top: -16px !important;
    /* Same 67px floor as the Dashboard holdings row (`.st-key-db_hold_`) —
       both use identical 12px 20px padding, so matching this makes the two
       tables' row heights consistent app-wide, as requested. */
    min-height: 67px !important;
  }
  [class*="st-key-scr_row_"]:not([class*="_name_cell"]):not([class*="_action"]):not([class*="_remove"]):not([class*="_view"]):hover,
  [class*="st-key-wl_row_"]:not([class*="_name_cell"]):not([class*="_action"]):not([class*="_remove"]):not([class*="_view"]):hover {
    background: var(--soft) !important;
  }
  /* Whole row as the click target (opens the detail drawer) — an invisible
     button is layered over the ENTIRE row via `position:absolute;inset:0`
     against the row's own `position:relative` (set on the row-divider rule
     above), matching the Dashboard holdings row's whole-row click behavior
     exactly (previously scoped to just the ticker/name cell). Same "target
     the real generated wrapper, not the st-key-* div itself" +
     "position:absolute removes it from flow so it can't reintroduce the
     invisible-element gap bug" pattern used there. Streamlit also gives this
     wrapper a `width="fit-content"` HTML attribute (same gotcha hit fixing
     the header sort buttons) whose own CSS rule beats the implicit width
     `inset:0`'s left:0/right:0 would otherwise produce — confirmed live,
     the wrapper measured only ~30px wide despite inset:0. width:100% here
     overrides that explicitly. */
  [class*="st-key-scr_row_"] [class*="_view"],
  [class*="st-key-wl_row_"] [class*="_view"] {
    position: absolute !important; inset: 0 !important; margin: 0 !important; z-index: 1;
    width: 100% !important; height: 100% !important;
  }
  [class*="st-key-scr_row_"] [class*="_view"] button,
  [class*="st-key-wl_row_"] [class*="_view"] button {
    width: 100% !important; height: 100% !important; opacity: 0 !important;
    border: none !important; background: transparent !important; padding: 0 !important;
    cursor: pointer;
  }
  /* Watchlist star (screener rows) / remove "×" (watchlist rows) —
     Streamlit's tertiary button style renders as an underlined link by
     default; these are plain icon-only controls with no such affordance.
     Centering targets the button's own *element-container* wrapper (not
     the button itself — forcing height:100% directly on the button
     produced a box that overflowed past its own column's top/bottom edges,
     off-center by ~8px live) so the naturally-sized button centers inside
     a wrapper that actually spans the column's full height, matching the
     taller two-line ticker/name cell beside it instead of hugging the
     column's own (shorter, content-sized) top edge. Also lifted above the
     row-wide click overlay (z-index:2 > the overlay's 1) via its own
     stacking context, so it stays independently clickable instead of being
     swallowed by that overlay sitting on top of the whole row.

     :not([class*="uv_hidden_util"]) matters here: the star's own per-row
     <style>-only markdown block is keyed "uv_hidden_util_<...>_action" —
     its class contains "_action" too, so without this exclusion this rule
     ALSO matched it and knocked its position back from the hidden_util
     rule's `absolute` to this rule's (higher-specificity) `relative`,
     pulling it back into normal flow. That silently added one whole
     ~16px flex gap to the row (confirmed live: row height jumped from
     ~68px to ~84.67px) — the exact "invisible utility element" bug this
     hidden_util convention exists to prevent, reintroduced by a sibling
     rule's substring match rather than by the hidden_util rule itself. */
  [class*="st-key-scr_row_"] [class*="_action"]:not([class*="uv_hidden_util"]),
  [class*="st-key-scr_row_"] [class*="_remove"]:not([class*="uv_hidden_util"]),
  [class*="st-key-wl_row_"] [class*="_action"]:not([class*="uv_hidden_util"]),
  [class*="st-key-wl_row_"] [class*="_remove"]:not([class*="uv_hidden_util"]) {
    display: flex !important; align-items: center !important; justify-content: center !important;
    height: 100% !important; position: relative !important; z-index: 2;
  }
  [class*="st-key-scr_row_"] [class*="_action"] button,
  [class*="st-key-scr_row_"] [class*="_remove"] button,
  [class*="st-key-wl_row_"] [class*="_action"] button,
  [class*="st-key-wl_row_"] [class*="_remove"] button {
    text-decoration: none !important;
    /* Streamlit's default button is ~48.67px tall (40px + its own border/
       padding) — taller than the now-compact 2-line name cell (~43px) once
       that cell's own line-height was tightened, which made the star
       column (not the name cell) the tallest thing in the row and set the
       whole row's height. Shrinking the button's own min-height keeps it a
       comfortable click target while no longer being the row's tallest
       column. */
    min-height: 32px !important; padding: 4px !important;
    /* The star/remove column is only as tall as this button (its sole
       content) and Streamlit centers that whole column within the taller
       row via auto margins — but the button measured live off-center
       within its own column regardless. `transform` (not `margin-top`)
       nudges it purely visually, without adding to the button's own layout
       box — a margin-based nudge was inflating the whole row's height,
       since this column's own box height feeds into the row's
       vertical_alignment math the same way the name cell's does. */
    transform: translateY(0px) !important;
  }

  /* ── Portfolio full-page title row (Open/Closed/Dividends) — extra
     breathing room before the table below it, per 2026-07-20 feedback
     ("more space between the title and the table"). Streamlit's plain
     ~16px default sibling gap read as too tight against a 22px page
     heading; this pads it out to a clearer ~28px. */
  [class*="st-key-pf_page_title_"] {
    margin-bottom: 12px !important;
  }
  /* Closed positions: five narrow columns, so the title row and the card
     stop at 760px (mockup) instead of stretching a sparse table. */
  .st-key-pf_page_title_closed, .st-key-pf_card_closed_full { max-width: 760px !important; }

  /* ── Portfolio page — card panels + row lists ────────────────────────────
     Same `background:var(--panel);border:0.5px solid var(--line);
     border-radius:12px;box-shadow:var(--shadow)` panel treatment as
     db_card_/an_card_ above, first `pf_`-prefixed rules in this file. */
  [class*="st-key-pf_card_"] {
    background: var(--panel) !important; border-color: var(--line) !important;
    border-radius: 12px !important; box-shadow: var(--shadow) !important;
    overflow: hidden !important; padding: 0 !important;
  }
  [data-testid="stHorizontalBlock"]:has([class*="st-key-pf_card_"]) {
    align-items: stretch !important; gap: 18px !important;
  }
  /* Overview's Closed positions + Dividends preview row is the one
     exception — it should NOT stretch to a shared height. Same reasoning as
     Dashboard's own bottom row (db_card_ rule above, ~line 272): Dividends
     usually has fewer rows than the wider Closed-positions table beside it,
     and stretching it to match left dead space under the shorter list
     (confirmed live). More specific than the blanket rule above (same
     `!important` weight, but this selector is more specific — the `:has()`
     argument itself carries the extra attribute selector), so it wins for
     just this row without touching every other pf_card_ pairing. */
  [data-testid="stHorizontalBlock"]:has([class*="st-key-pf_card_"]):has([class*="st-key-pf_card_div_ov"]) {
    align-items: flex-start !important;
  }
  [data-testid="stLayoutWrapper"]:has(> [class*="st-key-pf_card_"]) {
    flex: 1 1 auto !important;
  }
  [class*="st-key-pf_card_"] { flex: 1 1 auto !important; width: 100% !important; }
  [class*="st-key-pf_col_header"] {
    padding: 7px 20px !important; border-bottom: 0.5px solid var(--line-2) !important;
    min-height: 30px !important;
  }
  /* The Overview previews' column header comes right after the panel's own
     title-bar row (a SEPARATE sibling st.container, not a shared one) —
     Streamlit's default ~16px gap between the two siblings stacked on top
     of the header's own 30px box made the whole header area read as ~46px
     tall despite the header itself measuring exactly 30px (confirmed live:
     gap 16px, header 30px). The full-page variants don't need this — there
     the column header is the FIRST child of the card, flush against the
     panel's own top border with no preceding sibling gap to cancel. */
  [class*="st-key-pf_col_header_open_ov"], [class*="st-key-pf_col_header_closed_ov"],
  [class*="st-key-pf_col_header_div_ov"] {
    margin-top: -16px !important;
  }
  /* Panel title bar (e.g. "Open positions" + an icon-only "open full page"
     button — matches the mockup's own SVG expand-corners icon exactly,
     Uvalu.dc.html's `openOpenFull`/`openClosedFull`/`openDividendsFull`
     handlers, rather than this app's earlier "View all →" text link) sitting
     above the column header inside the same pf_card_ panel. 12px 20px
     lands at a measured ~50px total bar height, confirmed as the target by
     Sven on 2026-07-20 after an intermediate 4px-padding/~31px pass was
     tried and rejected — only the column header row below (pf_col_header)
     was meant to shrink to ~30px, not this title bar. */
  [class*="st-key-pf_panel_title_"] {
    padding: 16px 20px !important; border-bottom: 0.5px solid var(--line-2) !important;
  }
  /* The title text lives in a <p> several levels deep that carries its OWN
     explicit font-size from Streamlit's default markdown paragraph style —
     font-size/font-weight set on the container above never reaches it (CSS
     inheritance only fills gaps a descendant doesn't set itself), so the
     title rendered at Streamlit's default ~16px/400 with default line-height
     instead of the mockup's compact 15px/500 — the same gap this app hit
     fixing the Screener's sortable column headers. That taller, wrongly-
     weighted line box (not the button, which was already a compact 22px)
     is what inflated the whole title bar to ~55px against the mockup's
     ~48px and threw off the vertical centering against the "View all →"
     button beside it. Target the <p> directly and tighten its line-height. */
  [class*="st-key-pf_panel_title_"] [data-testid="stMarkdownContainer"] p {
    margin: 0 !important; font-size: 15px !important; font-weight: 500 !important; line-height: 1.3 !important;
  }
  /* Even after the font-size fix above, the title still sat 7px below the
     "View all →" button beside it (button center 321px, title center 328px,
     confirmed live) despite both being inside the same `vertical_alignment=
     "center"` row. Root cause: Streamlit's own `.stMarkdown > div` wrapper
     ships a hardcoded ~3.5px height (a class rule, not inline — presumably
     tuned for its own default font metrics) regardless of the real ~20px
     text it holds; flexbox then centers each *ancestor* on its own
     (wrong) reported height independently at every nesting level, and the
     errors compound differently for a <p> than for a <button> (which has
     no such wrapper). Restoring the correct height at the `.stMarkdown >
     div` level fixes that div's own box but NOT the residual offset — the
     centering math up the chain doesn't retroactively correct itself layer
     by layer. Rather than chase it through N more wrapper levels, nudge the
     whole title visually with `transform` (not `margin`, which would feed
     back into the same broken height math) — same pragmatic pattern used
     for the Screener star button's centering fix. -7px was the exact live-
     measured gap between the two centers; recheck if the title/button font
     sizes ever change. */
  [class*="st-key-pf_panel_title_"] .stMarkdown > div { min-height: 20px !important; }
  [class*="st-key-pf_panel_title_"] [data-testid="stElementContainer"]:has(> .stMarkdown) {
    min-height: 22px !important; display: flex !important; align-items: center !important;
    transform: translateY(-7px) !important;
  }
  /* Icon-only "open full page" button — matches the mockup's 15x15 SVG icon
     exactly (faint, teal on hover), same small-square treatment as the row
     edit-pencil buttons elsewhere on this page for visual consistency. */
  [class*="st-key-pf_panel_title_"] button {
    background: transparent !important; border: none !important; color: var(--muted) !important;
    padding: 0 !important; min-height: 22px !important; height: 22px !important; width: 22px !important;
  }
  [class*="st-key-pf_panel_title_"] button:hover { color: var(--link) !important; }
  /* No margin-top cancellation here, unlike scr_table_card — confirmed live
     (getBoundingClientRect) that every pf_card_ panel already sits a clean
     natural 16px below whatever precedes it (heading row, another card, or
     the KPI row below). scr_table_card's -16px fix was for a genuine
     doubled gap from two adjacent BORDERED panels; nothing here doubles up,
     so an earlier blanket copy of that rule was over-cancelling the normal
     gap to 0px (confirmed live: panels sat flush against the KPI row/heading
     above them, "not correct" per user report on 2026-07-20). */

  /* KPI card row (Overview only) — same Streamlit markdown-height
     under-estimation bug as the Dashboard KPI strip (db_kpi_row below):
     the raw-HTML kpi_card() content measured 115-116px live while its
     st.columns() row wrapper reported only 99-100px, so the *next* section
     (the Open positions panel) flowed 16px too high and visually overlapped
     the true bottom of the cards instead of leaving the normal 16px gap.
     Wrap the row in this key and float its wrapper's height to match. */
  .st-key-pf_kpi_row { min-height: 112px !important; }
  /* Same bug on the Dividend log's summary tiles: wrapper 99px vs 115px
     real cards, so the log table sat flush against them (0px gap vs the
     overview's 16px — both live-measured). */
  .st-key-pf_div_tiles { min-height: 112px !important; }
  /* Cash Management v1 — cash strip + Cash activity page (Uvalu Cash
     Management.dc.html). pf_card_ panels are padding:0, so the strip body,
     the ledger filter bar and the empty-state caption carry the mockup's
     16px/12px 20px insets themselves; the filter bar sits flush on the
     ledger header (-16px cancels Streamlit's sibling gap), and the ledger's
     single st.markdown drops the -1rem margin that would clip its last row
     under overflow:hidden. */
  .st-key-pf_cash_tiles { min-height: 112px !important; }
  .st-key-pf_cash_strip_body { padding: 16px 20px !important; }
  .st-key-pf_cash_filter_row {
    padding: 12px 20px !important; border-bottom: 0.5px solid var(--line-2) !important;
    margin-bottom: -16px !important;
  }
  .st-key-pf_card_cash_full [data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }
  /* Overview cash card: Deposit/Withdraw side by side, same width. */
  .st-key-pf_cash_btns { flex-wrap: nowrap !important; }
  .st-key-pf_cash_btns button { min-width: 96px !important; justify-content: center !important; }
  .st-key-pf_open_ov_all { padding: 4px 20px 10px !important; }
  .st-key-pf_open_ov_all button p { font-size: 12.5px !important; color: var(--link) !important; }
  .st-key-pf_card_cash_full [data-testid="stCaptionContainer"] { padding: 28px 20px 12px !important; }
  /* "Show more" only: a card-wide .stButton rule also padded every row's
     edit pencil to 40px in its 24px column, 8px past the card edge. */
  .st-key-pf_card_cash_full .st-key-cash_show_more .stButton { padding: 0 20px 12px !important; }
  .st-key-risk_cash_banner { padding: 11px 16px !important; border-radius: 8px !important; }
  .st-key-risk_cash_banner button p { color: var(--link) !important; font-size: 12px !important;
    white-space: nowrap !important; }

  /* Row lists — hairline-divided flat rows, no per-row border/shadow (the
     panel above provides that once). :not() exclusions follow the exact
     same pattern/reasoning as scr_row_'s (see that rule's comment): each
     row's nested sub-containers (the uv_hidden_util edit-color style block,
     the edit-pencil button's auto-generated wrapper, and — pf_open_row_
     only — the whole-row view-overlay button's wrapper) all contain the
     row's own key as a substring and would otherwise pick up this same
     divider/padding/position treatment too. */
  [class*="st-key-pf_open_row_"]:not([class*="_edit"]):not([class*="_view"]):not([class*="uv_hidden_util"]),
  [class*="st-key-pf_closed_row_"]:not([class*="_edit"]):not([class*="uv_hidden_util"]),
  [class*="st-key-pf_div_row_"]:not([class*="_edit"]):not([class*="uv_hidden_util"]),
  [class*="st-key-pf_cash_row_"]:not([class*="_edit"]):not([class*="uv_hidden_util"]) {
    position: relative !important; padding: 12px 20px !important;
    border-bottom: 0.5px solid var(--line-2) !important;
    border-radius: 0 !important; background: transparent !important;
    margin-top: -16px !important;
    min-height: 67px !important;
  }
  [class*="st-key-pf_div_row_ov_"]:not([class*="_edit"]):not([class*="uv_hidden_util"]) {
    /* Overview dividend preview rows are a 2-line name+ticker/date cell —
       measured live at 48px real content height (11px padding + 37px text
       block), 2px taller than the previous 46px floor, which let the date's
       descenders clip against the row divider. 52px gives clean headroom on
       both sides. Scoped to the preview (`_ov_`) only: the full Dividend log
       rows are the taller 2-line grid and keep the shared 67px / 12px-20px
       row treatment above, same as open/closed position rows. */
    min-height: 52px !important; padding: 11px 20px !important;
  }
  /* Full Dividend log rows/header: each is one multi-line HTML grid in a
     single st.markdown. Streamlit's stMarkdownContainer carries a -1rem
     margin-bottom, so its column reported 25px for a 41px grid and the
     edit-pencil column centred against the wrong height (pencil 8px high —
     confirmed live). Zero it so the pencil, grid and row share one centre. */
  [class*="st-key-pf_div_row_"]:not([class*="_ov_"]) [data-testid="stMarkdownContainer"],
  [class*="st-key-pf_cash_row_"] [data-testid="stMarkdownContainer"],
  .st-key-pf_col_header_cash_full [data-testid="stMarkdownContainer"],
  .st-key-pf_col_header_div_full [data-testid="stMarkdownContainer"],
  /* Same -1rem margin on the summary card: it under-reported the year table's
     height so overflow:hidden clipped the last year row by 15px, and pulled
     the title block off the Export button's centre line (both live-measured). */
  .st-key-pf_card_tax_years [data-testid="stMarkdownContainer"] {
    margin-bottom: 0 !important;
  }
  /* Tax-estimate box under the annual summary: a plain 8px box, not a card.
     Keep it outside the selector list above, or every row's markdown gets
     its padding (the ledger pencil then overflowed the card). */
  .st-key-pf_card_tax_note {
    padding: 14px 16px !important; border-radius: 8px !important; background: var(--panel) !important;
    box-shadow: none !important; border-color: var(--line) !important;
  }
  /* Annual dividend income summary — the card itself is padding:0 (pf_card_
     rule above), so its title bar carries the mockup's 18px/20px inset; the
     year table below brings its own 20px side padding per grid row. */
  .st-key-pf_tax_years_title { padding: 18px 20px 0 !important; }
  /* Only open-position rows are clickable (matches the mockup: only
     `h.onClick` exists — `s.`/`d.` rows have none). */
  [class*="st-key-pf_open_row_"]:not([class*="_edit"]):not([class*="_view"]):not([class*="uv_hidden_util"]) {
    cursor: pointer;
  }
  [class*="st-key-pf_open_row_"]:not([class*="_edit"]):not([class*="_view"]):not([class*="uv_hidden_util"]):hover {
    background: var(--soft) !important;
  }
  /* Whole-row click overlay (open positions only) — identical pattern to
     scr_row_'s `_view` overlay above. */
  [class*="st-key-pf_open_row_"] [class*="_view"] {
    position: absolute !important; inset: 0 !important; margin: 0 !important; z-index: 1;
    width: 100% !important; height: 100% !important;
  }
  [class*="st-key-pf_open_row_"] [class*="_view"] button {
    width: 100% !important; height: 100% !important; opacity: 0 !important;
    border: none !important; background: transparent !important; padding: 0 !important;
    cursor: pointer;
  }
  /* Edit-pencil button — lifted above the row-wide view overlay (open rows)
     via a higher z-index, same "independently clickable" trick as
     scr_row_'s star; closed/dividend rows have no overlay to fight but get
     the same centering/sizing for visual consistency. */
  [class*="st-key-pf_open_row_"] [class*="_edit"]:not([class*="uv_hidden_util"]),
  [class*="st-key-pf_closed_row_"] [class*="_edit"]:not([class*="uv_hidden_util"]),
  [class*="st-key-pf_div_row_"] [class*="_edit"]:not([class*="uv_hidden_util"]),
  [class*="st-key-pf_cash_row_"] [class*="_edit"]:not([class*="uv_hidden_util"]) {
    display: flex !important; align-items: center !important; justify-content: center !important;
    height: 100% !important; position: relative !important; z-index: 2;
  }
  [class*="st-key-pf_open_row_"] [class*="_edit"] button,
  [class*="st-key-pf_closed_row_"] [class*="_edit"] button,
  [class*="st-key-pf_div_row_"] [class*="_edit"] button,
  [class*="st-key-pf_cash_row_"] [class*="_edit"] button {
    min-height: 26px !important; width: 26px !important; padding: 0 !important;
    border-radius: 8px !important; background: transparent !important; border: none !important;
    text-decoration: none !important;
  }
  [class*="st-key-pf_open_row_"] [class*="_edit"] button:hover,
  [class*="st-key-pf_closed_row_"] [class*="_edit"] button:hover,
  [class*="st-key-pf_div_row_"] [class*="_edit"] button:hover,
  [class*="st-key-pf_cash_row_"] [class*="_edit"] button:hover {
    background: var(--line-2) !important;
  }

  /* ── Risk page — score/metrics cards, factor+concentration cards, holdings
     row list. Same `background:var(--panel);border:0.5px solid var(--line);
     border-radius:12px;box-shadow:var(--shadow)` panel treatment as
     db_card_/an_card_/pf_card_ above — Uvalu.dc.html's Risk screen puts every
     section in its own bordered/shadowed panel. */
  [class*="st-key-risk_card_"] {
    background: var(--panel) !important; border-color: var(--line) !important;
    border-radius: 12px !important; box-shadow: var(--shadow) !important;
  }
  [data-testid="stHorizontalBlock"]:has([class*="st-key-risk_card_"]) {
    align-items: stretch !important; gap: 18px !important;
  }
  [data-testid="stLayoutWrapper"]:has(> [class*="st-key-risk_card_"]) {
    flex: 1 1 auto !important;
  }
  [class*="st-key-risk_card_"] { flex: 1 1 auto !important; width: 100% !important; }
  /* Gauge/factor/concentration cards get the mockup's 20px/18px-20px inner
     padding; the metrics grid card instead pads each of its own 6 cells
     individually (matching riskVM.metrics' per-cell `padding:18px 20px`), so
     the card itself only needs a thin 6px/4px frame around them. The
     holdings table card is a seamless header+rows panel like scr_table_card,
     so it gets no padding at all — the column header/row rules below own it. */
  .st-key-risk_card_gauge { padding: 20px !important; }
  .st-key-risk_card_factors, .st-key-risk_card_conc { padding: 18px 20px !important; }
  .st-key-risk_card_metrics { padding: 6px 4px !important; }
  .st-key-risk_card_holdings { overflow: hidden !important; padding: 0 !important; }

  /* Column header + row list for "Risk contribution by holding" — same
     raw-CSS-Grid-per-row convention as the Dashboard's db_hold_ rows
     (components.py's risk_holding_row_html(), a fixed-px grid-template that
     st.columns()'s ratio-only widths can't replicate), including the same
     Streamlit markdown-height-underestimation floor and whole-row invisible-
     button click overlay. */
  .st-key-risk_col_header {
    padding: 10px 20px !important; border-bottom: 0.5px solid var(--line-2) !important;
    min-height: 30px !important;
  }
  /* Title above the header row; the card has no padding of its own, and the
     -16px cancels the sibling gap so the title and header read as one block. */
  .st-key-risk_holdings_title { padding: 16px 20px 0 !important; }
  .st-key-risk_holdings_title + * , [data-testid="stLayoutWrapper"]:has(> .st-key-risk_holdings_title) + [data-testid="stLayoutWrapper"] > .st-key-risk_col_header {
    margin-top: -6px !important;
  }
  /* :not([class*="_view"]) matters here — unlike db_hold_'s button (keyed
     "db_holdbtn_<idx>", a name that never contains "db_hold_" as a
     substring by design), this row's trailing button is keyed
     "risk_hold_<idx>_<ticker>_view", which DOES contain "st-key-risk_hold_"
     as a substring. Without the exclusion, this same rule would also match
     the button's own generated wrapper and reintroduce its padding/border/
     min-height, fighting the position:absolute overlay rule below (same
     class of bug documented for scr_row_/pf_open_row_'s identical `_view`
     exclusion). */
  [class*="st-key-risk_hold_"]:not([class*="_view"]) {
    position: relative !important; padding: 12px 20px !important;
    border-bottom: 0.5px solid var(--line-2) !important;
    border-radius: 0 !important; background: transparent !important;
    margin-top: -16px !important; min-height: 67px !important;
  }
  [class*="st-key-risk_hold_"]:not([class*="_view"]):hover { background: var(--soft) !important; }
  [class*="st-key-risk_hold_"] [data-testid="stElementContainer"]:has(button) {
    position: absolute !important; inset: 0 !important; margin: 0 !important; z-index: 1;
  }
  [class*="st-key-risk_hold_"] [data-testid="stElementContainer"]:has(button) button {
    width: 100% !important; height: 100% !important; opacity: 0 !important;
    border: none !important; background: transparent !important; padding: 0 !important;
    cursor: pointer;
  }

  /* ── Data-page header (components.page_header): brand §7 — 24px title,
     13px subtitle 2px below, provenance 8px below (provenance_bar_html). */
  :root { --uv-page-pad: 22px 28px 60px; --uv-section-gap: 18px; }
  .uv-page-title { font-size: 24px; font-weight: 500; letter-spacing: -0.02em; line-height: 1.2; color: var(--text); }
  .uv-page-sub { font-size: 13px; color: var(--muted); margin-top: 2px; line-height: 1.5; }
  .uv-page-sub b { color: var(--text); font-weight: 500; }
  /* Streamlit's -1rem markdown margin would let the next block ride up
     over the provenance line. */
  [data-testid="stMarkdownContainer"]:has(> .uv-page-head) { margin-bottom: 0 !important; }

  /* ── Supporting-page frame (components.support_page): Settings,
     Methodology, Legal, About. Left-aligned on the same gutter as
     every other page, 1180px cap; back link, 24px title (brand H1), then a
     200px sticky rail beside a 760px content column. ───────────────────── */
  .st-key-uv_support { max-width: 1180px !important; margin: 0 !important; padding: 0 !important; gap: 0 !important; }
  /* components.back_link — every "← Back to …" above a page title. */
  [class*="st-key-uv_back_"] button {
    min-height: 0 !important; padding: 0 !important; margin-bottom: 6px !important;
    border: none !important; background: none !important;
  }
  [class*="st-key-uv_back_"] button p { font-size: 12px !important; color: var(--muted) !important; }
  [class*="st-key-uv_back_"] button:hover p { color: var(--text) !important; }
  .uv-support-head { padding-bottom: 20px; }
  /* Streamlit pulls every markdown block up by 16px (margin-bottom:-1rem),
     which would swallow the gap above the rail. */
  [data-testid="stMarkdownContainer"]:has(> .uv-support-head) { margin-bottom: 0 !important; }
  .uv-support-title { font-size: 24px; font-weight: 500; letter-spacing: -0.02em; line-height: 1.2; color: var(--text); }
  .uv-support-subtitle { font-size: 13px; color: var(--muted); margin-top: 4px; line-height: 1.5; }
  .uv-support-links { display: flex; flex-wrap: wrap; gap: 4px 16px; margin-top: 10px; font-size: 12px; }
  .uv-support-links a { color: var(--link) !important; text-decoration: none; }
  .uv-support-links a:hover { color: var(--text) !important; }
  .st-key-uv_support_grid {
    gap: 32px !important; align-items: flex-start !important;
    flex-wrap: nowrap !important;
  }
  .st-key-uv_support_content { max-width: 760px !important; min-width: 0 !important; flex: 1 1 0 !important; gap: 20px !important; }
  [data-testid="stLayoutWrapper"]:has(> .st-key-uv_support_content) { max-width: 760px; min-width: 0; flex: 1 1 0; }
  /* No overflow:auto/max-height: Streamlit under-measures raw-HTML content,
     so a scroll box clipped the last link. */
  .st-key-uv_support_rail { position: sticky; top: 16px; align-self: flex-start; gap: 2px !important; flex: none !important; }
  [data-testid="stLayoutWrapper"]:has(> .st-key-uv_support_rail) { position: sticky; top: 16px; align-self: flex-start; flex: none; }
  .st-key-uv_support_rail [data-testid="stPageLink"], .st-key-uv_support_rail [data-testid="stPageLink"] > *,
  .st-key-uv_support_rail [class*="st-key-uv_rail_link_"] { width: 100% !important; }
  a.uv-rail-item, .st-key-uv_support_rail a[data-testid="stPageLink-NavLink"] {
    width: 100% !important; box-sizing: border-box;
    display: block; padding: 7px 12px; font-size: 13px; line-height: 1.35; color: var(--muted);
    text-decoration: none; border-left: 2px solid transparent; border-radius: 0 6px 6px 0;
  }
  a.uv-rail-item:hover { color: var(--text); }
  a.uv-rail-item.uv-rail-active {
    border-left-color: var(--teal); background: var(--panel); color: var(--text); font-weight: 500; padding-left: 10px;
  }
  .st-key-uv_support_rail a[data-testid="stPageLink-NavLink"] {
    height: auto !important; min-height: 0 !important; background: none !important; gap: 0 !important;
  }
  .st-key-uv_support_rail a[data-testid="stPageLink-NavLink"] > span:has([data-testid="stIconMaterial"]) { display: none !important; }
  .st-key-uv_support_rail a[data-testid="stPageLink-NavLink"] p {
    font-size: 13px !important; font-weight: 400 !important; color: var(--muted) !important; line-height: 1.35 !important;
    white-space: normal !important; overflow: visible !important; text-overflow: clip !important;
  }
  .st-key-uv_support_rail a[data-testid="stPageLink-NavLink"]:hover p { color: var(--text) !important; }
  [class*="st-key-uv_rail_link_active_"] a[data-testid="stPageLink-NavLink"] {
    border-left-color: var(--teal); background: var(--panel) !important; padding-left: 10px !important;
  }
  [class*="st-key-uv_rail_link_active_"] a[data-testid="stPageLink-NavLink"] p {
    color: var(--text) !important; font-weight: 500 !important;
  }
  .uv-toc-label { font-size: 12px; color: var(--muted); margin: 18px 0 6px 12px; }
  .uv-toc { display: flex; flex-direction: column; margin-left: 12px; border-left: 0.5px solid var(--line); }
  .uv-toc a { display: block; padding: 3px 0 3px 10px; font-size: 12px; line-height: 1.4;
    color: var(--muted); text-decoration: none; }
  .uv-toc a:hover { color: var(--text); }
  /* Section anchors land a little below the top edge. */
  .uv-anchor { display: block; scroll-margin-top: 16px; }
  /* Phone/tablet portrait: no rail (Legal shows a document select instead). */
  @media (max-width: 767px) {
    .st-key-uv_support_grid { flex-direction: column !important; gap: 16px !important; }
    .st-key-uv_support_rail, [data-testid="stLayoutWrapper"]:has(> .st-key-uv_support_rail) { display: none !important; }
    .st-key-uv_support_content, [data-testid="stLayoutWrapper"]:has(> .st-key-uv_support_content) { max-width: none !important; width: 100% !important; }
  }

  /* Long-form typography on the supporting pages: 14px / 1.65 body at a
     72ch measure, 17px H2, 12px captions — the denser end of the brand
     scale, next to the 13–13.5px data screens. Only st.markdown text, never
     widget labels. */
  .st-key-uv_support_content [data-testid="stMarkdown"] [data-testid="stMarkdownContainer"] p,
  .st-key-uv_support_content [data-testid="stMarkdown"] [data-testid="stMarkdownContainer"] li {
    font-size: 14px; line-height: 1.65; color: var(--muted); max-width: 72ch;
  }
  /* Bold lead-ins ("Same for everyone.") in --text, like the mockup's
     legal renderer. */
  .st-key-uv_support_content [data-testid="stMarkdown"] [data-testid="stMarkdownContainer"] strong { color: var(--text); font-weight: 600; }
  /* Tables in long-form documents (LG-01): a hairline box, a --panel-2
     header row in 10.5px uppercase, 12.5px muted cells. */
  .st-key-uv_support_content [data-testid="stMarkdownContainer"] table {
    border-collapse: separate !important; border-spacing: 0; width: 100%;
    border: 0.5px solid var(--line) !important; border-radius: 8px; overflow: hidden; margin: 14px 0 0;
  }
  .st-key-uv_support_content [data-testid="stMarkdownContainer"] th,
  .st-key-uv_support_content [data-testid="stMarkdownContainer"] td {
    border: none !important; padding: 11px 16px !important; text-align: left; vertical-align: top;
  }
  .st-key-uv_support_content [data-testid="stMarkdownContainer"] th {
    background: var(--panel-2); border-bottom: 0.5px solid var(--line) !important;
    font-size: 10.5px !important; font-weight: 500 !important; letter-spacing: 0.05em;
    text-transform: uppercase; color: var(--muted) !important;
  }
  .st-key-uv_support_content [data-testid="stMarkdownContainer"] td {
    font-size: 12.5px !important; line-height: 1.55; color: var(--muted) !important;
    border-bottom: 0.5px solid var(--line-2) !important;
  }
  .st-key-uv_support_content [data-testid="stMarkdownContainer"] tr:last-child td { border-bottom: none !important; }
  /* Bullets in the link colour (LG-04). */
  .st-key-uv_support_content [data-testid="stMarkdown"] li::marker { color: var(--link); }
  .uv-rail-note { font-size: 11px; color: var(--muted); line-height: 1.5; margin: 16px 0 0 12px; max-width: 188px; }
  .st-key-uv_support_content [data-testid="stMarkdown"] li { margin-bottom: 6px; }
  .st-key-uv_support_content [data-testid="stMarkdown"] h2 {
    font-size: 17px !important; font-weight: 500 !important; margin: 28px 0 8px !important; padding: 0 !important;
  }
  .st-key-uv_support_content [data-testid="stMarkdown"] h3 {
    font-size: 14px !important; font-weight: 500 !important; margin: 20px 0 6px !important; padding: 0 !important;
  }
  .st-key-uv_support_content [data-testid="stCaptionContainer"],
  .st-key-uv_support_content [data-testid="stCaptionContainer"] p { font-size: 12px !important; color: var(--muted) !important; }
  /* Card header row shared by Settings and Help: sentence case, 15px/500
     (brand §5 — no tracked uppercase). */
  .uv-card-head {
    display: flex; align-items: center; justify-content: space-between; gap: 12px;
    padding: 14px 20px; border-bottom: 0.5px solid var(--line-2);
    font-size: 15px; font-weight: 500; color: var(--text); line-height: 1.3;
  }
  .st-key-set_main { gap: 20px !important; }
  /* The profile card is one markdown block: undo Streamlit's -16px pull-up,
     which clipped its bottom padding under overflow:hidden. */
  .st-key-set_card_profile [data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }

  /* ── Settings page cards — Display/Screening & veto rules/Data,
     matching Uvalu.dc.html's Settings screen: one seamless bordered/shadowed
     panel per section (uppercase header row, then flat hairline-divided
     setting rows) instead of Streamlit's plain st.container(border=True) box
     + "##### Header" markdown, same overflow:hidden/no-padding convention as
     scr_table_card/risk_card_holdings above. */
  [class*="st-key-set_card_"] {
    background: var(--panel) !important; border-color: var(--line) !important;
    border-radius: 12px !important; box-shadow: var(--shadow) !important;
    overflow: hidden !important; padding: 0 !important;
  }
  /* Each title+control setting row — the mockup's own spec is `padding:15px
     20px`, but with the line-height fix above (real content now 38px, not
     the old inflated 43px) that read as more whitespace than the row's text
     needs; tightened to 12px top/bottom to hug the content more closely,
     matching the denser `padding:12px 20px` convention this app's other
     list-style rows already use (risk_hold_/scr_row_/pf_open_row_). Borders
     are set per-row below since which edge carries the hairline (bottom
     under the header block vs. top after the screening sliders) differs
     section to section in the spec. */
  [class*="st-key-set_row_"] { padding: 12px 20px !important; }
  /* Each row is its own st.container(key=...), so consecutive rows are
     sibling flex items in the card's vertical block and get Streamlit's
     default 16px sibling gap ON TOP of their own border/padding — invisible
     on a single row in isolation, but confirmed live it's exactly why
     Display currency/Number format read as having "extra space" compared to
     Theme: every row after the first accumulates one more of these 16px
     gaps (Theme→Currency, then Currency→Number format), even though each
     row's own height was identical the whole time. Same fix as elsewhere in
     this file (scr_table_card's margin-top pull) — cancel the gap with a
     negative margin on every row except the first one in its card (which
     has no preceding sibling row to cancel against; a negative margin there
     would instead pull it up into the header). */
  [class*="st-key-set_row_"] { margin-top: -16px !important; }
  /* Backup codes and trusted devices sit under two-factor, indented on
     --panel-2; "Sign out everywhere else" is a 12px link. */
  .st-key-set_row_backup_codes, .st-key-set_row_trusted_devices {
    margin-left: 34px !important; background: var(--panel-2) !important; border-radius: 8px !important;
  }
  .st-key-set_sessions_revoke_wrap button { min-height: 0 !important; padding: 0 !important; }
  .st-key-set_sessions_revoke_wrap button p { font-size: 12px !important; color: var(--link) !important; }
  .st-key-set_sessions_revoke_wrap button:hover p { color: var(--text) !important; }
  /* Target allocation and Import & export: label left, control right. */
  .st-key-set_targets_body textarea { max-width: 280px !important; }
  .st-key-set_targets_hhi :is([data-testid="stNumberInput"], [data-testid="stTextInput"]) {
    max-width: 110px !important; margin-left: auto;
  }
  .st-key-set_targets_save { align-items: flex-end !important; }
  /* The uploader as a compact, button-sized dropzone (it is a framework
     widget; this is the closest stable option). */
  .st-key-set_row_theme, .st-key-set_row_password {
    margin-top: 0 !important;
  }
  /* …and every card's first row, whatever its key: the row right after the
     header (Language had no top padding — the -16px pulled it under the
     header's hairline). */
  [data-testid="stElementContainer"]:has(.uv-set-head) + [data-testid="stLayoutWrapper"] > [class*="st-key-set_row_"] {
    margin-top: 0 !important;
  }
  .st-key-set_row_theme, .st-key-set_row_currency {
    border-bottom: 0.5px solid var(--line-2) !important;
  }
  .st-key-set_row_stoxx, .st-key-set_row_us {
    border-top: 0.5px solid var(--line-2) !important;
  }
  /* Security card rows — added after the border rules above were written, so
     they never got a hairline between them (confirmed live: rows ran
     together with no divider at all). Matches Uvalu Auth.dc.html frame 10's
     per-row `border-bottom:0.5px solid var(--line-2)` — every row except the
     last (Passkeys, which sits flush against the card's own bottom edge, no
     trailing divider). Backup codes/Trusted devices only render when 2FA is
     on, but Passkeys is always the true last row regardless, so this list is
     safe either way. */
  .st-key-set_row_password, .st-key-set_row_linked, .st-key-set_row_totp,
  .st-key-set_row_backup_codes, .st-key-set_row_trusted_devices {
    border-bottom: 0.5px solid var(--line-2) !important;
  }
  /* Active sessions rows — same missing-divider bug, same fix. A per-session
     dynamic key (set_row_session_<sid>) needs the substring selector, unlike
     Security's static per-row keys above. This used to deliberately skip
     both the divider and the sibling-gap cancellation (relying on
     Streamlit's own ~16px spacing instead) — reversed per direct feedback
     that the rows need visible dividers, matching Auth.dc.html frame 10's
     own per-session `border-bottom` (line 412). */
  [class*="st-key-set_row_session_"] {
    border-bottom: 0.5px solid var(--line-2) !important;
  }
  /* The generic margin-top:-16px rule above needs the same first-row
     exception set_row_theme/set_row_password get (else it pulls the first
     session row up into the "ACTIVE SESSIONS" header) — but there's no
     single static key to except here. Every child of this card's list IS a
     session row (nothing else mixed in), so :first-of-type correctly
     resolves to whichever session happens to render first, without needing
     to know its sid. */
  [class*="st-key-set_row_session_"]:first-of-type {
    margin-top: 0 !important;
  }
  /* Right-align every row's control (segmented control / toggle / select
     slider) instead of it sitting at the left edge of its own stretched
     column wrapper — same "wrapper is the real flex item" gotcha as the top
     bar's avatar button and Watchlist's Add-ticker submit button. */
  [class*="st-key-set_row_"] [data-testid="stColumn"]:last-child {
    display: flex !important; justify-content: flex-end !important;
  }
  [class*="st-key-set_row_"] [data-testid="stColumn"]:last-child [data-testid="stLayoutWrapper"],
  [class*="st-key-set_row_"] [data-testid="stColumn"]:last-child > [data-testid="stVerticalBlock"] {
    flex: none !important; width: auto !important;
  }
  /* The auto-width wrappers above shrink a selectbox to 212px, which clipped
     the region format's sample number ("Schweiz (Deutsch) — 1’234.5…").
     A fixed width (a percentage would resolve against the shrink-wrapped
     parent) that still fits the column on narrow screens. */
  [class*="st-key-set_row_i18n_"] [data-testid="stSelectbox"] {
    width: min(300px, 42vw) !important;
  }
  /* The title+desc column's generated wrapper reports a shorter height than
     the two-line raw-HTML block it actually holds — same "Streamlit
     under-reports a raw-HTML block's real height" bug documented for the
     Dashboard/Analysis/Risk pages. Since the wrapper's `overflow:visible`
     lets the real content spill out below its own undersized box instead of
     resizing it, the row's `align-items:center` centers on the WRONG
     (too-short) box, so the real text renders lower than the control beside
     it. A min-height floor matching the true content height fixes it the
     same way as an_header_row/an_hero_row's floors — 38px with the explicit
     line-height (1.3 title / 1.5 desc) set in uvalu/pages_/settings.py's
     `_row_title()`; without that explicit line-height the two lines inherit
     Streamlit's own markdown default of 1.6, measuring 43px instead — this
     number must be re-measured (not just guessed) if that line-height ever
     changes again. */
  [class*="st-key-set_row_"] [data-testid="stColumn"]:first-child {
    min-height: 38px !important;
    /* A one-line title sat at the top of the 38px floor while the control
       beside it was centred (Language, Region format, Time zone). */
    display: flex !important; flex-direction: column !important; justify-content: center !important;
  }
  [class*="st-key-set_row_"] [data-testid="stColumn"]:first-child > [data-testid="stVerticalBlock"] {
    justify-content: center !important;
  }
  /* Streamlit's markdown container carries margin-bottom:-16px, so its
     wrapper reported 22px for 38px of title + description and the centring
     above put the text 8px low. Zeroed here, the wrapper is the real height
     and the text centres on the control beside it. */
  [class*="st-key-set_row_"] [data-testid="stColumn"]:first-child [data-testid="stMarkdownContainer"] {
    margin-bottom: 0 !important;
  }
  /* Stacked rows (4-option controls under a long description): the control
     on its own line, as wide as its segments, not a full-width track. */
  .st-key-set_row_screen_style [data-testid="stButtonGroup"] {
    width: fit-content !important; margin-top: 6px !important;
  }
  /* The slider's own thumb value repeated the value already shown, larger,
     on the label row. */
  [class*="st-key-set_card_"] [data-testid="stSliderThumbValue"] { display: none !important; }
  .st-key-set_row_i18n_reset { align-items: flex-end !important; }
  /* Segmented controls (Theme/Currency/Number format/Table density) — same
     restyle as the Dashboard's db_range control: a padded panel-2 track with
     3px-gapped segments, the active one lifted with a panel background +
     shadow instead of Streamlit's default edge-to-edge bordered buttons. */
  [class*="st-key-set_row_"] [data-testid="stButtonGroup"] {
    display: flex !important; gap: 3px !important; flex-wrap: nowrap !important;
    background: var(--panel-2) !important; border-radius: 8px !important; padding: 3px !important;
  }
  /* The actual segment buttons live one level deeper than stButtonGroup
     itself, in an unstyled/unkeyed inner wrapper div Streamlit generates
     (confirmed live via its computed style) — that inner div, not
     stButtonGroup, is what actually has `flex-wrap:wrap`, so the nowrap
     above alone still let a 4-option row (Screening style, Price refresh
     interval) wrap onto two lines despite stButtonGroup itself correctly
     reporting nowrap. */
  [class*="st-key-set_row_"] [data-testid="stButtonGroup"] > div {
    flex-wrap: nowrap !important;
  }
  [class*="st-key-set_row_"] button[data-variant="segmented_control"] {
    border: none !important; border-radius: 6px !important; box-shadow: none !important;
    background: transparent !important; color: var(--muted) !important;
    font-size: 12px !important; font-weight: 500 !important;
    padding: 6px 13px !important; min-height: unset !important;
  }
  [class*="st-key-set_row_"] button[data-variant="segmented_control"][aria-checked="true"] {
    background: var(--panel) !important; color: var(--text) !important; box-shadow: var(--shadow) !important;
  }
  /* Language & region preview: one --panel-2 band with the sample values and
     the "Try a number" field inside it (design reference). */
  .st-key-set_i18n_preview_band {
    margin: 6px 20px 0 !important; padding: 12px 16px !important; width: auto !important;
    background: var(--panel-2); border-radius: 8px; gap: 12px !important;
  }
  .st-key-set_i18n_preview_band [data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }
  .st-key-set_i18n_try input { background: var(--panel) !important; font-size: 12.5px !important; }
  /* Currency codes in monospace (EUR / USD / GBP / CHF). */
  .st-key-set_row_i18n_currency button[data-variant="segmented_control"] { font-family: var(--uv-mono) !important; }
  /* Screening rules — 2x2 slider grid, matching the mockup's `padding:6px
     20px 16px` grid instead of a bare st.columns pair. Unlike the set_row_
     rows above (a seamless list of touching rows, where the native 16px
     sibling gap really was unwanted excess), this container follows a
     caption paragraph, not another row — cancelling that gap here left only
     6px between the caption text and "Max debt / equity" (confirmed live),
     reading as cramped/overlapping rather than clean. Left at its natural
     gap (16px sibling gap + this container's own 6px top padding ≈ 22px). */
  .st-key-set_slider_grid { padding: 6px 20px 16px !important; }
  /* Target allocation — added after this page's card grammar was written and
     never wired into it (confirmed live: native st.text_area/st.number_input
     labels + far-right help-icon tooltips instead of this page's own
     _row_title() header, no side padding on the two-column body, an
     unstyled default-width Save button). No exact mockup frame covers this
     card (added after both design references), so this brings it in line
     with the rest of the page's own row/card conventions instead of a
     specific pixel spec. */
  .st-key-set_targets_body { padding: 4px 20px 0 !important; }
  .st-key-set_targets_hhi { padding: 14px 20px 4px !important; }
  .st-key-set_targets_hhi [data-testid="stNumberInput"] { max-width: 180px !important; }
  .st-key-set_targets_save { padding: 6px 20px 18px !important; }
  /* Settings cards carry no padding of their own (each row pads itself), so
     the bare withholding grid sat flush on the card edge and its right-hand
     input ran past the card border. */
  .st-key-set_dividend_wh_grid { padding: 8px 20px 4px !important; box-sizing: border-box; }
  .st-key-set_wh_save { padding: 0 20px 18px !important; }
  /* Import & export: Uvalu.dc.html's two rows (15px 20px, hairline between
     them, button flush right). They use the set_row_ grammar above; only the
     padding and the divider are specific. */
  .st-key-set_row_import, .st-key-set_row_export { padding: 15px 20px !important; }
  .st-key-set_row_import { border-bottom: 0.5px solid var(--line-2) !important; }
  /* Import review (what the file holds, Add/Replace, confirm): full card
     width under the import row, closed by its own hairline. */
  .st-key-set_import_review {
    margin-top: -16px !important; padding: 15px 20px !important; gap: 10px !important;
    border-bottom: 0.5px solid var(--line-2) !important;
  }
  .st-key-set_import_add { gap: 10px !important; }
  /* Streamlit's -1rem markdown margin let the Import button ride up over
     the two-line cash note (confirmed live: 36px of text in a 20px box). */
  .st-key-set_import_review [data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }
  /* The review reads at the card's 13px, not Streamlit's 16px body size. */
  .st-key-set_import_review [data-testid="stMarkdownContainer"] :is(p, li),
  .st-key-set_import_review [data-testid="stRadio"] :is(p, label) { font-size: 13px !important; }
  .st-key-set_import_review [data-testid="stMarkdownContainer"] li { margin: 0 !important; padding: 0 !important; }
  .st-key-set_import_review [data-testid="stMarkdownContainer"] ul { margin: 0 !important; padding-left: 18px !important; }
  /* Importing replaces all portfolio data: the confirmation reads as a
     danger zone, with a red-outline confirm button. */
  .st-key-set_import_confirm {
    border: 0.5px solid var(--down-txt) !important; border-radius: 8px !important;
    background: var(--down-bg) !important; padding: 12px 14px !important; gap: 10px !important;
  }
  .st-key-imp_confirm button {
    border-color: var(--down-txt) !important; color: var(--down-txt) !important; background: transparent !important;
  }
  /* The file uploader as the design's plain "Choose .xlsx file" button,
     flush right like Download backup.xlsx. The dropzone is framework chrome
     (its own padding, 68px minimum height, dashed border, lighter native
     background, a "200MB per file" caption and, in newer Streamlit, a
     column layout that centred the button horizontally) — all of it goes;
     the button keeps only its click target. Its "Upload" text and icon are
     hidden and the translated label comes in through --uv-upload-label,
     set by the settings page. */
  .st-key-set_card_import [data-testid="stFileUploaderDropzoneInstructions"] { display: none !important; }
  .st-key-set_card_import [data-testid="stFileUploaderDropzone"] {
    min-height: 0 !important; height: auto !important; padding: 0 !important; border: 0 !important;
    background: transparent !important; align-items: flex-end !important;
  }
  .st-key-set_card_import [data-testid="stFileUploaderDropzone"] button[data-testid="stBaseButton-secondary"] {
    min-height: 0 !important; padding: 8px 14px !important; border-radius: 8px !important;
    border: 0.5px solid var(--line) !important; background: transparent !important; line-height: 1.2 !important;
  }
  .st-key-set_card_import [data-testid="stFileUploaderDropzone"] button[data-testid="stBaseButton-secondary"] > * { display: none !important; }
  .st-key-set_card_import [data-testid="stFileUploaderDropzone"] button[data-testid="stBaseButton-secondary"]::after {
    content: var(--uv-upload-label, "Choose .xlsx file"); font-size: 12.5px; color: var(--muted); white-space: nowrap;
  }
  .st-key-set_card_import [data-testid="stFileUploaderDropzone"] button[data-testid="stBaseButton-secondary"]:hover { border-color: var(--teal) !important; }
  .st-key-set_card_import [data-testid="stFileUploaderDropzone"] button[data-testid="stBaseButton-secondary"]:hover::after { color: var(--text); }
  .st-key-set_upload_label,
  [data-testid="stLayoutWrapper"]:has(> .st-key-set_upload_label) { display: none !important; }
  /* Privacy, Plan and Legal documents (Uvalu.dc.html): set_row_ rows at the
     design's 15px 20px, a hairline under every row but a card's last. */
  :is([class*="st-key-set_row_privacy_"], .st-key-set_row_plan_beta, [class*="st-key-set_row_legal_"]) {
    padding: 15px 20px !important;
  }
  :is(.st-key-set_row_privacy_export, .st-key-set_row_privacy_delete,
      .st-key-set_row_legal_terms, .st-key-set_row_legal_privacy, .st-key-set_row_legal_advice) {
    border-bottom: 0.5px solid var(--line-2) !important;
  }
  /* Delete account: the design's red-text outline button. */
  .st-key-set_row_privacy_delete button { color: var(--down-txt) !important; }
  .st-key-set_row_privacy_delete button:hover { border-color: var(--down-txt) !important; }
  .st-key-set_row_privacy_delete button * { color: inherit !important; }
  .uv-set-privacy-mail { text-align: right; white-space: nowrap; }
  .uv-set-privacy-mail a {
    font-family: var(--uv-mono); font-size: 12px; color: var(--link) !important; text-decoration: none;
  }
  .uv-set-chip-na {
    display: inline-block; font-size: 11px; font-weight: 500; padding: 3px 9px; border-radius: 6px;
    background: var(--panel-2); color: var(--muted); white-space: nowrap;
  }
  .uv-set-chip-active {
    display: inline-block; font-size: 11px; font-weight: 500; padding: 3px 9px; border-radius: 6px;
    background: var(--up-bg); color: var(--up-txt); white-space: nowrap;
  }
  /* Legal rows: "View" as the design's outline button (it is a page link). */
  [class*="st-key-set_row_legal_"] a[data-testid="stPageLink-NavLink"] {
    padding: 8px 14px !important; min-height: 0 !important; border-radius: 8px !important;
    border: 0.5px solid var(--line) !important; background: transparent !important; gap: 0 !important;
  }
  [class*="st-key-set_row_legal_"] a[data-testid="stPageLink-NavLink"] > span:has([data-testid="stIconMaterial"]) {
    display: none !important;
  }
  [class*="st-key-set_row_legal_"] a[data-testid="stPageLink-NavLink"],
  [class*="st-key-set_row_legal_"] a[data-testid="stPageLink-NavLink"] p {
    line-height: 1.3 !important;   /* inherited 32px made the button 42px tall (design ~33px) */
  }
  [class*="st-key-set_row_legal_"] a[data-testid="stPageLink-NavLink"] p {
    font-size: 12.5px !important; color: var(--muted) !important; white-space: nowrap;
  }
  [class*="st-key-set_row_legal_"] a[data-testid="stPageLink-NavLink"]:hover { border-color: var(--teal) !important; }
  [class*="st-key-set_row_legal_"] a[data-testid="stPageLink-NavLink"]:hover p { color: var(--text) !important; }
  .st-key-set_card_legal { padding-bottom: 13px !important; }
  /* The footnote sits right under the last row's hairline (design: 13px). */
  [data-testid="stElementContainer"]:has(.uv-set-legal-note) { margin-top: -16px !important; }
  /* …and Streamlit's -1rem markdown margin let it run out of the card. */
  [data-testid="stMarkdownContainer"]:has(> .uv-set-legal-note) { margin-bottom: 0 !important; }
  .uv-set-legal-note { padding: 13px 20px 0; font-size: 12px; color: var(--muted); line-height: 1.55; }
  /* Profile card's "Sign out" (top of the Account section): one raw-HTML flex
     row with the avatar and name — st.columns' per-column centring was off
     by 8px for these mismatched heights. */
  .uv-set-signout {
    display: inline-flex !important; align-items: center !important;
    box-sizing: border-box !important; height: 38px !important;
    padding: 0 14px !important; border-radius: 8px !important;
    border: 0.5px solid var(--line) !important; font-size: 12.5px !important;
    color: var(--muted) !important; cursor: pointer; text-decoration: none !important;
  }
  .uv-set-signout:hover { border-color: var(--down-txt) !important; color: var(--down-txt) !important; }

  /* ── Help page cards — Signal legend/Six fair-value models/Hard-veto
     rules/Frequently asked. Every section here is static text with no
     interactive widgets, so each card is one raw-HTML block (header + all
     rows) rendered inside a single st.container(key="help_card_...",
     border=True) rather than one st.container per row — same panel
     treatment as db_card_/an_card_/set_card_, but skips their per-row
     sibling-gap/height-underestimation fixes entirely since there's no
     widget here needing its own key. */
  [class*="st-key-help_card_"] {
    background: var(--panel) !important; border-color: var(--line) !important;
    border-radius: 12px !important; box-shadow: var(--shadow) !important;
    overflow: hidden !important; padding: 0 !important;
  }
  /* Streamlit pulls every markdown block up by 16px (margin-bottom:-1rem),
     so with overflow:hidden the card clipped the last 16px of its content —
     the cause of the old per-card min-height floors, now removed. */
  [class*="st-key-help_card_"] [data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }

  section[data-testid="stMain"] { width: 100% !important; }
  /* Legal footer always at the bottom of the screen — on short pages and
     while a page is loading, when Streamlit has cleared the old page but not
     yet sent the new one. The block container fills the scrolling stMain,
     the page's block grows into it, and the footer's wrapper takes the slack
     above it. Global, not in the footer's own <style>, which disappears with
     the footer mid-load and let the skeleton collapse onto it. */
  [data-testid="stMainBlockContainer"] { display: flex; flex-direction: column; flex: 1 0 auto; }
  [data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] { flex: 1 0 auto; }
  [data-testid="stLayoutWrapper"]:has(> .st-key-uv_footer) { margin-top: auto; }
  section[data-testid="stSidebar"][aria-expanded="true"]  ~ section[data-testid="stMain"] .block-container { padding-left: 1.5rem !important; padding-right: 1.5rem !important; }
  section[data-testid="stSidebar"][aria-expanded="false"] ~ section[data-testid="stMain"] .block-container { padding-left: 64px !important; padding-right: 1.5rem !important; padding-top: 1rem !important; }

  /* ── Sidebar — fixed width ───────────────────────────────────────────────── */
  section[data-testid="stSidebar"],
  section[data-testid="stSidebar"] > div:first-child { min-width: 220px !important; max-width: 220px !important; width: 220px !important; z-index: 100 !important; }
  section[data-testid="stSidebar"] { transition: none !important; }
  /* Fixed sidebar — no collapse/expand controls */
  [data-testid="stSidebarCollapseButton"],
  [data-testid="stExpandSidebarButton"] { display: none !important; }

  /* ── Tables ──────────────────────────────────────────────────────────────── */
  [data-testid="stDataFrame"],
  [data-testid="stDataFrameResizable"]            { width: 100% !important; }
  [data-testid="stDataFrame"] .dvn-scroller .cell-wrapper--header svg,
  [data-testid="stDataFrameResizable"] .dvn-scroller .cell-wrapper--header svg,
  .glideDataEditor .headerCellName > svg,
  .glideDataEditor [aria-label="Column menu"]     { display: none !important; }

  /* ── Metric cards ────────────────────────────────────────────────────────── */
  div[data-testid="stMetric"] {
    display: flex !important; flex-direction: column !important;
    align-items: center !important; justify-content: flex-start !important;
    height: 96px !important;
    padding: 12px 16px !important; border-radius: 12px !important;
    background: rgba(29,214,164,0.05) !important;
    border: 0.5px solid rgba(29,214,164,0.15) !important;
    text-align: center !important;
  }
  div[data-testid="stMetric"] label {
    display: flex !important; justify-content: center !important; align-items: center !important;
    gap: 4px; width: 100%; text-align: center !important;
    font-size: 0.72rem !important; font-weight: 500 !important;
    letter-spacing: 0.06em !important; text-transform: uppercase !important;
    opacity: 0.5;
  }
  div[data-testid="stMetric"] [data-testid="stMetricValue"] {
    text-align: center !important; font-size: 1.35rem !important;
    font-weight: 500 !important; letter-spacing: -0.02em !important;
    font-family: "SF Mono","Fira Code","Cascadia Code",monospace !important;
  }
  div[data-testid="stMetric"] [data-testid="stMetricDelta"] {
    justify-content: center !important; width: 100%;
  }
  [data-testid="stTabsContent"] [data-testid="stVerticalBlock"] { gap: 0 !important; }
  [data-testid="stTabsContent"] [data-testid="stColumns"]       { align-items: flex-start !important; }
  [data-testid="stTabsContent"] [data-testid="column"]          { padding-bottom: 0 !important; }
  [data-testid="stTabsContent"] [data-testid="stMetric"]{ margin-bottom: 0 !important; padding-bottom: 0.2rem !important; }
  [data-testid="stTabsContent"] [data-testid="stMetricDelta"]   { margin-bottom: 0 !important; padding-bottom: 0 !important; }

  /* ── Tabs ────────────────────────────────────────────────────────────────── */
  div[data-testid="stTabs"] > div:first-child                    { margin-bottom: 0.5rem; }
  div[data-testid="stTabsContent"]                               { padding-top: 0 !important; padding-bottom: 0 !important; }
  [data-testid="stTabsContent"] [data-testid="stVerticalBlock"]  { gap: 0.25rem !important; }
  [data-testid="stTabsContent"] hr                               { margin-top: -1.5rem !important; margin-bottom: 0.25rem !important; }
  button[data-testid="stTab"]                       { opacity: 0.5; font-weight: 500; }
  button[data-testid="stTab"]:hover                 { opacity: 0.85 !important; }
  button[data-testid="stTab"][aria-selected="true"] { opacity: 1 !important; }

  /* ── Password reveal button ─────────────────────────────────────────────── */
  [data-testid="stPasswordRevealButton"][data-testid="stPasswordRevealButton"] { background: transparent !important; background-color: transparent !important; border: none !important; box-shadow: none !important; }
  [data-testid="stPasswordRevealButton"][data-testid="stPasswordRevealButton"] svg,
  [data-testid="stPasswordRevealButton"][data-testid="stPasswordRevealButton"] svg * { color: currentColor !important; fill: currentColor !important; stroke: currentColor !important; opacity: 0.6; }
  [data-testid="stPasswordRevealButton"][data-testid="stPasswordRevealButton"]:hover svg,
  [data-testid="stPasswordRevealButton"][data-testid="stPasswordRevealButton"]:hover svg * { opacity: 1; }

  /* ── Metric delta brand colors ───────────────────────────────────────────── */
  [data-testid="stMetricDelta"] svg { display: none; }
  [data-testid="stMetricDelta"] { border-radius: 4px; padding: 1px 6px; font-size: 0.8rem !important; }
  [data-testid="stMetricDelta"][data-direction="increase"] {
    color: var(--up-txt) !important; background: var(--up-bg);
  }
  [data-testid="stMetricDelta"][data-direction="increase"]::before { content: "↑ "; }
  [data-testid="stMetricDelta"][data-direction="decrease"] {
    color: var(--down-txt) !important; background: var(--down-bg);
  }
  [data-testid="stMetricDelta"][data-direction="decrease"]::before { content: "↓ "; }

  /* ── Login page — full-bleed split panel, matching Uvalu.dc.html's LOGIN
     section. Pinned via position:fixed so it always covers the viewport
     regardless of the block-container's own padding/margins (no auth-ed
     nav/sidebar exists yet at this point, so nothing else needs to show
     through). ──────────────────────────────────────────────────────────── */
  .st-key-uv_login {
    position: fixed !important; inset: 0 !important; z-index: 9999 !important;
    background: var(--panel) !important;
  }
  /* Streamlit wraps each st.container(key=...) child of a horizontal container
     in its own auto-generated flex-item div (a hashed, unstable class) that
     sits BETWEEN the flex row and our keyed div — style that wrapper via
     :has() so height/flex-basis actually reach it, not just our inner div. */
  .st-key-uv_login > div { height: 100% !important; display: flex !important; }
  .st-key-uv_login > div:has(> .st-key-uv_login_right) {
    flex: 0 0 480px !important; max-width: 46vw !important;
  }
  .st-key-uv_login_left, .st-key-uv_login_right { height: 100% !important; width: 100% !important; }
  .st-key-uv_login_left {
    background: var(--navy) !important; color: #F5F7FA !important;
    display: flex !important; flex-direction: column !important; justify-content: space-between !important;
    padding: 48px 52px !important; position: relative !important; overflow: hidden !important;
    box-sizing: border-box !important;
  }
  .st-key-uv_login_right {
    background: var(--panel) !important; border-left: 0.5px solid var(--line) !important;
    display: flex !important; flex-direction: column !important; justify-content: center !important;
    padding: 48px 56px !important; overflow-y: auto !important; box-sizing: border-box !important;
  }
  a.uv-public-back { display: inline-block; font-size: 12px; color: var(--muted) !important;
    text-decoration: none; margin: 16px 0 6px; }
  a.uv-public-back:hover { color: var(--text) !important; }
  .uv-login-heading { font-size: 24px; font-weight: 500; letter-spacing: -0.02em; }
  .uv-login-subhead { font-size: 13px; color: var(--muted); margin-top: 4px; margin-bottom: 8px; }
  .uv-login-headline {
    font-size: 30px; font-weight: 500; letter-spacing: -0.02em; color: #F5F7FA;
    line-height: 1.25; max-width: 420px;
  }
  .uv-login-copy {
    font-size: 14px; color: rgba(245,247,250,0.55); margin-top: 16px; line-height: 1.6; max-width: 400px;
  }
  .uv-login-stats { display: flex; gap: 28px; margin-top: 32px; }
  .uv-login-stat-val { font-family: var(--uv-mono); font-size: 22px; font-weight: 500; color: var(--mint); }
  .uv-login-stat-lbl { font-size: 11px; color: rgba(245,247,250,0.5); margin-top: 3px; }
  /* The brand text fills the navy panel; the legal text sits at its bottom,
     across the panel's full width, with the stats above it. */
  .st-key-uv_login_left > [data-testid="stElementContainer"]:has(.uv-login-brand),
  .st-key-uv_login_left [data-testid="stMarkdown"]:has(.uv-login-brand),
  .st-key-uv_login_left [data-testid="stMarkdown"]:has(.uv-login-brand) > div,
  .st-key-uv_login_left [data-testid="stMarkdownContainer"]:has(.uv-login-brand) {
    flex: 1 1 auto !important; height: 100% !important; display: flex !important; flex-direction: column !important;
    margin-bottom: 0 !important;
  }
  .uv-login-brand { flex: 1 1 auto; display: flex; flex-direction: column; gap: 32px; min-height: 100%; }
  .uv-login-foot { font-size: 11px; line-height: 1.6; color: rgba(245,247,250,0.6); position: relative; z-index: 2;
    margin-top: auto; }
  .uv-login-ring {
    position: absolute; border-radius: 50%; border: 1px solid rgba(29,214,164,0.12); z-index: 1;
  }
  /* Provider-button list (Continue with Google/Microsoft) — pin the gap
     between entries to the design's 10px (Uvalu Auth.dc.html frame 01's
     `gap:10px` flex column) instead of Streamlit's larger default
     inter-element spacing. Substring selector: _render_provider_buttons()
     is called with a different key_prefix per screen (login_provider,
     login_locked_provider, invite_accept_provider), each producing its own
     "..._list" keyed container. */
  [class*="_provider_list"] { gap: 10px !important; }
  .st-key-uv_login_right div[data-testid="stTextInput"] label p {
    font-size: 11px !important; text-transform: uppercase; letter-spacing: 0.05em;
    color: var(--muted) !important; font-weight: 400 !important;
  }
  .st-key-uv_login_right div[data-testid="stTextInput"] > div {
    background: var(--panel-2) !important; border: 0.5px solid var(--line) !important;
    border-radius: 8px !important;
  }
  .st-key-uv_login_right div[data-testid="stTextInput"] input { font-size: 14px !important; }
  /* A tinted, bordered alert box — matches Uvalu Auth.dc.html frames 02/09b
     (`background:rgba(163,45,45,.12);border:.5px solid rgba(163,45,45,.3)`).
     Was plain colored text with no fill/border at all, which read as
     incidental copy rather than a distinct error on every failed-login,
     lockout, invalid-invite and invalid-reset-link message. `--down-bg`
     already carries this same rgb(163,45,45) hue at a theme-correct alpha
     (styles.py's :root/[data-theme="light"] blocks) for the fill; the
     border keeps the design's own literal alpha since there's no separate
     "--down-border" token and this hue doesn't otherwise shift by theme. */
  .uv-login-err {
    font-size: 12.5px; color: var(--down-txt); margin-top: 10px; line-height: 1.5;
    background: var(--down-bg); border: 0.5px solid rgba(163,45,45,0.3);
    border-radius: 8px; padding: 10px 12px;
  }
  .uv-lock-card {
    display: flex; align-items: center; gap: 14px; background: var(--panel-2);
    border: 0.5px solid var(--line); border-radius: 8px; padding: 16px 18px; margin-top: 18px;
  }
  .uv-lock-icon { color: var(--amber-txt); flex: none; }
  .uv-lock-timer { font-family: var(--uv-mono); font-size: 22px; font-weight: 500; color: var(--amber-txt); }
  .uv-lock-caption { font-size: 11px; color: var(--muted); margin-top: 2px; }
  .uv-login-btn-disabled {
    text-align: center; padding: 12px; border-radius: 8px; background: var(--faint);
    color: rgba(13,31,60,0.5); font-size: 13.5px; font-weight: 500; margin-top: 18px;
  }

  /* ── Misc spacing ────────────────────────────────────────────────────────── */
  div[data-testid="stMultiSelect"] { margin-bottom: 0.25rem !important; }
  .stCaption { margin-bottom: 0 !important; }

  /* ── Dialogs ─────────────────────────────────────────────────────────────── */
  [data-testid="stDialog"] [role="dialog"],
  [data-testid="stModal"] > div,
  div[aria-modal="true"],
  div[aria-label="Edit positions"] {
    max-width: 550px !important; width: 550px !important; min-width: 0 !important;
  }

  /* ── Destructive/confirm action button (Close "Confirm close", Delete, ...) ──
     Matches Uvalu.dc.html's red-filled confirm buttons on irreversible
     actions — wrap the button in st.container(key="uv_danger_btn"). */
  [class*="st-key-uv_danger_btn"] button[kind="primary"] {
    background: var(--down-txt) !important; border-color: var(--down-txt) !important;
    color: var(--navy) !important;
  }
  [class*="st-key-uv_danger_btn"] button[kind="primary"]:hover { opacity: 0.88; }
  /* Secondary "Delete" in Add/Edit dialog action rows (dialogs.dialog_actions)
     — the mockup's outline button with red text, red border + tint on hover. */
  [class*="st-key-uv_danger_btn"] button[kind="secondary"] {
    color: var(--down-txt) !important; border-color: var(--line) !important;
  }
  [class*="st-key-uv_danger_btn"] button[kind="secondary"]:hover {
    border-color: var(--down-txt) !important; background: var(--down-bg) !important;
  }

  /* ── Dashboard "Refresh" / Screener "Reset filters" buttons — matches
     Uvalu.dc.html's outline pill (border:0.5px solid var(--line);
     border-radius:8px;padding:8px 13px;font-size:12.5px;color:var(--muted),
     hover border-color:var(--teal);color:var(--text)) instead of Streamlit's
     plain tertiary-button look. */
  .st-key-db_refresh_btn button[kind="tertiary"],
  .st-key-scr_reset_btn button[kind="tertiary"] {
    display: flex !important; align-items: center !important; gap: 7px !important;
    padding: 8px 13px !important; border-radius: 8px !important;
    border: 0.5px solid var(--line) !important;
    font-size: 12.5px !important; color: var(--muted) !important;
  }
  .st-key-db_refresh_btn button[kind="tertiary"]:hover,
  .st-key-scr_reset_btn button[kind="tertiary"]:hover {
    border-color: var(--teal) !important; color: var(--text) !important;
  }

  /* Screener header buttons row (Reset filters) — Streamlit gives every
     column/block inside a horizontal container `flex:1 1 0%;width:100%` by
     default (same "wrapper is the real flex item" gotcha as the top bar's
     avatar button), so the button's wrapper tried to stretch to the FULL
     row width instead of hugging its own content. Pinning it to its own
     content width fixes it — kept even with a single child now that "Export
     list" (the other button this row used to hold) was removed, since the
     stretch-to-full-width behavior still applies to a lone child too. */
  .st-key-scr_header_btns > [data-testid="stLayoutWrapper"] {
    flex: none !important; width: auto !important;
  }

  /* ── Heading typography — brand spec ────────────────────────────────────── */
  [data-testid="stHeadingWithActionElements"] h1,
  [data-testid="stHeading"] h1 {
    font-size: 1.5rem !important; font-weight: 500 !important;
    letter-spacing: -0.02em !important; margin-bottom: 0.5rem !important;
  }
  [data-testid="stHeadingWithActionElements"] h2,
  [data-testid="stHeading"] h2 {
    font-size: 1.1rem !important; font-weight: 500 !important;
    letter-spacing: -0.01em !important; margin-bottom: 0.25rem !important;
  }
  /* Tighter dividers — color comes from the theme borderColor */
  [data-testid="stDivider"] hr, hr { margin: 8px 0 !important; }

  /* ── Captions inside cards: one footnote style (visual review G7) ──────────
     st.caption inside a card rendered at near body size (the factor-loading
     note, the risk-contribution note, the Analysis sub-score and assumptions
     notes); footnotes are 12px muted everywhere. The risk-contribution card
     has no padding of its own (rows pad themselves), so its note sat on the
     card edge — given the rows' 20px inset. */
  [class*="st-key-"][class*="_card_"] [data-testid="stCaptionContainer"],
  [class*="st-key-"][class*="_card_"] [data-testid="stCaptionContainer"] p {
    font-size: 12px !important; line-height: 1.5 !important; color: var(--muted) !important;
  }
  .st-key-risk_card_holdings [data-testid="stCaptionContainer"] { padding: 10px 20px 14px !important; }

  /* ── Admin user rows: markdown cells carried margin-bottom:-16px, so the
     row centring put them ~6px below the role select and badges. ───────── */
  [class*="st-key-admin_user_row_"] [data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }
  [class*="st-key-admin_role_"] { min-width: 104px !important; }

  /* ── Placeholders read as hints, not filled-in values (visual review G16) ── */
  input::placeholder, textarea::placeholder { color: var(--faint) !important; opacity: 1 !important; }

  /* ── Signal badges — brand v1.3 §8: one rule set on the token pairs for
     both themes (the tokens carry the light/dark difference). Fails quality
     screen is navy in light theme and slate with a hairline in dark theme, so
     the pill doesn't vanish into a navy card; No signal / No data are a grey
     wash with muted text. ─────────────────────────────────────────────── */
  .uv-badge {
    display: inline-flex; align-items: center; justify-content: center;
    height: 22px; padding: 0 9px; border-radius: 6px;
    font-size: 10.5px; font-weight: 500;   /* sentence case: descriptive labels (BDG-1) */
    white-space: nowrap; line-height: 1;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
  }
  .uv-badge-buy,     .uv-badge-ok      { background: var(--up-bg);    color: var(--up-txt); }
  .uv-badge-monitor, .uv-badge-caution { background: var(--amber-bg); color: var(--amber-txt); }
  .uv-badge-avoid,   .uv-badge-warn    { background: var(--down-bg);  color: var(--down-txt); }
  .uv-badge-veto                       { background: var(--veto-bg);  color: #FFFFFF;
                                         box-shadow: inset 0 0 0 0.5px var(--veto-line); }
  .uv-badge-neutral                    { background: var(--nosig-bg); color: var(--muted); }

  /* ── Numeric table cells never wrap mid-value ───────────────────────────────
     The st.columns tables (Portfolio open/closed/dividends, …) size columns by
     weight, so a narrow half-width card squeezed "€ 109,20" onto two lines
     ("€ 109,⏎20"). A right-aligned monospace cell is a number: keep each line
     on one line. When the column is a few px too narrow, a flex column with
     align-items:flex-end overflows on its start (left) side, into the column
     gap, instead of out of the card on the right. (Growing the column with
     min-width:max-content wrapped the whole row instead — Streamlit then
     pins the measured width, so it never recovers.) React writes these
     inline styles back as "prop: value;" with a space, hence the spelling. */
  [data-testid="stColumn"] [style*="text-align: right"][style*="font-family: var(--uv-mono)"] {
    white-space: nowrap;
    display: flex; flex-direction: column; align-items: flex-end;
  }

  /* ── Dialog key/value data rows — brand spec (monospace, right-aligned) ──── */
  [data-testid="stDialog"] [data-testid="stMarkdownContainer"] table td:last-child {
    font-family: "SF Mono","Fira Code","Cascadia Code",monospace !important;
    font-size: 0.85rem !important;
  }

  /* ── Signal provenance caption (components.provenance_bar_html) — the
     third line of the page header on Dashboard/Screener/Watchlist and under
     the ticker line in the drawer/Analysis. No fill or border; separators
     stay quiet. "Methodology →" uses the link colour like every other link
     (--link, set per theme; Sven, 11 Oct 2026 — was grey underlined). ───── */
  .uv-prov-sep { color: var(--faint); }
  [data-theme="light"] .uv-prov-sep { color: rgba(13,31,60,0.3); }
  a.uv-quiet-link, a.uv-quiet-link:visited {
    color: var(--link) !important; text-decoration: none !important; white-space: nowrap;
  }
  a.uv-quiet-link:hover { color: var(--text) !important; }
  /* REC-10: the share of covered stocks in each Screener signal pill
     (components.signal_share_label puts it in backticks). */
  .st-key-scr_signal_pills button code {
    font-family: var(--uv-mono) !important; font-size: 11px !important; color: var(--muted) !important;
    background: none !important; padding: 0 0 0 4px !important; border: none !important;
  }
  .st-key-scr_signal_pills .uv-pill-note { font-size: 11.5px; color: var(--muted); white-space: nowrap; }
  /* "Show N more": an outline button centred under the rows. */
  .st-key-scr_more { padding: 14px 20px !important; }
  .st-key-scr_more button {
    padding: 8px 14px !important; border: 0.5px solid var(--line) !important; border-radius: 8px !important;
    background: transparent !important; min-height: 0 !important;
  }
  .st-key-scr_more button p { font-size: 12.5px !important; color: var(--muted) !important; }
  .st-key-scr_more button:hover { border-color: var(--teal) !important; }
  .st-key-scr_more button:hover p { color: var(--text) !important; }

  /* ── Tooltips — one brand style for all three kinds: the app's own
     title= tooltips (uvalu/tooltips.py draws them as .uv-tip), Streamlit's
     help= tooltips (stTooltipContent) and Plotly hover labels
     (runtime.brand_hoverlabel, same colours). Light surface with navy text
     in light theme, a raised navy surface in dark theme. ───────────────── */
  :root { --tip-bg:#15305A; --tip-border:rgba(245,247,250,0.16); --tip-shadow:0 4px 16px rgba(0,0,0,0.45); }
  [data-theme="light"] { --tip-bg:#FFFFFF; --tip-border:rgba(13,31,60,0.14); --tip-shadow:0 4px 16px rgba(13,31,60,0.12); }
  .uv-tip {
    position: fixed; top: 0; left: 0; z-index: 1000000; max-width: 280px; padding: 6px 10px;
    background: var(--tip-bg); color: var(--text); border: 0.5px solid var(--tip-border); border-radius: 8px;
    box-shadow: var(--tip-shadow); pointer-events: none; opacity: 0; visibility: hidden;
    font: 400 12px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    white-space: pre-line; overflow-wrap: anywhere; transition: opacity 0.12s ease;
  }
  .uv-tip.uv-tip-on { opacity: 1; visibility: visible; }
  [data-testid="stTooltipContent"] {
    background: var(--tip-bg) !important; color: var(--text) !important;
    border: 0.5px solid var(--tip-border) !important; border-radius: 8px !important;
    box-shadow: var(--tip-shadow) !important; padding: 6px 10px !important; max-width: 280px !important;
  }
  [data-testid="stTooltipContent"] [data-testid="stMarkdownContainer"] p,
  [data-testid="stTooltipContent"] [data-testid="stMarkdownContainer"] li {
    font-size: 12px !important; line-height: 1.5 !important; color: var(--text) !important;
  }

  /* ── JS bridge iframes ───────────────────────────────────────────────────── */
  [data-testid="stIFrame"] { height: 0 !important; min-height: 0 !important; max-height: 0 !important;
    margin: 0 !important; padding: 0 !important; overflow: hidden !important; line-height: 0 !important; }
  [data-testid="stIFrame"] > div,
  [data-testid="stIFrame"] iframe { height: 0 !important; min-height: 0 !important; max-height: 0 !important;
    overflow: hidden !important; visibility: hidden !important; }
  /* …except the visible iframe buttons: Legal's "Print or save as PDF" and
     About's "Copy for support" (markdown can't carry an onclick). The rule
     above collapsed them to 0px too. */
  .st-key-legal_print [data-testid="stIFrame"], .st-key-legal_print [data-testid="stIFrame"] > div,
  .st-key-legal_print [data-testid="stIFrame"] iframe {
    height: 34px !important; max-height: none !important; visibility: visible !important; line-height: normal !important;
  }
  .st-key-about_copy [data-testid="stIFrame"], .st-key-about_copy [data-testid="stIFrame"] > div,
  .st-key-about_copy [data-testid="stIFrame"] iframe {
    height: 32px !important; max-height: none !important; visibility: visible !important; line-height: normal !important;
  }
"""


def inject() -> None:
    """Inject the global stylesheet (brand tokens, layout, widget theming)."""
    with st.container(key="uv_hidden_util_global"):
        st.markdown(f"<style>{GLOBAL_CSS}</style>", unsafe_allow_html=True)
