from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from redis.asyncio import Redis
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

from app.models import Broadcast, User
from app.ui.rich import rich


SEGMENTS = {"all", "buyers", "balance", "new"}


async def enqueue_broadcast(redis: Redis, broadcast_id: int) -> None:
    await redis.lpush("broadcast:queue", str(broadcast_id))


async def run_broadcast_worker(
    bot: Bot,
    factory: async_sessionmaker[AsyncSession],
    redis: Redis,
    stop_event,
) -> None:
    while not stop_event.is_set():
        item = await redis.brpop("broadcast:queue", timeout=2)
        if not item:
            continue
        _, raw = item
        try:
            await _send_one(bot, factory, int(raw))
        except Exception:
            continue


async def _send_one(bot: Bot, factory: async_sessionmaker[AsyncSession], broadcast_id: int) -> None:
    async with factory() as session:
        bc = await session.get(Broadcast, broadcast_id)
        if bc is None or bc.status not in {"queued", "running"}:
            return
        bc.status = "running"
        await session.commit()
        user_ids = await _segment_users(session, bc.segment)
        html = bc.html
        sent = failed = 0
        for tg_id in user_ids:
            try:
                await bot.send_rich_message(chat_id=tg_id, rich_message=rich(html))
                sent += 1
            except TelegramRetryAfter as err:
                import asyncio

                await asyncio.sleep(err.retry_after + 0.3)
                try:
                    await bot.send_rich_message(chat_id=tg_id, rich_message=rich(html))
                    sent += 1
                except Exception:
                    failed += 1
            except (TelegramForbiddenError, Exception):
                failed += 1
            if sent % 20 == 0:
                await asyncio_sleep()
        bc.sent = sent
        bc.failed = failed
        bc.status = "done"
        bc.finished_at = datetime.now(timezone.utc)
        await session.commit()


async def asyncio_sleep() -> None:
    import asyncio

    await asyncio.sleep(0.4)


async def _segment_users(session: AsyncSession, segment: str) -> list[int]:
    q = select(User.tg_id).where(User.is_banned.is_(False))
    if segment == "buyers":
        from app.models import Order

        q = q.where(User.id.in_(select(Order.user_id).distinct()))
    elif segment == "balance":
        q = q.where(User.balance_kopecks > 0)
    elif segment == "new":
        from datetime import timedelta

        since = datetime.now(timezone.utc) - timedelta(days=7)
        q = q.where(User.created_at >= since)
    result = await session.execute(q)
    return [int(x) for x in result.scalars().all()]
