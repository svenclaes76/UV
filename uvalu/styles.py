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
    --up-bg:rgba(29,214,164,0.14); --up-txt:#1DD6A4;
    --down-bg:rgba(163,45,45,0.26); --down-txt:#F0A6A6;
    --amber-bg:rgba(214,158,29,0.16); --amber-txt:#E0B94D;
    --grid:rgba(255,255,255,0.06); --axis:rgba(245,247,250,0.5);
    --tile:#0B1D3D; --shadow:0 1px 2px rgba(0,0,0,0.4);
  }
  [data-theme="light"] {
    --bg:#EAEEF3; --panel:#FFFFFF; --panel-2:#F5F7FA; --soft:rgba(29,214,164,0.055);
    --line:rgba(13,31,60,0.10); --line-2:rgba(13,31,60,0.06);
    --text:#0D1F3C; --muted:#5F5E5A; --faint:rgba(13,31,60,0.38);
    --up-bg:rgba(15,110,86,0.11); --up-txt:#0F6E56;
    --down-bg:rgba(163,45,45,0.11); --down-txt:#A32D2D;
    --grid:rgba(13,31,60,0.08); --axis:#5F5E5A;
    --tile:#F5F7FA; --shadow:0 1px 3px rgba(13,31,60,0.08);
  }

  /* ── Subheader spacing ───────────────────────────────────────────────────── */
  [data-testid="stHeadingWithActionElements"] { margin-top: 0.5rem !important; margin-bottom: 0.15rem !important; padding: 0 !important; }
  [data-testid="stHeadingWithActionElements"] h3 { margin: 0 !important; padding: 0 !important; font-size: 1.1rem !important; line-height: 1.3 !important; }

  /* ── Page transitions ────────────────────────────────────────────────────── */
  .block-container { animation: uvFadeIn 0.18s ease; }
  @keyframes uvFadeIn { from { opacity: 0; } to { opacity: 1; } }

  /* ── Chrome cleanup ──────────────────────────────────────────────────────── */
  [data-testid="stDecoration"] { display: none !important; }
  header[data-testid="stHeader"] { background: transparent !important; border-bottom: none !important; }

  /* ── Layout ──────────────────────────────────────────────────────────────── */
  .block-container {
    padding-top: 0 !important; padding-bottom: 0.5rem !important; max-width: 100% !important;
    padding-left: 1.5rem !important; padding-right: 1.5rem !important;
  }

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
    padding: 16px 20px 20px !important; border-bottom: 0.5px solid var(--line-2) !important;
  }
  .st-key-db_holdings_colheader {
    padding: 9px 20px !important; border-bottom: 0.5px solid var(--line-2) !important;
    /* Same Streamlit height-underestimation as the db_hold_ rows below (see
       that rule's comment) — the header's own markdown grid measured
       shorter than its real content, so once row0 was pulled flush against
       it (0px gap, by design), row0's divider visibly crossed through the
       header's own overflowing label text. min-height stops the box from
       under-reporting; confirmed live it now matches the real content
       exactly (9px top/bottom padding either side of the label row). */
    min-height: 34px !important;
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
    align-items: stretch !important; gap: 16px !important;
  }
  [data-testid="stLayoutWrapper"]:has(> [class*="st-key-db_card_"]) {
    flex: 1 1 auto !important;
  }
  [class*="st-key-db_card_"] { flex: 1 1 auto !important; width: 100% !important; }

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
  .st-key-db_range [data-testid^="stBaseButton-segmented_control"] {
    border: none !important; border-radius: 6px !important; box-shadow: none !important;
    background: transparent !important; color: var(--muted) !important;
    font-family: var(--uv-mono) !important; font-size: 11.5px !important; font-weight: 500 !important;
    padding: 5px 11px !important; min-height: unset !important;
  }
  .st-key-db_range [data-testid="stBaseButton-segmented_controlActive"] {
    background: var(--panel) !important; color: var(--text) !important; box-shadow: var(--shadow) !important;
  }

  /* ── Dashboard benchmark toggle chips (S&P 500 / Euro Stoxx 50) — same
     idea as the range control above: st.pills' default look (fully
     rounded 9999px pill, gray fill, 14px sans text) doesn't match
     Uvalu.dc.html's benchChip spec (uvalu_dc.html ~line 2140): a 6px
     rounded chip, 11px text, transparent/muted when off and a teal
     border + var(--soft) tint + full-text color when on. */
  .st-key-db_bench_pills [data-testid^="stBaseButton-pills"] {
    border-radius: 6px !important; padding: 4px 9px !important; font-size: 11px !important;
    background: transparent !important; border: 0.5px solid var(--line) !important; color: var(--muted) !important;
  }
  .st-key-db_bench_pills [data-testid="stBaseButton-pillsActive"] {
    background: var(--soft) !important; border-color: var(--teal) !important; color: var(--text) !important;
  }

  /* ── Table density (Settings → Display → Table density) ──────────────────
     Only affects card-based row lists built from raw HTML/st.container (e.g.
     Dashboard's holdings rows) — native st.dataframe tables render to a
     canvas (glide-data-grid) whose row height is set in Python per call and
     can't be restyled from CSS, so this intentionally doesn't touch them. */
  [data-density="compact"] [class*="st-key-db_hold_"] { padding: 4px 8px !important; }

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

  /* ── Risk page — income toggle right-aligned ─────────────────────────────── */
  .st-key-risk_income_toggle { display: flex !important; justify-content: flex-end !important; align-items: center !important; }
  [data-testid="stColumn"]:has(.st-key-risk_income_toggle) { padding-right: 0 !important; }
  section[data-testid="stMain"] { width: 100% !important; }
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
    color: #1DD6A4 !important; background: rgba(29,214,164,0.12);
  }
  [data-testid="stMetricDelta"][data-direction="increase"]::before { content: "↑ "; }
  [data-testid="stMetricDelta"][data-direction="decrease"] {
    color: #F5B5B5 !important; background: rgba(163,45,45,0.20);
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
  .uv-login-heading { font-size: 22px; font-weight: 500; letter-spacing: -0.02em; }
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
  .uv-login-foot { font-size: 11px; color: rgba(245,247,250,0.35); position: relative; z-index: 2; }
  .uv-login-ring {
    position: absolute; border-radius: 50%; border: 1px solid rgba(29,214,164,0.12); z-index: 1;
  }
  .st-key-uv_login_right div[data-testid="stTextInput"] label p {
    font-size: 11px !important; text-transform: uppercase; letter-spacing: 0.05em;
    color: var(--faint) !important; font-weight: 400 !important;
  }
  .st-key-uv_login_right div[data-testid="stTextInput"] > div {
    background: var(--panel-2) !important; border: 0.5px solid var(--line) !important;
    border-radius: 9px !important;
  }
  .st-key-uv_login_right div[data-testid="stTextInput"] input { font-size: 14px !important; }
  .uv-login-err { font-size: 12px; color: var(--down-txt); margin-top: 6px; }

  /* ── Misc spacing ────────────────────────────────────────────────────────── */
  div[data-testid="stMultiSelect"] { margin-bottom: 0.25rem !important; }
  .stCaption { margin-bottom: 0 !important; }

  /* ── Sidebar logo + footer ───────────────────────────────────────────────── */
  .uv-logo      { display: flex; align-items: center; gap: 10px; padding: 0 4px 20px; margin-top: -1.8rem; }
  .uv-logo-wordmark {
    font-size: 1.4rem; font-weight: 500; letter-spacing: -0.03em;
    line-height: 1;
  }
  .uv-logo-accent { color: #1A8C6E; }
  .uv-logo-sub  { font-size: 0.65rem; opacity: 0.3; margin-top: 3px; }
  .uv-bottom    {
    position: fixed; bottom: 0; left: 0; width: 220px; padding: 10px 16px 15px;
    background: transparent;
    border-top: 0.5px solid rgba(128,128,128,0.20); box-sizing: border-box;
  }
  .uv-bottom-email { font-size: 0.7rem; opacity: 0.4; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 3px; }
  .uv-logout {
    display: inline-flex; align-items: center;
    padding: 0 12px; height: 30px; line-height: 30px;
    font-size: 0.78rem; font-weight: 400;
    color: inherit !important; text-decoration: none !important;
    border: 0.5px solid rgba(128,128,128,0.35); border-radius: 6px;
    background: transparent; transition: border-color 0.12s, opacity 0.12s;
    white-space: nowrap; flex-shrink: 0;
  }
  .uv-logout:hover { border-color: rgba(29,214,164,0.5); color: #1DD6A4 !important; }

  /* ── Dialogs ─────────────────────────────────────────────────────────────── */
  [data-testid="stDialog"] [role="dialog"],
  [data-testid="stModal"] > div,
  div[aria-modal="true"],
  div[aria-label="Edit positions"] {
    max-width: 550px !important; width: 550px !important; min-width: 0 !important;
  }

  /* ── Destructive/confirm action button (Sell "Confirm sale", Delete, ...) ──
     Matches Uvalu.dc.html's red-filled confirm buttons on irreversible
     actions — wrap the button in st.container(key="uv_danger_btn"). */
  .st-key-uv_danger_btn button[kind="primary"] {
    background: var(--down-txt) !important; border-color: var(--down-txt) !important;
    color: var(--navy) !important;
  }
  .st-key-uv_danger_btn button[kind="primary"]:hover { opacity: 0.88; }

  /* ── Dashboard "Refresh" button — matches Uvalu.dc.html's outline pill
     (border:0.5px solid var(--line);border-radius:8px;padding:8px 13px;
     font-size:12.5px;color:var(--muted), hover border-color:var(--teal);
     color:var(--text)) instead of Streamlit's plain tertiary-button look. */
  .st-key-db_refresh_btn button[kind="tertiary"] {
    display: flex !important; align-items: center !important; gap: 7px !important;
    padding: 8px 13px !important; border-radius: 8px !important;
    border: 0.5px solid var(--line) !important;
    font-size: 12.5px !important; color: var(--muted) !important;
  }
  .st-key-db_refresh_btn button[kind="tertiary"]:hover {
    border-color: var(--teal) !important; color: var(--text) !important;
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

  /* ── Signal badges — brand spec (uv-badge-*) ────────────────────────────── */
  .uv-badge {
    display: inline-flex; align-items: center; justify-content: center;
    min-width: 46px; height: 22px; padding: 0 8px; border-radius: 6px;
    font-size: 11px; font-weight: 500; text-transform: uppercase;
    letter-spacing: 0.02em; white-space: nowrap; line-height: 1;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
  }
  .uv-badge-buy,     .uv-badge-ok      { background: var(--uv-pos-bg); color: var(--uv-pos-txt); }
  .uv-badge-monitor, .uv-badge-caution { background: var(--uv-cau-bg); color: var(--uv-cau-txt); }
  .uv-badge-avoid,   .uv-badge-warn    { background: var(--uv-neg-bg); color: var(--uv-neg-txt); }
  .uv-badge-veto                       { background: #0D1F3C; color: #FFFFFF; }
  .uv-badge-neutral                    { background: rgba(128,128,128,0.15); color: var(--uv-muted); }

  /* ── Dialog key/value data rows — brand spec (monospace, right-aligned) ──── */
  [data-testid="stDialog"] [data-testid="stMarkdownContainer"] table td:last-child {
    font-family: "SF Mono","Fira Code","Cascadia Code",monospace !important;
    font-size: 0.85rem !important;
  }

  /* ── JS bridge iframes ───────────────────────────────────────────────────── */
  [data-testid="stIFrame"] { height: 0 !important; min-height: 0 !important; max-height: 0 !important;
    margin: 0 !important; padding: 0 !important; overflow: hidden !important; line-height: 0 !important; }
  [data-testid="stIFrame"] > div,
  [data-testid="stIFrame"] iframe { height: 0 !important; min-height: 0 !important; max-height: 0 !important;
    overflow: hidden !important; visibility: hidden !important; }
"""


def inject() -> None:
    """Inject the global stylesheet (brand tokens, layout, widget theming)."""
    with st.container(key="uv_hidden_util_global"):
        st.markdown(f"<style>{GLOBAL_CSS}</style>", unsafe_allow_html=True)
