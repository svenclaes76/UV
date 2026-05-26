from fastapi import APIRouter, Query
from typing import Optional, List
from app.services.screener_service import get_top_undervalued

router = APIRouter(prefix="/screener", tags=["screener"])


@router.get("/")
def screener_endpoint(
    sector: Optional[str] = Query(default=None),
    min_score: Optional[float] = Query(default=None),
    method: Optional[str] = Query(default=None)  # 'DCF', 'Relative', 'Hybrid'
):
    results = get_top_undervalued(sector=sector, min_score=min_score, method=method)
    return {"count": len(results), "items": results}
