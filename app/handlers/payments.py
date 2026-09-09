from __future__ import annotations

from decimal import Decimal, InvalidOperation

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, LabeledPrice, Message, PreCheckoutQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import t
from app.keyboards.callbacks import TopupCB
from app.models import ShopSettings, User
from app.security.money import format_rub, rub_to_kopecks, stars_for_kopecks
from app.security.payload import PayloadError
from app.services.payments import complete_stars_payment, create_stars_invoice, get_pending_invoice
from app.states import UserStates

router = Router(name="payments")


async def send_stars_invoice(
    *,
    bot: Bot,
    session: AsyncSession,
    user: User,
    shop: ShopSettings,
    kopecks: int,
    product_id: int | None = None,
) -> None:
    lang = user.language
    kopecks = max(shop.min_topup_kopecks, min(shop.max_topup_kopecks, kopecks))
    stars = stars_for_kopecks(kopecks, shop.stars_kopecks_per_star)
    credited = stars * shop.stars_kopecks_per_star
    payment = await create_stars_invoice(
        session,
        user_id=user.id,
        kopecks=credited,
        stars=stars,
        product_id=product_id,
    )
    await bot.send_invoice(
        chat_id=user.tg_id,
        title=t(lang, "balance.stars_pay")[:32],
        description=format_rub(credited, lang)[:255],
        payload=payment.invoice_nonce,
        currency="XTR",
        prices=[LabeledPrice(label="Stars", amount=stars)],
    )


@router.callback_query(TopupCB.filter())
async def topup_click(
    callback: CallbackQuery,
    callback_data: TopupCB,
    bot: Bot,
    session: AsyncSession,
    db_user: User,
    shop: ShopSettings,
) -> None:
    await callback.answer()
    await send_stars_invoice(
        bot=bot,
        session=session,
        user=db_user,
        shop=shop,
        kopecks=callback_data.k,
        product_id=callback_data.pid or None,
    )


@router.message(StateFilter(UserStates.topup_custom), F.text.regexp(r"^\d+([.,]\d{1,2})?$"))
async def topup_custom(
    message: Message,
    bot: Bot,
    session: AsyncSession,
    db_user: User,
    shop: ShopSettings,
    state: FSMContext,
) -> None:
    try:
        kopecks = rub_to_kopecks(Decimal(message.text.replace(",", ".").replace(" ", "")))
    except (InvalidOperation, ValueError):
        await message.answer(t(db_user.language, "balance.custom"))
        return
    await send_stars_invoice(bot=bot, session=session, user=db_user, shop=shop, kopecks=kopecks)


@router.pre_checkout_query()
async def pre_checkout(
    query: PreCheckoutQuery,
    session: AsyncSession,
    db_user: User,
) -> None:
    payment = await get_pending_invoice(session, query.invoice_payload)
    if (
        payment is None
        or payment.user_id != db_user.id
        or payment.status.value != "pending"
        or int(payment.stars_amount or 0) != int(query.total_amount)
        or query.currency != "XTR"
    ):
        await query.answer(ok=False, error_message=t(db_user.language, "pay.fail"))
        return
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def paid(
    message: Message,
    session: AsyncSession,
    db_user: User,
) -> None:
    sp = message.successful_payment
    if sp is None:
        return
    try:
        payment = await complete_stars_payment(
            session,
            user_id=db_user.id,
            nonce=sp.invoice_payload,
            telegram_charge_id=sp.telegram_payment_charge_id,
            stars_paid=sp.total_amount,
        )
    except PayloadError:
        await message.answer(t(db_user.language, "pay.fail"))
        return
    await session.refresh(db_user)
    await message.answer(
        t(db_user.language, "pay.success", amount=format_rub(payment.amount_kopecks, db_user.language))
    )
