from app.database import db

def get_latest_metrics(company_id: int):
    with db.cursor() as cur:
        cur.execute("""
            SELECT f.free_cash_flow, f.shares_outstanding, f.net_income
            FROM fundamentals f
            WHERE f.company_id = %s
            ORDER BY f.period DESC
            LIMIT 1
        """, (company_id,))
        row = cur.fetchone()

    if not row:
        return None

    fcf, shares, net_income = row
    return {"fcf": fcf, "shares": shares, "net_income": net_income}


def get_sector_benchmarks(sector: str):
    with db.cursor() as cur:
        cur.execute("""
            SELECT pe_avg, fcf_yield_avg
            FROM sector_benchmarks
            WHERE sector = %s
            ORDER BY period DESC
            LIMIT 1
        """, (sector,))
        row = cur.fetchone()

    if not row:
        return None

    pe_avg, fcf_yield_avg = row
    return {"sector_pe": pe_avg, "sector_fcf_yield": fcf_yield_avg}
