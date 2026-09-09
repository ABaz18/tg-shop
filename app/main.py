from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import DefaultKeyBuilder, RedisStorage
from aiogram.types import BotCommand, ErrorEvent
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from redis.asyncio import Redis

from app.config import Settings, get_settings
from app.db.session import create_engine, create_session_factory, init_db
from app.handlers.admin import router as admin_router
from app.handlers.payments import router as payments_router
from app.handlers.user import router as user_router
from app.logging import setup_logging
from app.middlewares import (
    DbSessionMiddleware,
    GuardMiddleware,
    InstantCallbackMiddleware,
    PrivateOnlyMiddleware,
    RateLimitMiddleware,
    UserMiddleware,
)
from app.services.broadcast import run_broadcast_worker
from app.services.settings import get_settings as get_shop_settings

log = logging.getLogger(__name__)


async def on_error(event: ErrorEvent) -> None:
    log.exception("update failed", extra={"update_type": type(event.update).__name__})


def build_dispatcher(settings: Settings, redis: Redis, session_factory) -> Dispatcher:
    storage = RedisStorage(redis=redis, key_builder=DefaultKeyBuilder(with_bot_id=True, with_destiny=True))
    dp = Dispatcher(storage=storage)
    dp["settings"] = settings
    dp["redis"] = redis
    dp.message.middleware(PrivateOnlyMiddleware())
    dp.callback_query.middleware(PrivateOnlyMiddleware())
    dp.callback_query.middleware(InstantCallbackMiddleware())
    for observer in (dp.message, dp.callback_query, dp.pre_checkout_query):
        observer.middleware(RateLimitMiddleware(settings))
        observer.middleware(DbSessionMiddleware(session_factory))
        observer.middleware(UserMiddleware())
        observer.middleware(GuardMiddleware())
    dp.include_router(admin_router)
    dp.include_router(payments_router)
    dp.include_router(user_router)
    dp.errors.register(on_error)
    return dp


async def set_commands(bot: Bot) -> None:
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Магазин"),
            BotCommand(command="admin", description="Admin"),
        ]
    )


def _install_uvloop() -> None:
    try:
        import uvloop

        uvloop.install()
    except Exception:
        pass


async def run() -> None:
    settings = get_settings()
    setup_logging(settings)
    engine = create_engine(settings)
    await init_db(engine)
    session_factory = create_session_factory(engine)
    async with session_factory() as session:
        shop = await get_shop_settings(session)
        if shop.welcome_ru == "Добро пожаловать в магазин.":
            shop.welcome_ru = "Выберите товар в каталоге. Если на счёте мало денег — нажмите «Пополнить»."
            shop.welcome_en = "Open Catalog to buy. Tap Top up if you need money on your balance."
        await session.commit()

    redis = Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        max_connections=50,
        socket_connect_timeout=3,
        socket_timeout=5,
    )
    session_aio = AiohttpSession(limit=100, timeout=75)
    bot = Bot(
        token=settings.bot_token,
        session=session_aio,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = build_dispatcher(settings, redis, session_factory)
    me = await bot.get_me()
    bot_title = (settings.bot_name or me.first_name or me.full_name or me.username or "").strip()[:120]
    dp["bot_title"] = bot_title
    async with session_factory() as session:
        shop = await get_shop_settings(session)
        if shop.shop_title_ru in {"", "Shop"}:
            shop.shop_title_ru = bot_title
        if shop.shop_title_en in {"", "Shop"}:
            shop.shop_title_en = bot_title
        await session.commit()
    stop = asyncio.Event()
    worker = asyncio.create_task(run_broadcast_worker(bot, session_factory, redis, stop))
    await set_commands(bot)
    try:
        if settings.is_webhook:
            if not settings.webhook_secret or len(settings.webhook_secret) < 16:
                raise RuntimeError("WEBHOOK_SECRET must be set")
            await bot.set_webhook(
                url=settings.webhook_url,
                secret_token=settings.webhook_secret,
                allowed_updates=["message", "callback_query", "pre_checkout_query"],
                drop_pending_updates=False,
            )
            app = web.Application()
            SimpleRequestHandler(
                dispatcher=dp,
                bot=bot,
                secret_token=settings.webhook_secret,
                handle_in_background=True,
            ).register(app, path=settings.webhook_path)
            setup_application(app, dp, bot=bot)
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, settings.webhook_host, settings.webhook_port)
            await site.start()
            log.info("webhook started")
            await asyncio.Event().wait()
        else:
            await bot.delete_webhook(drop_pending_updates=False)
            await dp.start_polling(
                bot,
                allowed_updates=["message", "callback_query", "pre_checkout_query"],
                handle_as_tasks=True,
                polling_timeout=25,
                tasks_concurrency_limit=250,
            )
    finally:
        stop.set()
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker
        await bot.session.close()
        await redis.aclose()
        await engine.dispose()


def main() -> None:
    _install_uvloop()
    asyncio.run(run())


if __name__ == "__main__":
    main()
