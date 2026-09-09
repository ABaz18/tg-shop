from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import cache
from app.models import ShopSettings

_SHOP_KEY = "shop:row-loaded"


async def get_settings(session: AsyncSession) -> ShopSettings:
    row = await session.get(ShopSettings, 1)
    if row is None:
        row = ShopSettings(id=1)
        session.add(row)
        await session.flush()
        cache.delete(_SHOP_KEY)
    if not (row.rules_ru or "").strip():
        row.rules_ru = (
            "Оплата списывается с баланса. Автотовар приходит сразу. "
            "Если что-то не пришло — напишите в Помощь. Возврат — если товар не выдан."
        )
    if not (row.faq_ru or "").strip():
        row.faq_ru = (
            "Как купить: пополните счёт, каталог, Купить. "
            "Товар приходит в этот чат. Вопросы — кнопка Помощь."
        )
    return row


def invalidate_shop_cache() -> None:
    cache.delete("shop:channels")
    cache.delete(_SHOP_KEY)
