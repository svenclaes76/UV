from fastapi import FastAPI
from app.routers import stocks, screener, valuations, health

app = FastAPI(title="Stock Valuation API")

app.include_router(stocks.router)
app.include_router(screener.router)
app.include_router(valuations.router)
app.include_router(health.router)
