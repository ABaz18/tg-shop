from __future__ import annotations

from aiogram.types import (
    CopyTextButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.i18n import t
from app.keyboards.callbacks import AdmCB, BuyCB, CatCB, FavCB, LangCB, NavCB, PrdCB, SubCB, TopupCB
from app.models import RequiredChannel, Role, User
from app.security.money import format_rub


def main_reply(user: User) -> ReplyKeyboardMarkup:
    lang = user.language
    rows = [
        [KeyboardButton(text=t(lang, "btn.catalog")), KeyboardButton(text=t(lang, "btn.balance"))],
        [KeyboardButton(text=t(lang, "btn.profile")), KeyboardButton(text=t(lang, "btn.referral"))],
        [KeyboardButton(text=t(lang, "btn.support")), KeyboardButton(text=t(lang, "btn.settings"))],
    ]
    if user.role != Role.USER:
        rows.append([KeyboardButton(text=t(lang, "btn.admin"))])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def catalog_kb(
    lang: str,
    categories: list[tuple[int, str]],
    featured: list[tuple[int, str]] | None = None,
) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for pid, title in featured or []:
        b.button(text=t(lang, "btn.hit", title=title[:28]), callback_data=PrdCB(id=pid).pack())
    for cid, title in categories:
        b.button(text=title, callback_data=CatCB(id=cid).pack())
    n_feat = len(featured or [])
    if n_feat:
        b.adjust(*([1] * n_feat), 2)
    else:
        b.adjust(2)
    return b.as_markup()


def products_kb(
    lang: str,
    products: list[tuple[int, str, str]],
    page: int,
    pages: int,
    cat_id: int,
) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for pid, title, price in products:
        b.button(text=f"{title} · {price}", callback_data=PrdCB(id=pid).pack())
    b.adjust(1)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="‹", callback_data=CatCB(id=cat_id, p=page - 1).pack()))
    if page + 1 < pages:
        nav.append(InlineKeyboardButton(text="›", callback_data=CatCB(id=cat_id, p=page + 1).pack()))
    if nav:
        b.row(*nav)
    b.row(InlineKeyboardButton(text=t(lang, "btn.back"), callback_data=NavCB(to="cat").pack()))
    return b.as_markup()


def product_kb(lang: str, product_id: int, cat_id: int, fav: bool, need_topup: int = 0) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if need_topup > 0:
        b.button(
            text=t(lang, "btn.topup_need", amount=format_rub(need_topup, lang)),
            callback_data=TopupCB(k=need_topup, pid=product_id).pack(),
        )
    else:
        b.button(text=t(lang, "btn.buy"), callback_data=BuyCB(id=product_id).pack())
    b.button(text=t(lang, "btn.back"), callback_data=CatCB(id=cat_id).pack())
    b.adjust(1)
    return b.as_markup()


def subscription_kb(lang: str, channels: list[RequiredChannel]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for ch in channels:
        b.button(text=ch.title, url=ch.invite_url)
    b.adjust(1)
    b.row(InlineKeyboardButton(text=t(lang, "btn.check_sub"), callback_data=SubCB(act="chk").pack()))
    return b.as_markup()


def balance_kb(lang: str, amounts: list[int], product_id: int = 0) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for k in amounts:
        b.button(text=format_rub(k, lang), callback_data=TopupCB(k=k, pid=product_id).pack())
    b.adjust(2)
    return b.as_markup()


def profile_kb(lang: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=t(lang, "btn.orders"), callback_data=NavCB(to="ord").pack())
    b.button(text=t(lang, "btn.promo"), callback_data=NavCB(to="promo").pack())
    b.button(text="Русский", callback_data=LangCB(code="ru").pack())
    b.button(text="English", callback_data=LangCB(code="en").pack())
    b.button(text=t(lang, "btn.faq"), callback_data=NavCB(to="faq").pack())
    b.button(text=t(lang, "btn.rules"), callback_data=NavCB(to="rules").pack())
    b.adjust(2)
    return b.as_markup()


def settings_kb(lang: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="Русский", callback_data=LangCB(code="ru").pack())
    b.button(text="English", callback_data=LangCB(code="en").pack())
    b.adjust(2)
    return b.as_markup()


def copy_kb(lang: str, text: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "btn.copy"), copy_text=CopyTextButton(text=text[:256]))]
        ]
    )


def admin_root_kb() -> InlineKeyboardMarkup:
    acts = [
        ("Статистика", "dash"),
        ("Категории", "cats"),
        ("Товары", "prds"),
        ("Заказы", "ords"),
        ("Пользователи", "users"),
        ("Подписка на канал", "sub"),
        ("Рефка и курс ⭐", "ref"),
        ("Рассылка", "bc"),
        ("Промокоды", "promo"),
        ("Обращения", "tix"),
        ("Тексты магазина", "txt"),
        ("Обложка магазина", "banr"),
        ("Магазин открыт?", "set"),
    ]
    b = InlineKeyboardBuilder()
    for title, act in acts:
        b.button(text=title, callback_data=AdmCB(act=act).pack())
    b.adjust(2)
    return b.as_markup()
