// src/components/ScreenerTable.tsx

import { useEffect, useState } from "react";

type ScreenerItem = {
  ticker: string;
  name: string;
  fair_value: number;
  current_price: number;
  discount_pct: number;
  score: number;
  valuation_method: string;
  valuation_date: string;
};

export default function ScreenerTable() {
  const [items, setItems] = useState<ScreenerItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("http://localhost:8000/screener")
      .then((res) => res.json())
      .then((data) => {
        setItems(data.items);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return <div>Bezig met laden…</div>;
  }

  return (
    <div style={{ padding: "20px" }}>
      <h2>Top 20 ondergewaardeerde aandelen</h2>

      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ background: "#f0f0f0" }}>
            <th style={th}>Ticker</th>
            <th style={th}>Naam</th>
            <th style={th}>Fair Value</th>
            <th style={th}>Prijs</th>
            <th style={th}>Discount %</th>
            <th style={th}>Score</th>
            <th style={th}>Methode</th>
            <th style={th}>Datum</th>
          </tr>
        </thead>

        <tbody>
          {items.map((item) => (
            <tr key={item.ticker} style={{ borderBottom: "1px solid #ddd" }}>
              <td style={td}>{item.ticker}</td>
              <td style={td}>{item.name}</td>
              <td style={td}>{item.fair_value.toFixed(2)}</td>
              <td style={td}>{item.current_price.toFixed(2)}</td>
              <td style={td}>
                <strong style={{ color: item.discount_pct > 30 ? "green" : "black" }}>
                  {(item.discount_pct * 100).toFixed(1)}%
                </strong>
              </td>
              <td style={td}>{item.score.toFixed(1)}</td>
              <td style={td}>{item.valuation_method}</td>
              <td style={td}>{item.valuation_date}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const th = {
  padding: "10px",
  textAlign: "left" as const,
  borderBottom: "2px solid #ccc",
};

const td = {
  padding: "8px",
};
