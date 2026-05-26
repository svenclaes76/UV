def combine_hybrid(
    dcf_fair_value: float | None,
    relative_fair_value: float | None,
    w_dcf: float = 0.6,
    w_rel: float = 0.4,
) -> float | None:
    parts = []
    weights = []

    if dcf_fair_value is not None:
        parts.append(dcf_fair_value)
        weights.append(w_dcf)

    if relative_fair_value is not None:
        parts.append(relative_fair_value)
        weights.append(w_rel)

    if not parts:
        return None

    # normaliseer gewichten op basis van wat beschikbaar is
    total_w = sum(weights)
    weights = [w / total_w for w in weights]

    return sum(p * w for p, w in zip(parts, weights))
