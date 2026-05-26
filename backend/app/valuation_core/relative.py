def calculate_relative_value(
    price: float,
    pe: float | None,
    sector_pe: float | None,
    fcf_yield: float | None,
    sector_fcf_yield: float | None,
) -> float | None:
    estimates = []

    # P/E‑benadering
    if pe and sector_pe and pe > 0:
        target_price_pe = price * (sector_pe / pe)
        estimates.append(target_price_pe)

    # FCF‑yield‑benadering
    if fcf_yield and sector_fcf_yield and sector_fcf_yield > 0:
        target_price_fcf = price * (fcf_yield / sector_fcf_yield)
        estimates.append(target_price_fcf)

    if not estimates:
        return None

    return sum(estimates) / len(estimates)
