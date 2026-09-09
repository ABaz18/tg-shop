from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import Role, User
from app.services.settings import get_settings as get_shop_settings

_SEEN_TTL = timedelta(seconds=45)


async def upsert_user(
    session: AsyncSession,
    *,
    app_settings: Settings,
    tg_id: int,
    username: str | None,
    first_name: str | None,
    start_arg: str | None,
) -> User:
    result = await session.execute(select(User).where(User.tg_id == tg_id))
    user = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if user is None:
        user = User(
            tg_id=tg_id,
            username=username,
            first_name=first_name,
            last_seen_at=now,
        )
        session.add(user)
        await session.flush()
        shop = await get_shop_settings(session)
        if shop.welcome_bonus_kopecks > 0:
            user.balance_kopecks += shop.welcome_bonus_kopecks
        await _attach_referrer(session, user, start_arg)
    else:
        if user.username != username:
            user.username = username
        if user.first_name != first_name:
            user.first_name = first_name
        last_seen = user.last_seen_at
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        if now - last_seen >= _SEEN_TTL:
            user.last_seen_at = now

    if tg_id in app_settings.owners and (user.role != Role.OWNER or user.is_banned):
        user.role = Role.OWNER
        user.is_banned = False
    return user


async def _attach_referrer(session: AsyncSession, user: User, start_arg: str | None) -> None:
    if not start_arg or not start_arg.startswith("ref_"):
        return
    raw = start_arg[4:]
    if not raw.isdigit():
        return
    ref_tg = int(raw)
    if ref_tg == user.tg_id:
        return
    result = await session.execute(select(User).where(User.tg_id == ref_tg))
    referrer = result.scalar_one_or_none()
    if referrer is None or referrer.is_banned:
        return
    user.referrer_id = referrer.id


def has_staff_access(user: User) -> bool:
    return user.role in {Role.SUPPORT, Role.ADMIN, Role.OWNER}


def has_admin_access(user: User) -> bool:
    return user.role in {Role.ADMIN, Role.OWNER}


def has_owner_access(user: User) -> bool:
    return user.role == Role.OWNER
