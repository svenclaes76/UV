from typing import Optional, List, Dict
from app.repositories.screener_repository import fetch_top_undervalued


def get_top_undervalued(
    sector: Optional[str],
    min_score: Optional[float],
    method: Optional[str]
) -> List[Dict]:
    rows = fetch_top_undervalued(sector=sector, min_score=min_score, method=method)

    return [
        {
            "ticker": r["ticker"],
            "name": r["name"],
            "fair_value": float(r["fair_value"]) if r["fair_value"] is not None else None,
            "current_price": float(r["current_price"]) if r["current_price"] is not None else None,
            "discount_pct": float(r["discount_pct"]) if r["discount_pct"] is not None else None,
            "score": float(r["score"]) if r["score"] is not None else None,
            "valuation_method": r["valuation_method"],
            "valuation_date": r["valuation_date"].isoformat() if r["valuation_date"] else None,
        }
        for r in rows
    ]
