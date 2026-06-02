"""Streamlit web app — Euronext Brussels value screener + portfolio tracker."""

import math
import traceback
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from fetch_tickers import fetch_brussels_tickers
from screener import CACHE_FILE, CACHE_TTL_HOURS, _load_cache, run_screener
from portfolio import (parse_excel, save_portfolio, save_sold, save_div_hist,
                       load_portfolio, load_sold, load_div_hist, portfolio_exists,
                       PORTFOLIO_FILE, save_watchlist, load_watchlist)

def _cache_age_str() -> str:
    cache = _load_cache()
    if not cache:
        return "No cache yet"
    timestamps = [
        datetime.fromisoformat(v["fetched_at"])
        for v in cache.values()
        if v.get("fetched_at")
    ]
    if not timestamps:
        return "No cache yet"
    oldest = min(timestamps)
    age_min = (datetime.now(timezone.utc) - oldest).total_seconds() / 60
    if age_min < 60:
        return f"Cache age: {age_min:.0f} min  (TTL {CACHE_TTL_HOURS}h)"
    return f"Cache age: {age_min/60:.1f} h  (TTL {CACHE_TTL_HOURS}h)"


def _fmt_mcap(v) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    return f"€{v/1e9:.1f}B" if v >= 1e9 else f"€{v/1e6:.0f}M"


@st.cache_data(show_spinner=False)
def load_screener_data() -> pd.DataFrame:
    stocks = fetch_brussels_tickers()
    return run_screener(stocks)


def _compute_fair_values(info: dict) -> dict:
    eps  = info.get("trailingEps")
    bvps = info.get("bookValue")

    # Graham Number: √(22.5 × EPS × BVPS) — requires positive EPS and BVPS
    graham_number = None
    if eps and bvps and eps > 0 and bvps > 0:
        graham_number = round((22.5 * eps * bvps) ** 0.5, 2)

    # PE Fair Value: EPS × 15 (Graham's assumed fair P/E for a no-growth company)
    pe_fair_value = None
    if eps and eps > 0:
        pe_fair_value = round(eps * 15, 2)

    # Graham Growth: EPS × (8.5 + 2g) where g is expected annual earnings growth (%)
    # Uses earningsGrowth (TTM) as a proxy; clamped to [-5%, 25%] to avoid extremes.
    graham_growth = None
    raw_growth = info.get("earningsGrowth") or info.get("revenueGrowth")
    if eps and eps > 0 and raw_growth is not None:
        g = max(-5.0, min(25.0, raw_growth * 100))
        graham_growth = round(eps * (8.5 + 2 * g), 2)
        if graham_growth <= 0:
            graham_growth = None

    analyst_target = info.get("targetMeanPrice")

    # Composite: average of all available positive estimates
    estimates = [v for v in [graham_number, pe_fair_value, graham_growth, analyst_target]
                 if v is not None and v > 0]
    composite = round(sum(estimates) / len(estimates), 2) if estimates else None

    return {
        "graham_number": graham_number,
        "pe_fair_value": pe_fair_value,
        "graham_growth": graham_growth,
        "fair_value":    composite,
    }


@st.cache_data(show_spinner=False, ttl=60)
def _fetch_live_data(tickers: tuple) -> dict:
    result = {}
    for t in tickers:
        try:
            info = yf.Ticker(t).info
            price = info.get("currentPrice") or info.get("regularMarketPrice")
            div_rate = info.get("trailingAnnualDividendRate") or 0
            fv = _compute_fair_values(info)
            result[t] = {
                "price":          price,
                "analyst_target": info.get("targetMeanPrice"),
                "div_rate":       div_rate,
                **fv,
            }
        except Exception:
            result[t] = {
                "price": None, "analyst_target": None, "div_rate": None,
                "graham_number": None, "pe_fair_value": None,
                "graham_growth": None, "fair_value": None,
            }
    return result


# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="UV — Undervalued",
    page_icon="💎",
    layout="wide",
)

st.markdown("""
<div style="display:flex;align-items:center;gap:18px;margin-bottom:8px;">
  <svg width="56" height="56" viewBox="0 0 56 56" xmlns="http://www.w3.org/2000/svg">
    <rect width="56" height="56" rx="12" fill="#1a1d26"/>
    <text x="50%" y="54%" dominant-baseline="middle" text-anchor="middle"
          font-family="'Segoe UI',sans-serif" font-size="22" font-weight="800"
          fill="url(#g)">UV</text>
    <defs>
      <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="#4f8ef7"/>
        <stop offset="100%" stop-color="#a78bfa"/>
      </linearGradient>
    </defs>
  </svg>
  <div>
    <div style="font-size:1.8rem;font-weight:800;line-height:1.1;color:#fff;letter-spacing:-0.5px;">
      UV <span style="font-weight:300;color:#888;">· Undervalued</span>
    </div>
    <div style="font-size:0.85rem;color:#666;margin-top:2px;">
      Portfolio tracker &amp; stock screener
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

tab_portfolio, tab_screener = st.tabs(["Portfolio", "Screener"])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — VALUE SCREENER
# ══════════════════════════════════════════════════════════════════════════════

with tab_screener:
    st.caption(
        "Ranks ~125 Brussels-listed stocks by a composite value score "
        "(P/E · P/B · EV/EBITDA · Debt/Equity · Dividend Yield)."
    )

    # Cache age + refresh
    col_info, col_btn = st.columns([4, 1])
    with col_info:
        st.caption(_cache_age_str())
    with col_btn:
        if st.button("🔄 Refresh data", use_container_width=True):
            if CACHE_FILE.exists():
                CACHE_FILE.unlink()
            st.cache_data.clear()
            st.rerun()

    with st.spinner("Loading screener data…"):
        df = load_screener_data()

    watchlist = load_watchlist()

    display = pd.DataFrame({
        "★":           df["Ticker"].isin(watchlist),
        "Company":     df["Name"],
        "Ticker":      df["Ticker"],
        "Price":       df["Price"].map(lambda v: f"€{v:.2f}" if pd.notna(v) else "—"),
        "Mkt Cap":     df["Market Cap"].map(_fmt_mcap),
        "P/E":         df["trailingPE"].map(lambda v: f"{v:.1f}" if pd.notna(v) else "—"),
        "P/B":         df["priceToBook"].map(lambda v: f"{v:.2f}" if pd.notna(v) else "—"),
        "EV/EBITDA":   df["enterpriseToEbitda"].map(lambda v: f"{v:.1f}" if pd.notna(v) else "—"),
        "Debt/Equity": df["debtToEquity"].map(lambda v: f"{v:.1f}" if pd.notna(v) else "—"),
        "Div Yield":   df["dividendYield"].map(lambda v: f"{v*100:.2f}%" if pd.notna(v) else "—"),
        "Value Score": df["Value Score"],
    })

    st.markdown(f"**{len(df)}** stocks shown · check ★ to add to watchlist")
    edited = st.data_editor(
        display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "★": st.column_config.CheckboxColumn("★", width="small"),
            "Value Score": st.column_config.ProgressColumn(
                "Value Score", min_value=0, max_value=100, format="%.1f",
            ),
        },
        disabled=["Company", "Ticker", "Price", "Mkt Cap", "P/E", "P/B",
                  "EV/EBITDA", "Debt/Equity", "Div Yield", "Value Score"],
        height=700,
    )

    new_watchlist = set(edited.loc[edited["★"], "Ticker"].tolist())
    if new_watchlist != watchlist:
        save_watchlist(new_watchlist)
        st.rerun()

    with st.expander("Score distribution"):
        st.bar_chart(
            df["Value Score"].dropna()
            .value_counts(bins=10, sort=False).sort_index().rename("Count")
        )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — PORTFOLIO
# ══════════════════════════════════════════════════════════════════════════════

with tab_portfolio:

    # ── Upload (once) ─────────────────────────────────────────────────────────
    if not portfolio_exists():
        st.subheader("Import portfolio")
        st.info("Upload your Excel file once. Only open EBR: positions will be imported.")
        uploaded = st.file_uploader("Choose your portfolio .xlsx file", type=["xlsx"])
        if uploaded:
            with st.spinner("Parsing Excel…"):
                try:
                    pf, sold, div_hist = parse_excel(uploaded)
                    if pf.empty:
                        st.error("No open EBR: positions found. Check that your file matches the expected format.")
                    else:
                        save_portfolio(pf)
                        save_sold(sold)
                        save_div_hist(div_hist)
                        st.success(f"Imported {len(pf)} open, {len(sold)} sold, {len(div_hist)} dividend records. Reloading…")
                        st.rerun()
                except Exception as e:
                    st.error(f"Could not parse file: {e}")
                    st.code(traceback.format_exc())
        st.stop()

    # ── Load saved portfolio ───────────────────────────────────────────────────
    pf = load_portfolio()
    if pf is None or pf.empty:
        st.error("Portfolio file is empty or corrupted.")
        if st.button("Remove and re-upload"):
            PORTFOLIO_FILE.unlink(missing_ok=True)
            st.rerun()
        st.stop()

    # ── Fetch live prices ─────────────────────────────────────────────────────
    with st.spinner("Fetching live prices & fair value estimates…"):
        live_data = _fetch_live_data(tuple(pf["ticker"].tolist()))

    pf["live_price"]      = pf["ticker"].map(lambda t: live_data[t]["price"])
    pf["analyst_target"]  = pf["ticker"].map(lambda t: live_data[t]["analyst_target"])
    pf["graham_number"]   = pf["ticker"].map(lambda t: live_data[t]["graham_number"])
    pf["pe_fair_value"]   = pf["ticker"].map(lambda t: live_data[t]["pe_fair_value"])
    pf["graham_growth"]   = pf["ticker"].map(lambda t: live_data[t]["graham_growth"])
    pf["fair_value"]      = pf["ticker"].map(lambda t: live_data[t]["fair_value"])
    pf["div_rate"]        = pf["ticker"].map(lambda t: live_data[t]["div_rate"] or 0)
    pf["expected_annual"] = (pf["div_rate"] * pf["shares"]).round(2)
    pf["current_value"]   = pf["live_price"] * pf["shares"]
    pf["price_gain"]      = pf["current_value"] - pf["purchase_value"]
    pf["price_gain_pct"]  = (pf["price_gain"] / pf["purchase_value"] * 100).round(2)
    pf["total_return"]    = pf["price_gain"] + pf["dividends"].fillna(0)
    pf["total_return_pct"] = (pf["total_return"] / pf["purchase_value"] * 100).round(2)
    pf["upside_pct"]      = ((pf["analyst_target"] - pf["live_price"]) / pf["live_price"] * 100).round(1)
    pf["fv_upside_pct"]   = ((pf["fair_value"] - pf["live_price"]) / pf["live_price"] * 100).round(1)

    # Attach screener value score
    screener_scores = load_screener_data().set_index("Ticker")["Value Score"].to_dict()
    pf["value_score"] = pf["ticker"].map(screener_scores)

    # ── Summary cards (shared across both sub-tabs) ───────────────────────────
    total_invested   = pf["purchase_value"].sum()
    total_current    = pf["current_value"].sum()
    total_dividends  = pf["dividends"].fillna(0).sum()
    total_return     = total_current - total_invested + total_dividends
    total_return_pct = total_return / total_invested * 100 if total_invested else 0
    total_expected   = pf["expected_annual"].sum()

    st.subheader("Portfolio summary")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Invested",        f"€{total_invested:,.0f}")
    c2.metric("Current value",   f"€{total_current:,.0f}",
              delta=f"€{total_current - total_invested:+,.0f}")
    c3.metric("Price gain",      f"€{total_current - total_invested:+,.0f}",
              delta=f"{(total_current - total_invested) / total_invested * 100:+.1f}%")
    c4.metric("Dividends received", f"€{total_dividends:,.0f}")
    c5.metric("Total return",    f"€{total_return:+,.0f}",
              delta=f"{total_return_pct:+.1f}%")

    st.divider()

    sub_positions, sub_watchlist, sub_dividends, sub_sold = st.tabs(["Positions", "Watchlist", "Dividends", "Sold"])

    # ── Sub-tab: Positions ────────────────────────────────────────────────────
    with sub_positions:
        st_autorefresh(interval=60_000, key="portfolio_refresh")
        positions = pd.DataFrame({
            "Company":        pf["name"],
            "Ticker":         pf["ticker"],
            "Shares":         pf["shares"].map(lambda v: f"{v:.0f}" if pd.notna(v) else "—"),
            "Live Price":     pf["live_price"].map(lambda v: f"€{v:.2f}" if pd.notna(v) else "—"),
            "Fair Value":     pf["fair_value"].map(lambda v: f"€{v:.2f}" if pd.notna(v) else "—"),
            "FV Upside":      pf["fv_upside_pct"].map(lambda v: f"{v:+.1f}%" if pd.notna(v) else "—"),
            "Analyst Target": pf["analyst_target"].map(lambda v: f"€{v:.2f}" if pd.notna(v) else "—"),
            "Invested":       pf["purchase_value"].map(lambda v: f"€{v:,.0f}" if pd.notna(v) else "—"),
            "Current":        pf["current_value"].map(lambda v: f"€{v:,.0f}" if pd.notna(v) else "—"),
            "Price Gain %":   pf["price_gain_pct"],
            "Total Return %": pf["total_return_pct"],
            "Value Score":    pf["value_score"],
            "Buy Date":       pd.to_datetime(pf["date_in"]).dt.strftime("%d-%m-%Y").fillna("—"),
        })

        st.dataframe(
            positions,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Price Gain %":   st.column_config.NumberColumn("Price Gain %",   format="%.2f%%"),
                "Total Return %": st.column_config.NumberColumn("Total Return %", format="%.2f%%"),
                "Value Score":    st.column_config.ProgressColumn(
                    "Value Score", min_value=0, max_value=100, format="%.1f"),
            },
            height=(len(pf) + 1) * 35 + 10,
        )

        st.divider()
        ch1, ch2 = st.columns(2)
        with ch1:
            st.subheader("P&L per position")
            st.bar_chart(pf.set_index("name")["price_gain"].dropna().sort_values())
        with ch2:
            st.subheader("Portfolio allocation")
            st.bar_chart(pf.set_index("name")["current_value"].dropna().sort_values(ascending=False))

    # ── Sub-tab: Watchlist ────────────────────────────────────────────────────
    with sub_watchlist:
        wl_tickers = load_watchlist()
        if not wl_tickers:
            st.info("No stocks on your watchlist yet. Check ★ next to any stock in the Screener tab to add it.")
        else:
            screener_df = load_screener_data().set_index("Ticker")
            with st.spinner("Fetching live data for watchlist…"):
                wl_live = _fetch_live_data(tuple(sorted(wl_tickers)))

            rows = []
            for ticker in sorted(wl_tickers):
                s = screener_df.loc[ticker] if ticker in screener_df.index else {}
                live = wl_live.get(ticker, {})
                price = live.get("price")
                fv    = live.get("fair_value")
                rows.append({
                    "Ticker":         ticker,
                    "Company":        s.get("Name", ticker) if hasattr(s, "get") else ticker,
                    "Live Price":     f"€{price:.2f}" if price else "—",
                    "Fair Value":     f"€{fv:.2f}" if fv else "—",
                    "FV Upside":      f"{(fv - price) / price * 100:+.1f}%" if fv and price else "—",
                    "Analyst Target": f"€{live['analyst_target']:.2f}" if live.get("analyst_target") else "—",
                    "P/E":            f"{s['trailingPE']:.1f}" if hasattr(s, "get") and pd.notna(s.get("trailingPE")) else "—",
                    "P/B":            f"{s['priceToBook']:.2f}" if hasattr(s, "get") and pd.notna(s.get("priceToBook")) else "—",
                    "Div Yield":      f"{s['dividendYield']*100:.2f}%" if hasattr(s, "get") and pd.notna(s.get("dividendYield")) else "—",
                    "Value Score":    s.get("Value Score") if hasattr(s, "get") else None,
                })

            wl_df = pd.DataFrame(rows)
            st.dataframe(
                wl_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Value Score": st.column_config.ProgressColumn(
                        "Value Score", min_value=0, max_value=100, format="%.1f"),
                },
            )

    # ── Sub-tab: Dividends ────────────────────────────────────────────────────
    with sub_dividends:
        div_hist = load_div_hist()
        if div_hist is not None and not div_hist.empty:
            div_hist["amount"] = pd.to_numeric(div_hist["amount"], errors="coerce")
            div_hist["date"]   = pd.to_datetime(div_hist["date"], errors="coerce")
            total_hist = div_hist["amount"].sum()
        else:
            total_hist = total_dividends

        d1, d2, d3, d4 = st.columns(4)
        d1.metric("Total received (history)", f"€{total_hist:,.2f}")
        d2.metric("Current holdings received", f"€{total_dividends:,.2f}")
        d3.metric("Expected next 12 mths",     f"€{total_expected:,.2f}")
        d4.metric("Portfolio yield",
                  f"{total_expected / total_current * 100:.2f}%" if total_current else "—")

        st.divider()

        # Per-position summary for current holdings
        st.subheader("Current holdings — dividend summary")
        _gross = pf["dividends"].fillna(0)
        _tax   = (_gross * 0.30).round(2)
        _net   = (_gross - _tax).round(2)
        div_table = pd.DataFrame({
            "Company":   pf["name"],
            "Ticker":    pf["ticker"],
            "Shares":    pf["shares"].map(lambda v: f"{v:.0f}" if pd.notna(v) else "—"),
            "Div/Share": pf["div_rate"].map(lambda v: f"€{v:.4f}" if pd.notna(v) and v else "—"),
            "Gross":     _gross.map(lambda v: f"€{v:,.2f}" if pd.notna(v) else "—"),
            "Tax (30%)": _tax.map(lambda v: f"€{v:,.2f}" if pd.notna(v) else "—"),
            "Net":       _net.map(lambda v: f"€{v:,.2f}" if pd.notna(v) else "—"),
            "Date":      pd.to_datetime(pf["date_in"]).dt.strftime("%d-%m-%Y").fillna("—"),
        })
        st.dataframe(div_table, use_container_width=True, hide_index=True,
                     height=(len(pf) + 1) * 35 + 10)

        st.divider()

        # Full dividend payment history
        if div_hist is not None and not div_hist.empty:
            st.subheader("Dividend history")

            years = sorted(div_hist["date"].dt.year.dropna().unique().astype(int), reverse=True)
            year_options = ["All"] + years
            default_idx = year_options.index(datetime.now().year) if datetime.now().year in year_options else 0
            selected_year = st.selectbox("Filter by year", year_options, index=default_idx, key="div_year_filter")

            hist_table = div_hist.copy()
            if selected_year != "All":
                hist_table = hist_table[hist_table["date"].dt.year == selected_year]
            hist_table = hist_table.sort_values("date", ascending=True)
            hist_shares = pd.to_numeric(hist_table.get("shares"), errors="coerce") if "shares" in hist_table.columns else None
            div_per_share = (hist_table["amount"] / hist_shares).round(4) if hist_shares is not None else None
            TAX_RATE = 0.30
            gross = hist_table["amount"]
            tax   = (gross * TAX_RATE).round(2)
            net   = (gross - tax).round(2)
            hist_display = pd.DataFrame({
                "Company":   hist_table["name"],
                "Ticker":    hist_table["ticker"],
                "Shares":    hist_shares.map(lambda v: f"{v:.0f}" if pd.notna(v) else "—") if hist_shares is not None else "—",
                "Div/Share": div_per_share.map(lambda v: f"€{v:.4f}" if pd.notna(v) else "—") if div_per_share is not None else "—",
                "Gross":     gross.map(lambda v: f"€{v:,.2f}" if pd.notna(v) else "—"),
                "Tax (30%)": tax.map(lambda v: f"€{v:,.2f}" if pd.notna(v) else "—"),
                "Net":       net.map(lambda v: f"€{v:,.2f}" if pd.notna(v) else "—"),
                "Date":      hist_table["date"].dt.strftime("%d-%m-%Y"),
            })
            st.dataframe(hist_display, use_container_width=True, hide_index=True,
                         height=(len(hist_display) + 1) * 35 + 10)

            st.divider()
            ch3, ch4 = st.columns(2)
            with ch3:
                st.subheader("Total received per stock")
                st.bar_chart(
                    div_hist.groupby("name")["amount"].sum().sort_values(ascending=False)
                )
            with ch4:
                st.subheader("Dividends by year")
                by_year = div_hist.copy()
                by_year["year"] = by_year["date"].dt.year
                st.bar_chart(by_year.groupby("year")["amount"].sum())
        else:
            st.info("Re-upload your Excel file to load full dividend history.")

    # ── Sub-tab: Sold ─────────────────────────────────────────────────────────
    with sub_sold:
        sold = load_sold()
        if sold is None or sold.empty:
            st.info("No sold EBR: positions found in your portfolio file.")
        else:
            sold["price_gain"]     = pd.to_numeric(sold["sale_value"], errors="coerce") - pd.to_numeric(sold["purchase_value"], errors="coerce")
            sold["price_gain_pct"] = (sold["price_gain"] / pd.to_numeric(sold["purchase_value"], errors="coerce") * 100).round(2)
            sold["dividends"]      = pd.to_numeric(sold["dividends"], errors="coerce").fillna(0)
            sold["total_return"]   = sold["price_gain"] + sold["dividends"]
            sold["total_return_pct"] = (sold["total_return"] / pd.to_numeric(sold["purchase_value"], errors="coerce") * 100).round(2)
            sold["held_days"]      = (pd.to_datetime(sold["date_out"]) - pd.to_datetime(sold["date_in"])).dt.days

            # Summary cards
            s1, s2, s3, s4 = st.columns(4)
            s1.metric("Positions sold",   len(sold))
            s2.metric("Total invested",   f"€{pd.to_numeric(sold['purchase_value'], errors='coerce').sum():,.0f}")
            s3.metric("Total proceeds",   f"€{pd.to_numeric(sold['sale_value'], errors='coerce').sum():,.0f}")
            s4.metric("Total realised return", f"€{sold['total_return'].sum():+,.0f}",
                      delta=f"{sold['total_return'].sum() / pd.to_numeric(sold['purchase_value'], errors='coerce').sum() * 100:+.1f}%")

            st.divider()

            sold_table = pd.DataFrame({
                "Company":         sold["name"],
                "Ticker":          sold["ticker"],
                "Shares":          pd.to_numeric(sold["shares"], errors="coerce").map(lambda v: f"{v:.0f}" if pd.notna(v) else "—"),
                "Invested":        pd.to_numeric(sold["purchase_value"], errors="coerce").map(lambda v: f"€{v:,.0f}" if pd.notna(v) else "—"),
                "Proceeds":        pd.to_numeric(sold["sale_value"], errors="coerce").map(lambda v: f"€{v:,.0f}" if pd.notna(v) else "—"),
                "Price Gain":      sold["price_gain"].map(lambda v: f"€{v:+,.0f}" if pd.notna(v) else "—"),
                "Price Gain %":    sold["price_gain_pct"],
                "Dividends":       sold["dividends"].map(lambda v: f"€{v:,.0f}"),
                "Total Return %":  sold["total_return_pct"],
                "Held (days)":     sold["held_days"].map(lambda v: f"{v:.0f}" if pd.notna(v) else "—"),
                "Buy Date":        pd.to_datetime(sold["date_in"]).dt.strftime("%d-%m-%Y").fillna("—"),
                "Sell Date":       pd.to_datetime(sold["date_out"]).dt.strftime("%d-%m-%Y").fillna("—"),
            })

            st.dataframe(
                sold_table,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Price Gain %":   st.column_config.NumberColumn("Price Gain %",   format="%.2f%%"),
                    "Total Return %": st.column_config.NumberColumn("Total Return %", format="%.2f%%"),
                },
                height=(len(sold) + 1) * 35 + 10,
            )

            st.divider()
            st.subheader("Realised return per position")
            st.bar_chart(sold.set_index("name")["total_return"].sort_values())

    # ── Re-upload option ──────────────────────────────────────────────────────
    st.divider()
    with st.expander("Re-upload portfolio file"):
        st.warning("This will replace your current portfolio data.")
        new_file = st.file_uploader("Upload new .xlsx", type=["xlsx"], key="reupload")
        if new_file:
            try:
                new_pf, new_sold, new_div_hist = parse_excel(new_file)
                if new_pf.empty:
                    st.error("No open EBR: positions found.")
                else:
                    save_portfolio(new_pf)
                    save_sold(new_sold)
                    save_div_hist(new_div_hist)
                    st.cache_data.clear()
                    st.success(f"Portfolio updated with {len(new_pf)} positions.")
                    st.rerun()
            except Exception as e:
                st.error(f"Could not parse file: {e}")
