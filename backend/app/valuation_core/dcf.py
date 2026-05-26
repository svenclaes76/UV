def calculate_dcf(fcf: float, growth: float, discount_rate: float) -> float:
    projected = [fcf * (1 + growth)**i for i in range(1, 6)]
    discounted = [p / ((1 + discount_rate)**i) for i, p in enumerate(projected, start=1)]

    terminal_value = projected[-1] * (1 + growth) / (discount_rate - growth)
    terminal_discounted = terminal_value / ((1 + discount_rate)**5)

    return sum(discounted) + terminal_discounted
