from __future__ import annotations

from aiogram.filters import Filter
from aiogram.types import Message

from app.i18n import EN, RU


def _norm(value: str) -> str:
    return (
        value.replace("\ufe0f", "")
        .replace("\u200d", "")
        .replace("\xa0", " ")
        .strip()
        .lower()
    )


def _aliases(key: str) -> set[str]:
    extra = {
        "btn.catalog": {"каталог", "catalog"},
        "btn.balance": {"пополнить", "баланс", "balance", "top up"},
        "btn.profile": {"профиль", "profile"},
        "btn.referral": {"друзья", "рефералка", "referral"},
        "btn.support": {"помощь", "поддержка", "support"},
        "btn.settings": {"язык", "настройки", "settings", "language"},
        "btn.admin": {"админка", "admin"},
    }
    names = {_norm(RU[key]), _norm(EN[key])}
    names.update(extra.get(key, set()))
    return names


class MenuButton(Filter):
    def __init__(self, key: str) -> None:
        self.needles = _aliases(key)

    async def __call__(self, message: Message) -> bool:
        if not message.text:
            return False
        text = _norm(message.text)
        if text in self.needles:
            return True
        tail = text.split()[-1] if text.split() else ""
        return tail in self.needles


MENU_KEYS = (
    "btn.catalog",
    "btn.profile",
    "btn.balance",
    "btn.referral",
    "btn.support",
    "btn.settings",
    "btn.admin",
)


async def is_menu_message(message: Message) -> bool:
    for key in MENU_KEYS:
        if await MenuButton(key)(message):
            return True
    return False


class NotMenu(Filter):
    async def __call__(self, message: Message) -> bool:
        return not await is_menu_message(message)
