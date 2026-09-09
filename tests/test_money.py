from app.security.money import format_rub, kopecks_from_stars, percent_of, rub_to_kopecks, stars_for_kopecks


def test_rub_roundtrip() -> None:
    assert rub_to_kopecks("199.99") == 19999
    assert format_rub(19999, "ru") == "199,99 ₽"


def test_stars_ceil() -> None:
    assert stars_for_kopecks(201, 200) == 2
    assert kopecks_from_stars(2, 200) == 400


def test_percent() -> None:
    assert percent_of(10000, 10) == 1000
    assert percent_of(10000, 0) == 0
