import { useEffect, useState } from "react";
import { getScreener } from "../api/screener";

export default function ScreenerPage() {
  const [results, setResults] = useState([]);

  useEffect(() => {
    getScreener().then(setResults);
  }, []);

  return (
    <div>
      <h1>Ondergewaardeerde aandelen</h1>
      <table>
        <thead>
          <tr>
            <th>Ticker</th>
            <th>Fair Value</th>
            <th>Discount %</th>
          </tr>
        </thead>
        <tbody>
          {results.map((r: any) => (
            <tr key={r.ticker}>
              <td>{r.ticker}</td>
              <td>{r.fair_value}</td>
              <td>{r.discount_pct}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
