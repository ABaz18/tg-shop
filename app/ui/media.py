from __future__ import annotations

from aiogram import Bot
from aiogram.types import BufferedInputFile, Message
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Category, Product, ShopSettings
from app.security.money import format_rub
from app.ui.covers import (
    LAYOUT,
    cover_key,
    jpeg_file,
    render_page,
    render_product_cover,
    render_shop_banner,
)


def _extra(shop: ShopSettings) -> dict:
    data = shop.extra if isinstance(shop.extra, dict) else {}
    shop.extra = dict(data)
    flag_modified(shop, "extra")
    if shop.extra.get("cover_layout") != LAYOUT:
        shop.extra["cover_layout"] = LAYOUT
        shop.extra["pages"] = {}
        shop.extra.pop("banner_key", None)
        shop.banner_file_id = None
    return shop.extra


async def shop_banner(
    bot: Bot,
    session: AsyncSession,
    shop: ShopSettings,
    title: str,
) -> str | BufferedInputFile:
    extra = _extra(shop)
    if extra.get("banner_key") == "custom" and shop.banner_file_id:
        return shop.banner_file_id
    subtitle = "цифровые товары · баланс в рублях"
    key = cover_key("shop", title, subtitle)
    if shop.banner_file_id and extra.get("banner_key") == key:
        return shop.banner_file_id
    extra["banner_key"] = key
    shop.banner_file_id = None
    return jpeg_file(render_shop_banner(title, subtitle), "shop.jpg")


async def category_cover(
    session: AsyncSession,
    cat: Category,
    count: int,
    shop: ShopSettings | None = None,
    lang: str = "ru",
) -> str | BufferedInputFile:
    if cat.cover_file_id:
        return cat.cover_file_id
    if shop is None:
        n = f"{count} позиц." if count else "скоро"
        return jpeg_file(
            render_page(
                eyebrow="КАТАЛОГ",
                title=cat.title_ru,
                footer="нажмите товар ниже",
                accent=cat.id,
            ),
            "cat.jpg",
        )
    title = cat.title_en if lang == "en" and cat.title_en else cat.title_ru
    return page_cover(
        shop,
        f"c:{cat.id}:{lang}",
        eyebrow="КАТАЛОГ" if lang != "en" else "CATALOG",
        title=title,
        footer="нажмите товар ниже",
        accent=cat.id,
    )


async def product_cover(
    product: Product,
    lang: str = "ru",
    shop: ShopSettings | None = None,
) -> str | BufferedInputFile:
    extra = _extra(shop) if shop is not None else {}
    custom = extra.get("custom_covers") if isinstance(extra.get("custom_covers"), dict) else {}
    if product.cover_file_id and str(product.id) in custom:
        return product.cover_file_id
    title = product.title_en if lang == "en" and product.title_en else product.title_ru
    badge = "ВРУЧНУЮ" if product.fulfillment.value == "manual" else "СРАЗУ"
    price = format_rub(product.price_kopecks, "ru")
    slot = f"p:{product.id}:{lang}"
    extra = _extra(shop) if shop is not None else None
    if extra is not None:
        pages = extra.get("pages") if isinstance(extra.get("pages"), dict) else {}
        key = cover_key(slot, title, price, badge)
        rec = pages.get(slot) if isinstance(pages.get(slot), dict) else {}
        if rec.get("key") == key and rec.get("id"):
            return str(rec["id"])
        pages[slot] = {"key": key, "id": None}
        extra["pages"] = pages
    return jpeg_file(render_product_cover(title, price, badge), "item.jpg")
    return jpeg_file(render_product_cover(title, price, badge), "item.jpg")


def page_cover(
    shop: ShopSettings,
    slot: str,
    *,
    eyebrow: str,
    title: str,
    subtitle: str = "",
    footer: str = "",
    accent: int = 0,
) -> str | BufferedInputFile:
    extra = _extra(shop)
    pages = extra.get("pages")
    if not isinstance(pages, dict):
        pages = {}
    key = cover_key(slot, eyebrow, title, subtitle, footer, accent)
    rec = pages.get(slot) if isinstance(pages.get(slot), dict) else {}
    if rec.get("key") == key and rec.get("id"):
        return str(rec["id"])
    pages[slot] = {"key": key, "id": None}
    extra["pages"] = pages
    return jpeg_file(
        render_page(
            eyebrow=eyebrow,
            title=title,
            subtitle=subtitle,
            footer=footer,
            accent=accent,
        ),
        f"{slot}.jpg",
    )


def remember_photo(message: Message | None, target) -> None:
    if message is None or not message.photo:
        return
    file_id = message.photo[-1].file_id
    if hasattr(target, "banner_file_id") and not getattr(target, "banner_file_id"):
        target.banner_file_id = file_id


def remember_page(shop: ShopSettings, slot: str, message: Message | None) -> None:
    if message is None or not message.photo:
        return
    extra = _extra(shop)
    pages = extra.get("pages")
    if not isinstance(pages, dict):
        pages = {}
    rec = pages.get(slot) if isinstance(pages.get(slot), dict) else {}
    rec["id"] = message.photo[-1].file_id
    pages[slot] = rec
    extra["pages"] = pages
