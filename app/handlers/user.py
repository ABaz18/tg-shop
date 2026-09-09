from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import t
from app.keyboards.filters import MenuButton, NotMenu
from app.keyboards.build import (
    balance_kb,
    catalog_kb,
    copy_kb,
    main_reply,
    product_kb,
    products_kb,
    profile_kb,
    settings_kb,
    subscription_kb,
)
from app.keyboards.callbacks import BuyCB, CatCB, FavCB, LangCB, NavCB, PrdCB, SubCB, TopupCB
from app.models import Category, Order, ReferralPayout, ShopSettings, User
from app.security.locks import exclusive
from app.security.money import format_rub
from app.services.catalog import (
    get_product,
    list_categories_with_counts,
    list_featured,
    list_products,
    sold_count,
    stock_left,
    toggle_favorite,
)
from app.services.fulfillment import deliver_product
from app.services.ops import add_ticket_message, open_or_get_ticket, staff_ids
from app.services.promo import redeem_promo
from app.services.shop import ShopError, count_orders, purchase
from app.services.subscription import active_channels, user_subscribed
from app.states import UserStates
from app.ui.media import category_cover, page_cover, product_cover, remember_page, remember_photo, shop_banner
from app.ui.screens import answer_plain, show_screen
from app.ui.views import (
    balance_caption,
    balance_html,
    catalog_caption,
    catalog_html,
    home_caption,
    home_html,
    loc,
    orders_caption,
    product_caption,
    product_html,
    products_caption,
    products_html,
    profile_caption,
    profile_html,
    receipt_caption,
    receipt_html,
    referral_caption,
    referral_html,
    settings_caption,
    settings_html,
    shop_heading,
    sub_caption,
    sub_html,
    support_caption,
    support_html,
    text_caption,
)

router = Router(name="user")

PAGE = 8


async def gated(
    bot: Bot,
    session: AsyncSession,
    user: User,
    shop: ShopSettings,
    event: Message | CallbackQuery,
) -> bool:
    channels = await active_channels(session, shop)
    if not channels:
        return True
    if await user_subscribed(bot, user.tg_id, channels):
        return True
    lang = user.language
    photo = page_cover(
        shop,
        f"sub:{lang}",
        eyebrow=t(lang, "cover.sub"),
        title=t(lang, "sub.title"),
        subtitle=t(lang, "sub.body"),
        footer=t(lang, "cover.foot.sub"),
        accent=3,
    )
    sent = await show_screen(
        bot=bot,
        user=user,
        event=event,
        html=sub_html(lang),
        caption=sub_caption(lang),
        photo=photo,
        reply_markup=subscription_kb(lang, channels),
    )
    remember_page(shop, f"sub:{lang}", sent)
    return False


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    bot: Bot,
    session: AsyncSession,
    db_user: User,
    shop: ShopSettings,
    state: FSMContext,
    bot_title: str = "",
) -> None:
    await state.clear()
    if not await gated(bot, session, db_user, shop, message):
        return
    title = shop_heading(shop, db_user.language, bot_title)
    photo = await shop_banner(bot, session, shop, title)
    sent = await show_screen(
        bot=bot,
        user=db_user,
        event=message,
        html=home_html(db_user, shop, bot_title),
        caption=home_caption(db_user, shop, bot_title),
        photo=photo,
        reply_keyboard=main_reply(db_user),
    )
    remember_photo(sent, shop)


@router.message(MenuButton("btn.catalog"))
@router.callback_query(NavCB.filter(F.to == "cat"))
async def open_catalog(
    event: Message | CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    db_user: User,
    shop: ShopSettings,
    state: FSMContext,
) -> None:
    await state.clear()
    if not await gated(bot, session, db_user, shop, event):
        return
    cats = await list_categories_with_counts(session)
    featured = await list_featured(session)
    lang = db_user.language
    buttons = []
    feat_rows = []
    feat_btns = []
    for item in featured:
        feat_rows.append([loc(item, "title", lang), format_rub(item.price_kopecks, lang)])
        feat_btns.append((item.id, loc(item, "title", lang)))
    for cat, n in cats:
        title = loc(cat, "title", lang)
        buttons.append((cat.id, f"{title} · {n}"))
    photo = page_cover(
        shop,
        f"catalog:{lang}",
        eyebrow=t(lang, "cover.catalog"),
        title=t(lang, "catalog.title"),
        subtitle=t(lang, "cover.subline.catalog"),
        footer=t(lang, "cover.foot.catalog"),
        accent=1,
    )
    sent = await show_screen(
        bot=bot,
        user=db_user,
        event=event,
        html=catalog_html(lang, feat_rows, empty=not buttons),
        caption=catalog_caption(lang, empty=not buttons),
        photo=photo,
        reply_markup=catalog_kb(lang, buttons, feat_btns),
    )
    remember_page(shop, f"catalog:{lang}", sent)


@router.callback_query(CatCB.filter())
async def open_category(
    callback: CallbackQuery,
    callback_data: CatCB,
    bot: Bot,
    session: AsyncSession,
    db_user: User,
    shop: ShopSettings,
) -> None:
    if not await gated(bot, session, db_user, shop, callback):
        return
    products = await list_products(session, callback_data.id)
    lang = db_user.language
    pages = max(1, (len(products) + PAGE - 1) // PAGE)
    page = min(max(callback_data.p, 0), pages - 1)
    chunk = products[page * PAGE : (page + 1) * PAGE]
    cat = await session.get(Category, callback_data.id)
    title = loc(cat, "title", lang) if cat else t(lang, "catalog.title")
    photo = None
    if cat:
        photo = await category_cover(session, cat, len(products), shop, lang)
    sent = await show_screen(
        bot=bot,
        user=db_user,
        event=callback,
        html=products_html(lang, title, [[loc(p, "title", lang), format_rub(p.price_kopecks, lang)] for p in chunk]),
        caption=products_caption(lang, title, len(products)),
        photo=photo,
        reply_markup=products_kb(
            lang,
            [(p.id, loc(p, "title", lang), format_rub(p.price_kopecks, lang)) for p in chunk],
            page,
            pages,
            callback_data.id,
        ),
    )
    if cat:
        remember_page(shop, f"c:{cat.id}:{lang}", sent)


@router.callback_query(PrdCB.filter())
async def open_product(
    callback: CallbackQuery,
    callback_data: PrdCB,
    bot: Bot,
    session: AsyncSession,
    db_user: User,
    shop: ShopSettings,
) -> None:
    if not await gated(bot, session, db_user, shop, callback):
        return
    await _show_product(callback, bot, session, db_user, shop, callback_data.id)


async def _show_product(
    event: Message | CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    db_user: User,
    shop: ShopSettings,
    product_id: int,
) -> None:
    product = await get_product(session, product_id, with_parts=False)
    lang = db_user.language
    if product is None or not product.is_active:
        await answer_plain(event, t(lang, "buy.inactive"))
        return
    stock = await stock_left(session, product.id) if product.use_stock else None
    sold = await sold_count(session, product.id)
    need = max(0, product.price_kopecks - db_user.balance_kopecks)
    photo = await product_cover(product, lang, shop)
    sent = await show_screen(
        bot=bot,
        user=db_user,
        event=event,
        html=product_html(lang, product, stock, shop, sold),
        caption=product_caption(lang, product, stock, sold),
        photo=photo,
        reply_markup=product_kb(lang, product.id, product.category_id, False, need_topup=need),
    )
    remember_page(shop, f"p:{product.id}:{lang}", sent)


@router.callback_query(FavCB.filter())
async def fav(
    callback: CallbackQuery,
    callback_data: FavCB,
    bot: Bot,
    session: AsyncSession,
    db_user: User,
    shop: ShopSettings,
) -> None:
    await toggle_favorite(session, db_user.id, callback_data.id)
    await _show_product(callback, bot, session, db_user, shop, callback_data.id)


@router.callback_query(BuyCB.filter())
async def buy(
    callback: CallbackQuery,
    callback_data: BuyCB,
    bot: Bot,
    session: AsyncSession,
    db_user: User,
    shop: ShopSettings,
    redis: Redis,
) -> None:
    if not await gated(bot, session, db_user, shop, callback):
        return
    lang = db_user.language
    product = await get_product(session, callback_data.id)
    if product is None:
        await callback.answer(t(lang, "buy.inactive"), show_alert=True)
        return
    need = product.price_kopecks - db_user.balance_kopecks
    if need > 0:
        await callback.answer(t(lang, "buy.no_funds", amount=format_rub(need, lang)), show_alert=True)
        await _show_product(callback, bot, session, db_user, shop, product.id)
        return
    try:
        async with exclusive(redis, f"buy:{db_user.id}"):
            result = await purchase(session, user_id=db_user.id, product_id=product.id)
            await session.commit()
    except ShopError as err:
        mapping = {
            "no_funds": t(lang, "buy.no_funds", amount=format_rub(max(need, 0), lang)),
            "no_stock": t(lang, "buy.no_stock"),
            "inactive": t(lang, "buy.inactive"),
            "busy": t(lang, "generic.error"),
        }
        await callback.answer(mapping.get(err.code, t(lang, "generic.error")), show_alert=True)
        return
    manual = result.product.fulfillment.value == "manual"
    if not manual:
        try:
            await deliver_product(bot, db_user.tg_id, result.product, result.stock_payload)
        except Exception:
            await bot.send_message(db_user.tg_id, t(lang, "generic.error"))
    else:
        for tg in await staff_ids(session):
            try:
                await bot.send_message(
                    tg,
                    f"Ручная выдача #{result.order.id}\nuser={db_user.tg_id}\n{loc(result.product, 'title', 'ru')}",
                )
            except Exception:
                pass
    await session.refresh(db_user)
    cover = page_cover(
        shop,
        f"receipt:{lang}",
        eyebrow=t(lang, "cover.receipt"),
        title=t(lang, "receipt.title"),
        subtitle=loc(result.product, "title", lang),
        footer=t(lang, "cover.foot.receipt"),
        accent=0,
    )
    sent = await show_screen(
        bot=bot,
        user=db_user,
        event=callback,
        html=receipt_html(
            lang,
            result.order.id,
            loc(result.product, "title", lang),
            format_rub(result.order.price_kopecks, lang),
            format_rub(db_user.balance_kopecks, lang),
            manual,
        ),
        caption=receipt_caption(
            lang,
            result.order.id,
            loc(result.product, "title", lang),
            format_rub(result.order.price_kopecks, lang),
            format_rub(db_user.balance_kopecks, lang),
            manual,
        ),
        photo=cover,
    )
    remember_page(shop, f"receipt:{lang}", sent)


@router.message(MenuButton("btn.profile"))
async def profile(
    message: Message,
    bot: Bot,
    session: AsyncSession,
    db_user: User,
    shop: ShopSettings,
    state: FSMContext,
) -> None:
    await state.clear()
    orders = await count_orders(session, db_user.id)
    refs = int(
        (
            await session.execute(select(func.count(User.id)).where(User.referrer_id == db_user.id))
        ).scalar_one()
    )
    lang = db_user.language
    photo = page_cover(
        shop,
        f"profile:{lang}",
        eyebrow=t(lang, "cover.profile"),
        title=t(lang, "profile.title"),
        subtitle=format_rub(db_user.balance_kopecks, lang),
        footer=t(lang, "cover.foot.profile"),
        accent=0,
    )
    sent = await show_screen(
        bot=bot,
        user=db_user,
        event=message,
        html=profile_html(lang, db_user, orders, refs),
        caption=profile_caption(lang, db_user, orders, refs),
        photo=photo,
        reply_markup=profile_kb(lang),
    )
    remember_page(shop, f"profile:{lang}", sent)


@router.message(MenuButton("btn.balance"))
@router.callback_query(NavCB.filter(F.to == "home"))
async def balance(
    event: Message | CallbackQuery,
    bot: Bot,
    db_user: User,
    shop: ShopSettings,
    state: FSMContext,
) -> None:
    if isinstance(event, Message):
        await state.set_state(UserStates.topup_custom)
    amounts = [10_000, 25_000, 50_000, 100_000, 250_000, 500_000]
    lang = db_user.language
    photo = page_cover(
        shop,
        f"balance:{lang}",
        eyebrow=t(lang, "cover.balance"),
        title=t(lang, "balance.title"),
        subtitle=t(lang, "cover.subline.balance"),
        footer=t(lang, "cover.foot.balance"),
        accent=0,
    )
    sent = await show_screen(
        bot=bot,
        user=db_user,
        event=event,
        html=balance_html(lang, db_user, shop),
        caption=balance_caption(lang, db_user, shop),
        photo=photo,
        reply_markup=balance_kb(lang, amounts),
    )
    remember_page(shop, f"balance:{lang}", sent)


@router.message(MenuButton("btn.referral"))
async def referral(
    message: Message,
    bot: Bot,
    session: AsyncSession,
    db_user: User,
    shop: ShopSettings,
    state: FSMContext,
) -> None:
    await state.clear()
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{db_user.tg_id}"
    invited = int(
        (await session.execute(select(func.count(User.id)).where(User.referrer_id == db_user.id))).scalar_one()
    )
    earned = int(
        (
            await session.execute(
                select(func.coalesce(func.sum(ReferralPayout.amount_kopecks), 0)).where(
                    ReferralPayout.beneficiary_id == db_user.id
                )
            )
        ).scalar_one()
    )
    lang = db_user.language
    photo = page_cover(
        shop,
        f"ref:{lang}",
        eyebrow=t(lang, "cover.ref"),
        title=t(lang, "ref.title"),
        subtitle=t(lang, "ref.how"),
        footer=t(lang, "cover.foot.ref"),
        accent=1,
    )
    sent = await show_screen(
        bot=bot,
        user=db_user,
        event=message,
        html=referral_html(lang, link, shop, invited, earned),
        caption=referral_caption(lang, link, shop, invited, earned),
        photo=photo,
        reply_markup=copy_kb(lang, link),
    )
    remember_page(shop, f"ref:{lang}", sent)


@router.message(MenuButton("btn.settings"))
async def settings_menu(message: Message, bot: Bot, db_user: User, shop: ShopSettings, state: FSMContext) -> None:
    await state.clear()
    lang = db_user.language
    photo = page_cover(
        shop,
        f"lang:{lang}",
        eyebrow=t(lang, "cover.lang"),
        title=t(lang, "settings.title"),
        footer=t(lang, "cover.foot.lang"),
        accent=2,
    )
    sent = await show_screen(
        bot=bot,
        user=db_user,
        event=message,
        html=settings_html(lang),
        caption=settings_caption(lang),
        photo=photo,
        reply_markup=settings_kb(lang),
    )
    remember_page(shop, f"lang:{lang}", sent)


@router.callback_query(LangCB.filter())
async def set_lang(
    callback: CallbackQuery,
    callback_data: LangCB,
    bot: Bot,
    db_user: User,
    shop: ShopSettings,
) -> None:
    if callback_data.code not in {"ru", "en"}:
        await callback.answer()
        return
    db_user.language = callback_data.code
    lang = db_user.language
    await callback.answer(t(lang, "lang.set"))
    photo = page_cover(
        shop,
        f"lang:{lang}",
        eyebrow=t(lang, "cover.lang"),
        title=t(lang, "settings.title"),
        footer=t(lang, "cover.foot.lang"),
        accent=2,
    )
    sent = await show_screen(
        bot=bot,
        user=db_user,
        event=callback,
        html=settings_html(lang),
        caption=settings_caption(lang),
        photo=photo,
        reply_markup=settings_kb(lang),
    )
    remember_page(shop, f"lang:{lang}", sent)
    await bot.send_message(db_user.tg_id, t(lang, "lang.set"), reply_markup=main_reply(db_user))


@router.message(MenuButton("btn.support"))
async def support_open(
    message: Message, bot: Bot, db_user: User, shop: ShopSettings, state: FSMContext
) -> None:
    await state.set_state(UserStates.support)
    lang = db_user.language
    rules = loc(shop, "rules", lang)
    photo = page_cover(
        shop,
        f"help:{lang}",
        eyebrow=t(lang, "cover.support"),
        title=t(lang, "support.title"),
        subtitle=t(lang, "support.body"),
        footer=t(lang, "cover.foot.support"),
        accent=3,
    )
    sent = await show_screen(
        bot=bot,
        user=db_user,
        event=message,
        html=support_html(lang, rules),
        caption=support_caption(lang, rules),
        photo=photo,
    )
    remember_page(shop, f"help:{lang}", sent)


@router.message(StateFilter(UserStates.support), NotMenu(), F.content_type.in_({"text", "photo", "document"}))
async def support_msg(
    message: Message,
    bot: Bot,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    ticket = await open_or_get_ticket(session, db_user.id)
    kind = "text"
    file_id = None
    text = message.text or message.caption
    if message.photo:
        kind = "photo"
        file_id = message.photo[-1].file_id
    elif message.document:
        kind = "document"
        file_id = message.document.file_id
    await add_ticket_message(session, ticket=ticket, from_staff=False, text=text, file_id=file_id, kind=kind)
    await message.answer(t(db_user.language, "support.sent"))
    for tg in await staff_ids(session):
        try:
            await bot.send_message(tg, f"Тикет #{ticket.id} от {db_user.tg_id}: {text or kind}")
        except Exception:
            pass


@router.callback_query(NavCB.filter(F.to == "promo"))
async def promo_ask(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    await state.set_state(UserStates.promo)
    await callback.answer()
    if callback.message:
        await callback.message.answer(t(db_user.language, "promo.ask"))


@router.message(StateFilter(UserStates.promo), F.text)
async def promo_use(message: Message, session: AsyncSession, db_user: User, state: FSMContext) -> None:
    await state.clear()
    try:
        amount = await redeem_promo(session, user_id=db_user.id, code=message.text or "")
    except ShopError:
        await message.answer(t(db_user.language, "promo.bad"))
        return
    await message.answer(t(db_user.language, "promo.ok", amount=format_rub(amount, db_user.language)))


@router.callback_query(NavCB.filter(F.to == "ord"))
async def orders_list(
    callback: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    db_user: User,
    shop: ShopSettings,
) -> None:
    result = await session.execute(
        select(Order).where(Order.user_id == db_user.id).order_by(Order.id.desc()).limit(15)
    )
    orders = list(result.scalars().all())
    lang = db_user.language
    if not orders:
        await callback.answer(t(lang, "orders.empty"), show_alert=True)
        return
    rows = [[str(o.id), o.status.value, format_rub(o.price_kopecks, lang)] for o in orders]
    from app.ui.rich import h1, join, table

    photo = page_cover(
        shop,
        f"orders:{lang}",
        eyebrow=t(lang, "cover.orders"),
        title=t(lang, "orders.title"),
        footer=t(lang, "cover.foot.orders"),
        accent=1,
    )
    sent = await show_screen(
        bot=bot,
        user=db_user,
        event=callback,
        html=join(h1(t(lang, "orders.title")), table(["№", t(lang, "receipt.sum"), ""], [[r[0], r[2], r[1]] for r in rows])),
        caption=orders_caption(lang, [[r[0], r[2], r[1]] for r in rows]),
        photo=photo,
        reply_markup=profile_kb(lang),
    )
    remember_page(shop, f"orders:{lang}", sent)


@router.callback_query(NavCB.filter(F.to.in_({"faq", "rules"})))
async def texts(
    callback: CallbackQuery,
    callback_data: NavCB,
    bot: Bot,
    db_user: User,
    shop: ShopSettings,
) -> None:
    field = "faq" if callback_data.to == "faq" else "rules"
    body = loc(shop, field, db_user.language) or t(db_user.language, "support.rules_default")
    lang = db_user.language
    title = t(lang, "btn.faq" if field == "faq" else "btn.rules")
    from app.ui.rich import h1, join, p

    slot = f"{field}:{lang}"
    photo = page_cover(
        shop,
        slot,
        eyebrow=t(lang, f"cover.{field}"),
        title=title,
        footer=t(lang, "trust.support"),
        accent=2,
    )
    sent = await show_screen(
        bot=bot,
        user=db_user,
        event=callback,
        html=join(h1(title), p(body)),
        caption=text_caption(title, body),
        photo=photo,
        reply_markup=profile_kb(lang),
    )
    remember_page(shop, slot, sent)


@router.callback_query(SubCB.filter())
async def check_sub(
    callback: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    db_user: User,
    shop: ShopSettings,
    bot_title: str = "",
) -> None:
    channels = await active_channels(session, shop)
    ok = await user_subscribed(bot, db_user.tg_id, channels)
    lang = db_user.language
    if not ok:
        await callback.answer(t(lang, "sub.fail"), show_alert=True)
        return
    await callback.answer(t(lang, "sub.ok"))
    title = shop_heading(shop, lang, bot_title)
    photo = await shop_banner(bot, session, shop, title)
    sent = await show_screen(
        bot=bot,
        user=db_user,
        event=callback,
        html=home_html(db_user, shop, bot_title),
        caption=home_caption(db_user, shop, bot_title),
        photo=photo,
        reply_keyboard=main_reply(db_user),
    )
    remember_photo(sent, shop)
