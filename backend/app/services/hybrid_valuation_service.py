from app.repositories.valuation_repository import get_latest_price, save_valuation
from app.repositories.relative_repository import get_latest_metrics, get_sector_benchmarks
from app.valuation_core.dcf import calculate_dcf
from app.valuation_core.relative import calculate_relative_value
from app.valuation_core.hybrid import combine_hybrid
from app.repositories.company_repository import get_company_sector  # simpele repo-functie


def run_hybrid_for_company(company_id: int):
    # 1. Basisdata
    price = get_latest_price(company_id)
    if price is None:
        return None

    metrics = get_latest_metrics(company_id)
    if not metrics:
        return None

    fcf = metrics["fcf"]
    shares = metrics["shares"]
    net_income = metrics["net_income"]

    # 2. Sectorbenchmarks
    sector = get_company_sector(company_id)
    sector_bm = get_sector_benchmarks(sector) if sector else None

    # 3. DCF‑fair value (vereenvoudigd)
    growth = 0.03
    discount_rate = 0.10
    dcf_total = calculate_dcf(fcf, growth, discount_rate) if fcf else None
    dcf_fair_value = dcf_total / shares if (dcf_total and shares) else None

    # 4. Relative fair value
    pe = (price * shares / net_income) if (net_income and net_income != 0) else None
    fcf_yield = fcf / (price * shares) if (fcf and price and shares) else None

    relative_fair_value = None
    if sector_bm:
        relative_fair_value = calculate_relative_value(
            price=price,
            pe=pe,
            sector_pe=sector_bm["sector_pe"],
            fcf_yield=fcf_yield,
            sector_fcf_yield=sector_bm["sector_fcf_yield"],
        )

    # 5. Hybrid fair value
    hybrid_fair_value = combine_hybrid(dcf_fair_value, relative_fair_value)

    if hybrid_fair_value is None:
        return None

    discount_pct = (hybrid_fair_value - price) / price if price else None

    # simpele score
    score = max(0, min(100, (discount_pct or 0) * 200))

    inputs = {
        "dcf_fair_value": dcf_fair_value,
        "relative_fair_value": relative_fair_value,
        "price": price,
        "pe": pe,
        "fcf_yield": fcf_yield,
        "sector": sector,
        "sector_benchmarks": sector_bm,
        "growth": growth,
        "discount_rate": discount_rate,
    }

    save_valuation(
        company_id=company_id,
        fair_value=hybrid_fair_value,
        discount_pct=discount_pct,
        method="Hybrid",
        score=score,
        inputs=inputs,
    )

    return {
        "company_id": company_id,
        "fair_value": hybrid_fair_value,
        "discount_pct": discount_pct,
        "score": score,
    }
