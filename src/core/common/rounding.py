from decimal import Decimal, ROUND_HALF_UP


def round_half_up(value: float, ndigits: int = 0) -> float:
    quant = Decimal("1") if ndigits == 0 else Decimal(f"1e-{ndigits}")
    return float(Decimal(str(value)).quantize(quant, rounding=ROUND_HALF_UP))
