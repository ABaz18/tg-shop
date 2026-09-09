from __future__ import annotations

import math
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP


KOPECKS = 100
MAX_MONEY = 10_000_000_00  # 10 mln RUB in kopecks


def rub_to_kopecks(value: Decimal | str | int | float) -> int:
    amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    kopecks = int(amount * KOPECKS)
    if kopecks < 0 or kopecks > MAX_MONEY:
        raise ValueError("amount out of range")
    return kopecks


def format_rub(kopecks: int, lang: str = "ru") -> str:
    sign = "-" if kopecks < 0 else ""
    kopecks = abs(int(kopecks))
    rub, kop = divmod(kopecks, 100)
    body = f"{rub:,}".replace(",", " ")
    if lang == "en":
        return f"{sign}{body}.{kop:02d} RUB"
    return f"{sign}{body},{kop:02d} ₽"


def stars_for_kopecks(kopecks: int, kopecks_per_star: int) -> int:
    if kopecks_per_star <= 0:
        raise ValueError("invalid star rate")
    if kopecks <= 0:
        return 0
    stars = math.ceil(kopecks / kopecks_per_star)
    return max(1, stars)


def kopecks_from_stars(stars: int, kopecks_per_star: int) -> int:
    if stars <= 0 or kopecks_per_star <= 0:
        raise ValueError("invalid stars")
    total = int(stars) * int(kopecks_per_star)
    if total > MAX_MONEY:
        raise ValueError("amount out of range")
    return total


def percent_of(kopecks: int, percent: int) -> int:
    if percent <= 0:
        return 0
    if percent > 100:
        raise ValueError("percent too high")
    return int((Decimal(kopecks) * Decimal(percent) / Decimal(100)).to_integral_value(rounding=ROUND_HALF_UP))
