from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PromoCode, PromoRedemption, User
from app.services.shop import ShopError


async def redeem_promo(session: AsyncSession, *, user_id: int, code: str) -> int:
    normalized = code.strip().upper()[:32]
    if not normalized:
        raise ShopError("promo_bad")
    promo = (
        await session.execute(
            select(PromoCode).where(PromoCode.code == normalized).with_for_update()
        )
    ).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if (
        promo is None
        or not promo.is_active
        or (promo.expires_at and promo.expires_at < now)
        or (promo.max_uses and promo.used_count >= promo.max_uses)
    ):
        raise ShopError("promo_bad")
    used = await session.execute(
        select(PromoRedemption).where(PromoRedemption.promo_id == promo.id, PromoRedemption.user_id == user_id)
    )
    if used.scalar_one_or_none():
        raise ShopError("promo_bad")
    user = await session.get(User, user_id, with_for_update=True)
    if user is None:
        raise ShopError("promo_bad")
    amount = promo.amount_kopecks
    if amount <= 0:
        raise ShopError("promo_bad")
    user.balance_kopecks += amount
    promo.used_count += 1
    session.add(PromoRedemption(promo_id=promo.id, user_id=user.id))
    await session.flush()
    return amount
