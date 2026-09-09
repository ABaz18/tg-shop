from __future__ import annotations

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError

from app.models import DeliveryKind, Product


async def deliver_product(bot: Bot, chat_id: int, product: Product, stock_payload: str | None) -> None:
    for part in product.parts:
        try:
            await _send_part(bot, chat_id, part.kind, part.text, part.file_id, part.caption)
        except TelegramForbiddenError:
            raise
    if stock_payload:
        await bot.send_message(chat_id, stock_payload, protect_content=True)


async def _send_part(
    bot: Bot,
    chat_id: int,
    kind: DeliveryKind,
    text: str | None,
    file_id: str | None,
    caption: str | None,
) -> None:
    if kind == DeliveryKind.TEXT:
        await bot.send_message(chat_id, text or "", protect_content=True)
        return
    if not file_id:
        return
    if kind == DeliveryKind.PHOTO:
        await bot.send_photo(chat_id, file_id, caption=caption, protect_content=True)
    elif kind == DeliveryKind.DOCUMENT:
        await bot.send_document(chat_id, file_id, caption=caption, protect_content=True)
    elif kind == DeliveryKind.VIDEO:
        await bot.send_video(chat_id, file_id, caption=caption, protect_content=True)
    elif kind == DeliveryKind.ANIMATION:
        await bot.send_animation(chat_id, file_id, caption=caption, protect_content=True)
    elif kind == DeliveryKind.AUDIO:
        await bot.send_audio(chat_id, file_id, caption=caption, protect_content=True)
