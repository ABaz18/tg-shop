from app.ui.covers import render_page, render_product_cover, render_shop_banner


def test_covers_are_jpeg() -> None:
    for blob in (
        render_shop_banner("UrentRentFree Shop", "цифровые товары · баланс в рублях"),
        render_page(eyebrow="КАТАЛОГ", title="Подписки", footer="нажмите товар ниже", accent=1),
        render_page(eyebrow="БАЛАНС", title="Пополнение", subtitle="деньги на счёт", footer="звёзды Telegram"),
        render_product_cover("Ключ на месяц", "199 ₽", "СРАЗУ"),
    ):
        assert blob[:2] == b"\xff\xd8"
        assert len(blob) > 8000
