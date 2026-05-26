from typing import Optional, List, Dict
from app.database import db


def fetch_top_undervalued(
    sector: Optional[str],
    min_score: Optional[float],
    method: Optional[str]
) -> List[Dict]:
    with db.cursor() as cur:
        query = """
        WITH latest_valuation AS (
            SELECT
                v.company_id,
                v.fair_value,
                v.discount_pct,
                v.score,
                v.valuation_method,
                v.valuation_date,
                ROW_NUMBER() OVER (
                    PARTITION BY v.company_id
                    ORDER BY v.valuation_date DESC
                ) AS rn
            FROM valuations v
        ),
        latest_price AS (
            SELECT
                p.company_id,
                p.close AS current_price,
                p.date,
                ROW_NUMBER() OVER (
                    PARTITION BY p.company_id
                    ORDER BY p.date DESC
                ) AS rn
            FROM prices p
        )
        SELECT
            c.ticker,
            c.name,
            lv.fair_value,
            lp.current_price,
            lv.discount_pct,
            lv.score,
            lv.valuation_method,
            lv.valuation_date
        FROM latest_valuation lv
        JOIN latest_price lp
            ON lp.company_id = lv.company_id AND lp.rn = 1
        JOIN companies c
            ON c.id = lv.company_id
        WHERE lv.rn = 1
          AND lv.discount_pct > 0
          AND lv.score IS NOT NULL
        """
        params = []

        if sector:
            query += " AND c.sector = %s"
            params.append(sector)

        if min_score is not None:
            query += " AND lv.score >= %s"
            params.append(min_score)

        if method:
            query += " AND lv.valuation_method = %s"
            params.append(method)

        query += " ORDER BY lv.discount_pct DESC, lv.score DESC LIMIT 20"

        cur.execute(query, params)
        cols = [c.name for c in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]

    return rows
