from app.database import db

def fetch_stocks(sector: str | None):
    query = "SELECT ticker, name, sector FROM companies"
    params = ()

    if sector:
        query += " WHERE sector = %s"
        params = (sector,)

    with db.cursor() as cur:
        cur.execute(query, params)
        return cur.fetchall()
