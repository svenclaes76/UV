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
  .block-container { padding-top: 0.25rem !important; padding-bottom: 0.5rem !important; max-width: 100% !important; }

  /* ── Mockup canvas background — every page now sits on --bg, matching the
     top bar (uvalu/shell.py) and the raw-HTML mockup-token cards each screen
     is adopting (Dashboard first, Phase 3.1) ──────────────────────────────── */
  section[data-testid="stMain"] { background: var(--bg) !important; }

  /* ── Dashboard holdings rows — dark-panel card per position, matching the
     mockup's "Holdings · price vs fair value" table (uvalu/pages_/dashboard.py) */
  [class*="st-key-db_hold_"] {
    background: var(--panel) !important; border-color: var(--line) !important;
    border-radius: 10px !important;
  }

  /* ── Table density (Settings → Display → Table density) ──────────────────
     Only affects card-based row lists built from raw HTML/st.container (e.g.
     Dashboard's holdings rows) — native st.dataframe tables render to a
     canvas (glide-data-grid) whose row height is set in Python per call and
     can't be restyled from CSS, so this intentionally doesn't touch them. */
  [data-density="compact"] [class*="st-key-db_hold_"] { padding: 4px 8px !important; }

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

  /* ── Login page ──────────────────────────────────────────────────────────── */
  .login-wrap {
    display: flex; flex-direction: column; align-items: center;
    margin: 64px auto 32px;
  }
  .uv-wordmark {
    font-size: 2.6rem; font-weight: 500; letter-spacing: -0.03em;
    margin-bottom: 8px; line-height: 1;
  }
  .uv-wordmark-accent { color: #1A8C6E; }
  .login-sub { font-size: 0.82rem; opacity: 0.4; margin-bottom: 4px; }

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
    st.markdown(f"<style>{GLOBAL_CSS}</style>", unsafe_allow_html=True)
