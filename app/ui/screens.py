from __future__ import annotations

from contextlib import suppress

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
    ReplyKeyboardMarkup,
)

from app.models import User
from app.ui.rich import rich


async def show_screen(
    *,
    bot: Bot,
    user: User,
    event: Message | CallbackQuery,
    html: str,
    reply_markup=None,
    reply_keyboard: ReplyKeyboardMarkup | None = None,
    photo: str | BufferedInputFile | None = None,
    caption: str | None = None,
) -> Message | None:
    chat_id = user.tg_id
    message = event if isinstance(event, Message) else event.message
    markup = reply_markup if reply_markup is not None else reply_keyboard
    if isinstance(event, CallbackQuery):
        with suppress(TelegramBadRequest):
            await event.answer()

    if photo is not None:
        cap = (caption or "")[:1024]
        sent = await _show_photo(bot, message, photo, cap, markup, chat_id)
        if sent:
            user.menu_message_id = sent.message_id
        return sent

    if message and message.photo and message.from_user and message.from_user.id == bot.id:
        with suppress(TelegramBadRequest):
            await message.delete()
        message = None

    if isinstance(event, CallbackQuery) and message:
        try:
            await message.edit_text(rich_message=rich(html), reply_markup=reply_markup)
            user.menu_message_id = message.message_id
            return message
        except TelegramBadRequest:
            pass
    sent = await bot.send_rich_message(
        chat_id=chat_id,
        rich_message=rich(html),
        reply_markup=markup,
    )
    user.menu_message_id = sent.message_id
    return sent


async def _show_photo(
    bot: Bot,
    message: Message | None,
    photo: str | BufferedInputFile,
    caption: str,
    markup: InlineKeyboardMarkup | ReplyKeyboardMarkup | None,
    chat_id: int,
) -> Message | None:
    media = InputMediaPhoto(media=photo, caption=caption or None, parse_mode="HTML")
    if message and message.photo and _from_bot(message, bot):
        try:
            await message.edit_media(
                media=media,
                reply_markup=markup if isinstance(markup, InlineKeyboardMarkup) else None,
            )
            return message
        except TelegramBadRequest:
            with suppress(TelegramBadRequest):
                await message.delete()
    elif message and not message.photo and _from_bot(message, bot):
        with suppress(TelegramBadRequest):
            await message.delete()
    return await bot.send_photo(
        chat_id, photo=photo, caption=caption or None, reply_markup=markup, parse_mode="HTML"
    )


def _from_bot(message: Message, bot: Bot) -> bool:
    return bool(message.from_user and message.from_user.id == bot.id)


def file_id_from(message: Message) -> str | None:
    if message.photo:
        return message.photo[-1].file_id
    return None


async def answer_plain(event: Message | CallbackQuery, text: str, reply_markup=None) -> None:
    if isinstance(event, CallbackQuery):
        with suppress(TelegramBadRequest):
            await event.answer(text[:180], show_alert=True)
        return
    await event.answer(text, reply_markup=reply_markup)
