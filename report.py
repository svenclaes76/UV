"""Generates an HTML report from the screener results."""

import math
import pandas as pd
from datetime import datetime


def _fmt(val, pct=False, decimals=2):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return '<span class="na">—</span>'
    if pct:
        return f"{val * 100:.2f}%"
    if isinstance(val, float):
        return f"{val:,.{decimals}f}"
    if isinstance(val, int):
        return f"{val:,}"
    return str(val)


def _market_cap_fmt(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return '<span class="na">—</span>'
    if val >= 1e9:
        return f"{val/1e9:.1f}B"
    if val >= 1e6:
        return f"{val/1e6:.0f}M"
    return f"{val:,.0f}"


def _score_color(score):
    """Green for high scores, red for low."""
    if math.isnan(score):
        return "#888"
    r = int(255 * (1 - score / 100))
    g = int(200 * (score / 100))
    return f"rgb({r},{g},60)"


def generate_html(df: pd.DataFrame, output_path: str = "report.html"):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    rows_html = []
    for rank, row in df.iterrows():
        score = row["Value Score"]
        color = _score_color(score if not math.isnan(score) else 50)
        rows_html.append(f"""
        <tr>
          <td class="rank">{rank}</td>
          <td class="name">{row['Name']}<br><span class="ticker">{row['Ticker']}</span></td>
          <td>{_fmt(row.get('Price'), decimals=2)} <small>{row.get('Currency','')}</small></td>
          <td>{_market_cap_fmt(row.get('Market Cap'))}</td>
          <td>{_fmt(row.get('trailingPE'), decimals=1)}</td>
          <td>{_fmt(row.get('priceToBook'), decimals=2)}</td>
          <td>{_fmt(row.get('enterpriseToEbitda'), decimals=1)}</td>
          <td>{_fmt(row.get('debtToEquity'), decimals=1)}</td>
          <td>{_fmt(row.get('dividendYield'), pct=True)}</td>
          <td class="score" style="color:{color};border-left:4px solid {color}">{_fmt(score, decimals=1)}</td>
        </tr>""")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Euronext Brussels — Value Screener</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            background: #0f1117; color: #e0e0e0; padding: 24px; }}
    h1 {{ font-size: 1.6rem; margin-bottom: 4px; color: #fff; }}
    .subtitle {{ color: #888; font-size: 0.85rem; margin-bottom: 24px; }}
    .legend {{ background: #1a1d26; border: 1px solid #2a2d3a; border-radius: 8px;
               padding: 14px 20px; margin-bottom: 20px; font-size: 0.82rem; color: #aaa; }}
    .legend strong {{ color: #ddd; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.84rem; }}
    thead th {{ background: #1a1d26; color: #aaa; font-weight: 600; padding: 10px 12px;
                text-align: right; border-bottom: 2px solid #2a2d3a; white-space: nowrap; }}
    thead th:nth-child(1), thead th:nth-child(2) {{ text-align: left; }}
    tbody tr {{ border-bottom: 1px solid #1e2130; transition: background 0.15s; }}
    tbody tr:hover {{ background: #1a1d26; }}
    td {{ padding: 9px 12px; text-align: right; vertical-align: middle; }}
    td.rank {{ color: #555; font-size: 0.75rem; text-align: left; width: 36px; }}
    td.name {{ text-align: left; color: #fff; font-weight: 500; }}
    td.name .ticker {{ color: #666; font-size: 0.75rem; font-weight: 400; }}
    td.score {{ font-weight: 700; font-size: 0.95rem; padding-left: 16px; }}
    .na {{ color: #444; }}
    small {{ color: #666; font-size: 0.75rem; }}
    @media (max-width: 900px) {{
      .hide-mobile {{ display: none; }}
    }}
  </style>
</head>
<body>
  <h1>Euronext Brussels — Value Screener</h1>
  <p class="subtitle">Generated {now} &nbsp;·&nbsp; {len(df)} stocks ranked by composite value score</p>

  <div class="legend">
    <strong>Value Score (0–100):</strong> composite percentile rank across
    P/E, P/B, EV/EBITDA, Debt/Equity (lower = better) and Dividend Yield (higher = better).
    A higher score means the stock looks <em>relatively</em> cheap vs. its peers on Euronext Brussels.
    Missing metrics are excluded from the average. <strong>Not financial advice.</strong>
  </div>

  <table>
    <thead>
      <tr>
        <th>#</th>
        <th>Company</th>
        <th>Price</th>
        <th>Mkt Cap</th>
        <th>P/E</th>
        <th>P/B</th>
        <th class="hide-mobile">EV/EBITDA</th>
        <th class="hide-mobile">Debt/Eq</th>
        <th>Div Yield</th>
        <th>Value Score</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows_html)}
    </tbody>
  </table>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Report saved to: {output_path}")
