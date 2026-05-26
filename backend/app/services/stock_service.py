from app.repositories.stock_repository import fetch_stocks

def get_all_stocks(sector: str | None):
    stocks = fetch_stocks(sector)
    return {"count": len(stocks), "items": stocks}
