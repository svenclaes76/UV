from app.repositories.valuation_repository import (
    get_fundamentals,
    get_latest_price,
    save_valuation
)
from app.valuation_core.dcf import calculate_dcf


def run_dcf_for_company(company_id: int):
    fundamentals = get_fundamentals(company_id)

    if len(fundamentals) < 2:
        return None  # onvoldoende data

    # Extract data
    last_year = fundamentals[0]
    prev_year = fundamentals[1]

    fcf = last_year[1]
    prev_fcf = prev_year[1]

    # Growth berekenen
    growth = (fcf - prev_fcf) / prev_fcf if prev_fcf else 0.03

    # Discount rate (vereenvoudigd)
    discount_rate = 0.10

    # DCF fair value
    fair_value_total = calculate_dcf(fcf, growth, discount_rate)

    # Aantal aandelen
    shares = last_year[4]
    fair_value_per_share = fair_value_total / shares if shares else None

    # Laatste prijs
    price = get_latest_price(company_id)

    discount_pct = (fair_value_per_share - price) / price if price else None

    # Score (heel simpel)
    score = max(0, min(100, discount_pct * 200))

    # Opslaan
    save_valuation(
        company_id=company_id,
        fair_value=fair_value_per_share,
        discount_pct=discount_pct,
        method="DCF",
        score=score,
        inputs={
            "fcf": fcf,
            "growth": growth,
            "discount_rate": discount_rate,
            "shares": shares
        }
    )

    return {
        "company_id": company_id,
        "fair_value": fair_value_per_share,
        "discount_pct": discount_pct,
        "score": score
    }
