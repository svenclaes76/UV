from app.database import db

def get_fundamentals(company_id: int):
    with db.cursor() as cur:
        cur.execute("""
            SELECT period, free_cash_flow, total_debt, total_equity, shares_outstanding
            FROM fundamentals
            WHERE company_id = %s
            ORDER BY period DESC
            LIMIT 5
        """, (company_id,))
        rows = cur.fetchall()
    return rows


def get_latest_price(company_id: int):
    with db.cursor() as cur:
        cur.execute("""
            SELECT close
            FROM prices
            WHERE company_id = %s
            ORDER BY date DESC
            LIMIT 1
        """, (company_id,))
        row = cur.fetchone()
    return row[0] if row else None


def save_valuation(company_id: int, fair_value: float, discount_pct: float, method: str, score: float, inputs: dict):
    with db.cursor() as cur:
        cur.execute("""
            INSERT INTO valuations (company_id, valuation_date, fair_value, discount_pct, valuation_method, score, inputs)
            VALUES ( %s, CURRENT_DATE, %s, %s, %s, %s, %s )
        """, (company_id, fair_value, discount_pct, method, score, inputs))
    db.commit()
