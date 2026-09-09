from __future__ import annotations

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import cache
from app.models import RequiredChannel, ShopSettings


async def active_channels(session: AsyncSession, shop: ShopSettings | None = None) -> list[RequiredChannel]:
    if shop is not None and not shop.subscription_enabled:
        return []
    if shop is None:
        from app.services.settings import get_settings

        shop = await get_settings(session)
        if not shop.subscription_enabled:
            return []
    result = await session.execute(
        select(RequiredChannel).where(RequiredChannel.is_active.is_(True)).order_by(RequiredChannel.id)
    )
    return list(result.scalars().all())


async def user_subscribed(bot: Bot, user_tg_id: int, channels: list[RequiredChannel]) -> bool:
    if not channels:
        return True
    key = f"sub:{user_tg_id}:{','.join(str(c.chat_id) for c in channels)}"
    cached = cache.get(key)
    if cached is not None:
        return bool(cached)
    ok_statuses = {
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.CREATOR,
        ChatMemberStatus.RESTRICTED,
    }
    ok = True
    for channel in channels:
        try:
            member = await bot.get_chat_member(channel.chat_id, user_tg_id)
        except Exception:
            ok = False
            break
        if member.status not in ok_statuses:
            ok = False
            break
        if member.status == ChatMemberStatus.RESTRICTED and not getattr(member, "is_member", True):
            ok = False
            break
    cache.set(key, ok, 25 if ok else 5)
    return ok
