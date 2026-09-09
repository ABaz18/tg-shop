from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message, PreCheckoutQuery, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.cache import limiter
from app.config import Settings
from app.i18n import t
from app.models import Role, User
from app.services.settings import get_settings as get_shop_settings
from app.services.users import upsert_user


class DbSessionMiddleware(BaseMiddleware):
    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self.factory = factory

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self.factory() as session:
            data["session"] = session
            try:
                result = await handler(event, data)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise


class UserMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        from_user = data.get("event_from_user")
        if from_user is None:
            return await handler(event, data)
        session: AsyncSession = data["session"]
        settings: Settings = data["settings"]
        start_arg = None
        if isinstance(event, Message) and event.text and event.text.startswith("/start"):
            parts = event.text.split(maxsplit=1)
            start_arg = parts[1] if len(parts) > 1 else None
        user = await upsert_user(
            session,
            app_settings=settings,
            tg_id=from_user.id,
            username=from_user.username,
            first_name=from_user.first_name,
            start_arg=start_arg,
        )
        data["db_user"] = user
        data["lang"] = user.language if user.language in {"ru", "en"} else "ru"
        return await handler(event, data)


class GuardMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("db_user")
        if user is None:
            return await handler(event, data)
        lang = data.get("lang", "ru")
        if user.is_banned:
            await _notice(event, t(lang, "banned"))
            return None
        session: AsyncSession = data["session"]
        shop = await get_shop_settings(session)
        data["shop"] = shop
        if shop.maintenance and user.role == Role.USER:
            text = event.text if isinstance(event, Message) else ""
            cb = event.data if isinstance(event, CallbackQuery) else ""
            if text and (text.startswith("/start") or "Админ" in text or "Admin" in text):
                return await handler(event, data)
            if isinstance(cb, str) and cb.startswith("a:"):
                return await handler(event, data)
            await _notice(event, t(lang, "maintenance"))
            return None
        return await handler(event, data)


class PrivateOnlyMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        chat = data.get("event_chat")
        if chat is not None and getattr(chat, "type", "private") != "private":
            return None
        return await handler(event, data)


class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        from_user = data.get("event_from_user")
        if from_user is None or isinstance(event, PreCheckoutQuery):
            return await handler(event, data)
        kind = "cb" if isinstance(event, CallbackQuery) else "msg"
        limit = (
            int(self.settings.rate_limit_callback_per_sec)
            if kind == "cb"
            else int(self.settings.rate_limit_private_per_sec)
        )
        if limiter.allow(f"{kind}:{from_user.id}", max(limit, 1)):
            return await handler(event, data)
        if isinstance(event, CallbackQuery):
            with suppress(TelegramBadRequest):
                await event.answer()
        return None


class InstantCallbackMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, CallbackQuery):
            with suppress(TelegramBadRequest):
                await event.answer()
        return await handler(event, data)


async def _notice(event: TelegramObject, text: str) -> None:
    if isinstance(event, Message):
        await event.answer(text)
    elif isinstance(event, CallbackQuery):
        with suppress(TelegramBadRequest):
            await event.answer(text, show_alert=True)
