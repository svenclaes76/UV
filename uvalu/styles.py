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

  /* ── Screener/Watchlist filter panel — one bordered/shadowed card holding
     every filter control, matching Uvalu.dc.html's filter-bar spec
     (`background:var(--panel);border:0.5px solid var(--line);border-radius:
     12px;box-shadow:var(--shadow);padding:16px 18px`) instead of native
     widgets sitting bare on the page background. */
  .st-key-scr_filter_panel {
    background: var(--panel) !important; border-color: var(--line) !important;
    border-radius: 12px !important; box-shadow: var(--shadow) !important;
    padding: 16px 18px !important;
  }
  /* Filter row — each filter sized to its own content with a fixed 32px
     gap between, matching Uvalu.dc.html's flex-wrap filter bar instead of
     st.columns' equal-share ratios (which stretched a short "All sectors"
     select to the same width as the whole signal-chip group). Streamlit
     gives every child of a horizontal container `flex:1 1 0%;width:100%`
     by default (same gotcha as the header buttons row) — pinning each
     child's own generated wrapper to `flex:none;width:auto` is what
     actually lets it shrink to content instead of stretching. */
  .st-key-scr_filter_row { gap: 32px !important; }
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
     [data-testid="stButtonGroup"] is NOT the buttons' direct parent —
     confirmed live via outerHTML: it wraps a hidden <label> (the
     collapsed "Signal" widget label) *and* a separate nested
     [data-baseweb="button-group"] div, and the actual 4 <button>s live
     inside that inner div. Styling display/gap/flex-wrap on the outer
     stButtonGroup wrapper was a no-op for actual layout — its own
     computed `display` stayed `block` regardless — so VETO (the 4th pill)
     kept wrapping like ordinary text once it no longer fit on the line.
     The chip-track look (track background/radius/padding) and the actual
     flex/wrap behavior both belong on this inner div instead. */
  .st-key-scr_signal_pills [data-baseweb="button-group"] {
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
  .st-key-scr_signal_pills [data-testid^="stBaseButton-pills"] {
    border: none !important; border-radius: 6px !important; box-shadow: none !important;
    background: transparent !important; color: var(--muted) !important;
    font-size: 9px !important; font-weight: 400 !important;
    padding: 6px 8px !important; min-height: unset !important;
    white-space: nowrap !important;
  }
  .st-key-scr_signal_pills [data-testid="stBaseButton-pillsActive"] {
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
  [class*="st-key-scr_row_"] [data-testid="stColumn"]:nth-child(n+4),
  [class*="st-key-wl_row_"] [data-testid="stColumn"]:nth-child(n+4) {
    min-height: 21px !important;
  }

  /* ── Screener/Watchlist results table — one seamless panel (column-header
     row, then flat hairline-divided rows), matching Uvalu.dc.html's results
     table exactly instead of Streamlit's individually-boxed/gapped
     st.container(border=True) rows — same overflow:hidden/no-padding/
     row-divider convention as the Dashboard's db_holdings_card above. */
  .st-key-scr_table_card {
    background: var(--panel) !important; border-color: var(--line) !important;
    border-radius: 12px !important; box-shadow: var(--shadow) !important;
    overflow: hidden !important; padding: 0 !important;
    /* The plain default gap between these two top-level bordered containers
       measured 32px live (double the 16px rhythm used everywhere else in
       this app, e.g. the Dashboard's db_gap_ spacers) — pull it in to match. */
    margin-top: -16px !important;
  }
  .st-key-scr_col_header {
    padding: 11px 20px !important; border-bottom: 0.5px solid var(--line-2) !important;
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
  /* Filled teal submit button — matches scr_export_btn's primary-action
     treatment (the design's one filled CTA per screen): compact 8px 13px
     padding and 12.5px text instead of Streamlit's default button sizing
     (which, combined with the column stretching to fill its share of the
     row, rendered much larger/wider than every other button in the app). */
  .st-key-wl_add_form_wrap [data-testid="stFormSubmitButton"] button[kind="primaryFormSubmit"] {
    background: var(--teal) !important; border: none !important; color: #fff !important;
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
  }
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
    padding: 11px 20px !important; border-bottom: 0.5px solid var(--line-2) !important;
    /* Its columns are plain single-line <div> labels (no sortable button
       chrome the way Screener's header has) — Streamlit's own internal
       height estimate for them came back as literally 0px live (same
       under-reporting bug as the name-cell fix above), so the row's real
       23px was just its padding, not real content. min-height both fixes
       that and matches Screener's own (button-chrome-driven) 48px header
       height exactly, as requested. */
    min-height: 48px !important;
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

  /* Screener header buttons row (Reset filters / Export list) — Streamlit
     gives every column/block inside a horizontal container `flex:1 1 0%;
     width:100%` by default (same "wrapper is the real flex item" gotcha as
     the top bar's avatar button), so each button's wrapper tried to stretch
     to the FULL row width, forcing the two onto separate wrapped lines that
     read as stacked instead of side by side. Pinning both direct children
     to their own content width fixes it. */
  .st-key-scr_header_btns > [data-testid="stLayoutWrapper"] {
    flex: none !important; width: auto !important;
  }

  /* ── Screener "Export list" button — filled teal pill matching
     Uvalu.dc.html's primary action (background:var(--teal);color:#fff,
     hover background:var(--mint);color:var(--navy)). */
  .st-key-scr_export_btn button[kind="primary"] {
    border-radius: 8px !important; padding: 8px 13px !important;
    font-size: 12.5px !important; font-weight: 500 !important; border: none !important;
    background: var(--teal) !important; color: #fff !important;
  }
  .st-key-scr_export_btn button[kind="primary"]:hover {
    background: var(--mint) !important; color: var(--navy) !important;
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
