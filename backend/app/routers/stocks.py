from fastapi import APIRouter
from app.services.stock_service import get_all_stocks

router = APIRouter(prefix="/stocks", tags=["stocks"])

@router.get("/")
def list_stocks(sector: str | None = None):
    return get_all_stocks(sector)
