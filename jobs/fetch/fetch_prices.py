import requests
import os
from app.database import db

API_KEY = os.getenv("MARKET_API_KEY")

def fetch_prices(ticker: str):
    url = f"https://api.example.com/prices/{ticker}?apikey={API_KEY}"
    data = requests.get(url).json()
    return data

def save_prices(ticker: str, prices: list):
    with db.cursor() as cur:
        for p in prices:
            cur.execute("""
                INSERT INTO prices (ticker, date, close)
                VALUES (%s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (ticker, p["date"], p["close"]))
    db.commit()
