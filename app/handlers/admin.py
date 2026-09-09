from __future__ import annotations

from datetime import datetime, timezone

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.i18n import t
from app.keyboards.filters import MenuButton, NotMenu
from app.keyboards.build import admin_root_kb
from app.keyboards.callbacks import AdmCB
from app.models import (
    Broadcast,
    Category,
    DeliveryKind,
    FulfillmentMode,
    Order,
    OrderStatus,
    Payment,
    PaymentStatus,
    Product,
    ProductPart,
    PromoCode,
    RequiredChannel,
    Role,
    ShopSettings,
    StockItem,
    Ticket,
    TicketStatus,
    User,
)
from app.security.money import format_rub, rub_to_kopecks
from app.services.broadcast import enqueue_broadcast
from app.services.ops import add_ticket_message, write_audit
from app.services.shop import credit_balance, refund_order
from app.services.users import has_admin_access, has_owner_access, has_staff_access
from app.states import AdminStates
from app.ui.rich import h1, join, p, table
from app.ui.screens import show_screen
from redis.asyncio import Redis

router = Router(name="admin")

REF_FIELDS = [
    ("dep", "% с пополнения", "percent"),
    ("buy", "% с покупки", "percent"),
    ("star", "1 звезда в рублях", "stars"),
    ("min", "Мин. пополнение, ₽", "money"),
    ("bon", "Бонус новичка, ₽", "money"),
]

TEXT_FIELDS = [
    ("shop_title_ru", "Название RU"),
    ("shop_title_en", "Название EN"),
    ("welcome_ru", "Приветствие RU"),
    ("welcome_en", "Приветствие EN"),
    ("rules_ru", "Правила RU"),
    ("rules_en", "Правила EN"),
    ("faq_ru", "Вопросы RU"),
    ("faq_en", "Вопросы EN"),
]


def _staff_ok(user: User) -> bool:
    return has_staff_access(user)


async def _deny(event: Message | CallbackQuery, user: User) -> bool:
    if _staff_ok(user):
        return False
    text = t(user.language, "admin.denied")
    if isinstance(event, CallbackQuery):
        await event.answer(text, show_alert=True)
    else:
        await event.answer(text)
    return True


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Отмена", callback_data=AdmCB(act="x").pack())]]
    )


def home_btn() -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(text="В админку", callback_data=AdmCB(act="home").pack())]


def with_home(builder: InlineKeyboardBuilder) -> InlineKeyboardMarkup:
    builder.row(*home_btn())
    return builder.as_markup()


async def _home(event: Message | CallbackQuery, bot: Bot, db_user: User) -> None:
    await show_screen(
        bot=bot,
        user=db_user,
        event=event,
        html=join(h1("Админка"), p("Нажимайте кнопки. Текст нужен только для названий, цен и сообщений.")),
        reply_markup=admin_root_kb(),
    )


@router.message(Command("admin"))
@router.message(MenuButton("btn.admin"))
async def admin_home(event: Message, bot: Bot, db_user: User, state: FSMContext) -> None:
    if await _deny(event, db_user):
        return
    await state.clear()
    await _home(event, bot, db_user)


@router.callback_query(AdmCB.filter(F.act == "home"))
async def admin_home_cb(callback: CallbackQuery, bot: Bot, db_user: User, state: FSMContext) -> None:
    if await _deny(callback, db_user):
        return
    await state.clear()
    await _home(callback, bot, db_user)


@router.callback_query(AdmCB.filter(F.act == "x"))
async def admin_cancel(callback: CallbackQuery, bot: Bot, db_user: User, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("Отменено")
    await _home(callback, bot, db_user)


@router.callback_query(AdmCB.filter(F.act == "dash"))
async def dash(callback: CallbackQuery, bot: Bot, session: AsyncSession, db_user: User) -> None:
    if await _deny(callback, db_user):
        return
    users = int((await session.execute(select(func.count(User.id)))).scalar_one())
    orders_n = int((await session.execute(select(func.count(Order.id)))).scalar_one())
    rev = int(
        (
            await session.execute(
                select(func.coalesce(func.sum(Order.price_kopecks), 0)).where(
                    Order.status.in_([OrderStatus.DELIVERED, OrderStatus.PENDING_MANUAL, OrderStatus.PAID])
                )
            )
        ).scalar_one()
    )
    stars = int(
        (
            await session.execute(
                select(func.coalesce(func.sum(Payment.stars_amount), 0)).where(
                    Payment.status == PaymentStatus.COMPLETED
                )
            )
        ).scalar_one()
    )
    pending = int(
        (
            await session.execute(
                select(func.count(Order.id)).where(Order.status == OrderStatus.PENDING_MANUAL)
            )
        ).scalar_one()
    )
    html = join(
        h1("Статистика"),
        table(
            ["Что", "Сейчас"],
            [
                ["Людей в боте", str(users)],
                ["Покупок", str(orders_n)],
                ["Оборот", format_rub(rev, "ru")],
                ["Звёзд пришло", str(stars)],
                ["Ждут ручную выдачу", str(pending)],
            ],
        ),
    )
    b = InlineKeyboardBuilder()
    if pending:
        b.button(text=f"Открыть заказы ({pending})", callback_data=AdmCB(act="ords").pack())
    await show_screen(bot=bot, user=db_user, event=callback, html=html, reply_markup=with_home(b))


@router.callback_query(AdmCB.filter(F.act == "cats"))
async def cats(callback: CallbackQuery, bot: Bot, session: AsyncSession, db_user: User) -> None:
    if not has_admin_access(db_user):
        await callback.answer(t(db_user.language, "admin.denied"), show_alert=True)
        return
    items = list((await session.execute(select(Category).order_by(Category.sort, Category.id))).scalars().all())
    rows = [[c.title_ru, "видна" if c.is_active else "скрыта"] for c in items]
    b = InlineKeyboardBuilder()
    b.button(text="Добавить категорию", callback_data=AdmCB(act="cat_new").pack())
    for c in items:
        mark = "Скрыть" if c.is_active else "Показать"
        b.button(text=f"{mark}: {c.title_ru[:28]}", callback_data=AdmCB(act="cat_t", id=c.id).pack())
    b.adjust(1)
    await show_screen(
        bot=bot,
        user=db_user,
        event=callback,
        html=join(h1("Категории"), table(["Название", ""], rows) if rows else p("Пока пусто. Нажмите «Добавить».")),
        reply_markup=with_home(b),
    )


@router.callback_query(AdmCB.filter(F.act == "cat_new"))
async def cat_new(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    if not has_admin_access(db_user):
        return
    await state.set_state(AdminStates.cat_ru)
    await callback.answer()
    await callback.message.answer("Напишите название категории (как увидит покупатель):", reply_markup=cancel_kb())


@router.message(StateFilter(AdminStates.cat_ru), NotMenu(), F.text)
async def cat_ru(message: Message, state: FSMContext) -> None:
    await state.update_data(cat_ru=message.text[:120])
    await state.set_state(AdminStates.cat_en)
    b = InlineKeyboardBuilder()
    b.button(text="Оставить то же на английском", callback_data=AdmCB(act="cat_en").pack())
    b.button(text="Отмена", callback_data=AdmCB(act="x").pack())
    b.adjust(1)
    await message.answer("Английское название — напишите текстом или нажмите кнопку.", reply_markup=b.as_markup())


@router.callback_query(AdmCB.filter(F.act == "cat_en"))
async def cat_en_same(callback: CallbackQuery, state: FSMContext, session: AsyncSession, db_user: User, bot: Bot) -> None:
    data = await state.get_data()
    title = str(data.get("cat_ru") or "")
    await state.clear()
    if not title:
        await callback.answer("Сначала название")
        return
    session.add(Category(title_ru=title, title_en=title))
    await write_audit(session, actor_id=db_user.id, action="category.create", target=title)
    await callback.answer("Категория создана")
    await cats(callback, bot, session, db_user)


@router.message(StateFilter(AdminStates.cat_en), NotMenu(), F.text)
async def cat_en(message: Message, state: FSMContext, session: AsyncSession, db_user: User) -> None:
    data = await state.get_data()
    await state.clear()
    session.add(Category(title_ru=data["cat_ru"], title_en=message.text[:120]))
    await write_audit(session, actor_id=db_user.id, action="category.create", target=data["cat_ru"])
    await message.answer("Категория создана.", reply_markup=admin_root_kb())


@router.callback_query(AdmCB.filter(F.act == "cat_t"))
async def cat_toggle(callback: CallbackQuery, callback_data: AdmCB, session: AsyncSession, db_user: User, bot: Bot) -> None:
    if not has_admin_access(db_user):
        return
    cat = await session.get(Category, callback_data.id)
    if cat:
        cat.is_active = not cat.is_active
        await callback.answer("Показываем" if cat.is_active else "Скрыли")
    await cats(callback, bot, session, db_user)


@router.callback_query(AdmCB.filter(F.act == "prds"))
async def prds(callback: CallbackQuery, bot: Bot, session: AsyncSession, db_user: User) -> None:
    if not has_admin_access(db_user):
        await callback.answer("Нет доступа", show_alert=True)
        return
    items = list((await session.execute(select(Product).order_by(Product.id.desc()).limit(20))).scalars().all())
    rows = [[item.title_ru, format_rub(item.price_kopecks), "в продаже" if item.is_active else "скрыт"] for item in items]
    b = InlineKeyboardBuilder()
    b.button(text="Добавить товар", callback_data=AdmCB(act="prd_new").pack())
    for item in items:
        b.button(
            text=f"{item.title_ru[:28]} · {format_rub(item.price_kopecks)}",
            callback_data=AdmCB(act="prd_v", id=item.id).pack(),
        )
    b.adjust(1)
    body = table(["Товар", "Цена", ""], rows) if rows else p("Пока пусто. Сначала категория, потом «Добавить товар».")
    await show_screen(
        bot=bot,
        user=db_user,
        event=callback,
        html=join(h1("Товары"), body),
        reply_markup=with_home(b),
    )


@router.callback_query(AdmCB.filter(F.act == "prd_new"))
async def prd_new(callback: CallbackQuery, session: AsyncSession, state: FSMContext, db_user: User) -> None:
    if not has_admin_access(db_user):
        return
    cats_list = list((await session.execute(select(Category).order_by(Category.sort, Category.id))).scalars().all())
    if not cats_list:
        await callback.message.answer("Сначала в админке откройте «Категории» и нажмите «Добавить категорию». Потом сюда — «Добавить товар».")
        return
    await state.set_state(AdminStates.prd_cat)
    await callback.answer()
    b = InlineKeyboardBuilder()
    for c in cats_list:
        b.button(text=c.title_ru[:40], callback_data=AdmCB(act="pc", id=c.id).pack())
    b.button(text="Отмена", callback_data=AdmCB(act="x").pack())
    b.adjust(1)
    await callback.message.answer("В какую категорию кладём товар?", reply_markup=b.as_markup())


@router.callback_query(AdmCB.filter(F.act == "pc"))
async def prd_pick_cat(callback: CallbackQuery, callback_data: AdmCB, state: FSMContext) -> None:
    await state.update_data(cat_id=callback_data.id)
    await state.set_state(AdminStates.prd_ru)
    await callback.answer()
    await callback.message.answer("Напишите название товара:", reply_markup=cancel_kb())


@router.message(StateFilter(AdminStates.prd_ru), NotMenu(), F.text)
async def prd_ru(message: Message, state: FSMContext) -> None:
    await state.update_data(ru=message.text[:180], en=message.text[:180])
    await state.set_state(AdminStates.prd_en)
    b = InlineKeyboardBuilder()
    b.button(text="Оставить то же на английском", callback_data=AdmCB(act="psame").pack())
    b.button(text="Отмена", callback_data=AdmCB(act="x").pack())
    b.adjust(1)
    await message.answer("Английское название — текстом или кнопка.", reply_markup=b.as_markup())


@router.callback_query(AdmCB.filter(F.act == "psame"))
async def prd_en_same(callback: CallbackQuery, state: FSMContext) -> None:
    await _after_title(callback, state)


@router.message(StateFilter(AdminStates.prd_en), NotMenu(), F.text)
async def prd_en(message: Message, state: FSMContext) -> None:
    await state.update_data(en=message.text[:180])
    await _ask_desc(message, state)


async def _after_title(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await _ask_desc(callback.message, state)


async def _ask_desc(target: Message, state: FSMContext) -> None:
    await state.update_data(dru="", den="")
    await state.set_state(AdminStates.prd_desc_ru)
    b = InlineKeyboardBuilder()
    b.button(text="Без описания", callback_data=AdmCB(act="pd0").pack())
    b.button(text="Отмена", callback_data=AdmCB(act="x").pack())
    b.adjust(1)
    await target.answer("Описание товара — напишите текстом или пропустите.", reply_markup=b.as_markup())


@router.callback_query(AdmCB.filter(F.act == "pd0"))
async def prd_skip_desc(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(dru="", den="")
    await state.set_state(AdminStates.prd_price)
    await callback.answer()
    await callback.message.answer("Напишите цену в рублях, например 199", reply_markup=cancel_kb())


@router.message(StateFilter(AdminStates.prd_desc_ru), NotMenu(), F.text)
async def prd_d_ru(message: Message, state: FSMContext) -> None:
    await state.update_data(dru=message.text[:4000], den=message.text[:4000])
    await state.set_state(AdminStates.prd_price)
    await message.answer("Напишите цену в рублях, например 199", reply_markup=cancel_kb())


@router.message(StateFilter(AdminStates.prd_price), NotMenu(), F.text)
async def prd_price(message: Message, state: FSMContext) -> None:
    try:
        price = rub_to_kopecks((message.text or "").replace(",", ".").split()[0])
    except Exception:
        await message.answer("Нужна цена цифрами, например 199")
        return
    await state.update_data(price=price)
    b = InlineKeyboardBuilder()
    b.button(text="Выдать сразу", callback_data=AdmCB(act="pauto").pack())
    b.button(text="Выдать вручную", callback_data=AdmCB(act="pman").pack())
    b.button(text="Отмена", callback_data=AdmCB(act="x").pack())
    b.adjust(1)
    await message.answer("Как отдаём товар после оплаты?", reply_markup=b.as_markup())


@router.callback_query(AdmCB.filter(F.act.in_({"pauto", "pman"})))
async def prd_mode(callback: CallbackQuery, callback_data: AdmCB, state: FSMContext) -> None:
    await state.update_data(mode=callback_data.act)
    b = InlineKeyboardBuilder()
    b.button(text="Одинаковый всем (ссылка, файл)", callback_data=AdmCB(act="pst0").pack())
    b.button(text="Уникальный из списка (ключи)", callback_data=AdmCB(act="pst1").pack())
    b.button(text="Отмена", callback_data=AdmCB(act="x").pack())
    b.adjust(1)
    await callback.answer()
    await callback.message.answer("Что выдаём?", reply_markup=b.as_markup())


@router.callback_query(AdmCB.filter(F.act.in_({"pst0", "pst1"})))
async def prd_create(
    callback: CallbackQuery,
    callback_data: AdmCB,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
) -> None:
    data = await state.get_data()
    mode = FulfillmentMode.MANUAL if data.get("mode") == "pman" else FulfillmentMode.AUTO
    use_stock = callback_data.act == "pst1"
    product = Product(
        category_id=int(data["cat_id"]),
        title_ru=data["ru"],
        title_en=data.get("en") or data["ru"],
        description_ru=data.get("dru") or "",
        description_en=data.get("den") or "",
        price_kopecks=int(data["price"]),
        fulfillment=mode,
        use_stock=use_stock,
    )
    session.add(product)
    await session.flush()
    await write_audit(session, actor_id=db_user.id, action="product.create", target=str(product.id))
    await state.update_data(pid=product.id, psort=0)
    await callback.answer("Товар создан")
    if use_stock:
        await state.set_state(AdminStates.stock_paste)
        await callback.message.answer(
            "Пришлите ключи/логины — каждый с новой строки.",
            reply_markup=cancel_kb(),
        )
        return
    await state.set_state(AdminStates.prd_part)
    b = InlineKeyboardBuilder()
    b.button(text="Готово, хватит", callback_data=AdmCB(act="pdon").pack())
    b.button(text="Отмена", callback_data=AdmCB(act="x").pack())
    b.adjust(1)
    await callback.message.answer(
        "Пришлите, что получит покупатель: текст, фото или файл. Можно несколько сообщений.",
        reply_markup=b.as_markup(),
    )


@router.callback_query(AdmCB.filter(F.act == "pdon"))
async def prd_done_btn(callback: CallbackQuery, state: FSMContext, bot: Bot, db_user: User, session: AsyncSession) -> None:
    await state.clear()
    await callback.answer("Сохранено")
    await prds(callback, bot, session, db_user)


@router.message(Command("done"), StateFilter(AdminStates.prd_part))
async def prd_done(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Сохранено.", reply_markup=admin_root_kb())


@router.message(StateFilter(AdminStates.prd_part), NotMenu())
async def prd_part(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if message.text and message.text.startswith("/"):
        return
    data = await state.get_data()
    pid = int(data["pid"])
    sort = int(data.get("psort", 0))
    kind = DeliveryKind.TEXT
    file_id = None
    text = message.text or message.caption
    caption = message.caption
    if message.photo:
        kind = DeliveryKind.PHOTO
        file_id = message.photo[-1].file_id
    elif message.document:
        kind = DeliveryKind.DOCUMENT
        file_id = message.document.file_id
    elif message.video:
        kind = DeliveryKind.VIDEO
        file_id = message.video.file_id
    elif message.animation:
        kind = DeliveryKind.ANIMATION
        file_id = message.animation.file_id
    elif message.audio:
        kind = DeliveryKind.AUDIO
        file_id = message.audio.file_id
    session.add(ProductPart(product_id=pid, sort=sort, kind=kind, text=text, file_id=file_id, caption=caption))
    await state.update_data(psort=sort + 1)
    b = InlineKeyboardBuilder()
    b.button(text="Готово, хватит", callback_data=AdmCB(act="pdon").pack())
    await message.answer(f"Добавлено ({sort + 1}). Ещё файл/текст или «Готово».", reply_markup=b.as_markup())


@router.callback_query(AdmCB.filter(F.act == "prd_v"))
async def prd_view(callback: CallbackQuery, callback_data: AdmCB, bot: Bot, session: AsyncSession, db_user: User) -> None:
    prod = await session.get(Product, callback_data.id)
    if prod is None:
        await callback.answer("Нет такого")
        return
    stock = int(
        (
            await session.execute(
                select(func.count(StockItem.id)).where(
                    StockItem.product_id == prod.id, StockItem.is_sold.is_(False)
                )
            )
        ).scalar_one()
    )
    html = join(
        h1(prod.title_ru),
        table(
            ["", ""],
            [
                ["Цена", format_rub(prod.price_kopecks)],
                ["Выдача", "вручную" if prod.fulfillment == FulfillmentMode.MANUAL else "сразу"],
                ["Сток", str(stock) if prod.use_stock else "не используется"],
                ["В каталоге", "да" if prod.is_active else "скрыт"],
                ["Хит", "да" if prod.is_featured else "нет"],
                ["Обложка", "своя" if prod.cover_file_id else "шаблон"],
            ],
        ),
    )
    b = InlineKeyboardBuilder()
    b.button(
        text="Скрыть из каталога" if prod.is_active else "Показать в каталоге",
        callback_data=AdmCB(act="prd_t", id=prod.id).pack(),
    )
    b.button(
        text="Убрать из хитов" if prod.is_featured else "Показать как хит",
        callback_data=AdmCB(act="pft", id=prod.id).pack(),
    )
    b.button(text="Своя обложка (фото)", callback_data=AdmCB(act="pcov", id=prod.id).pack())
    b.button(text="Сгенерировать обложку", callback_data=AdmCB(act="pgen", id=prod.id).pack())
    b.button(
        text="Выдавать сразу" if prod.fulfillment == FulfillmentMode.MANUAL else "Выдавать вручную",
        callback_data=AdmCB(act="pfl", id=prod.id).pack(),
    )
    b.button(text="Добавить ключи в сток", callback_data=AdmCB(act="stk", id=prod.id).pack())
    b.button(text="Добавить файлы выдачи", callback_data=AdmCB(act="padd", id=prod.id).pack())
    b.button(text="К списку товаров", callback_data=AdmCB(act="prds").pack())
    b.adjust(1)
    await show_screen(bot=bot, user=db_user, event=callback, html=html, reply_markup=with_home(b))


@router.callback_query(AdmCB.filter(F.act == "prd_t"))
async def prd_toggle(callback: CallbackQuery, callback_data: AdmCB, session: AsyncSession, db_user: User, bot: Bot) -> None:
    prod = await session.get(Product, callback_data.id)
    if prod:
        prod.is_active = not prod.is_active
    await callback.answer("Ок")
    await prd_view(callback, callback_data, bot, session, db_user)


@router.callback_query(AdmCB.filter(F.act == "pft"))
async def prd_featured(callback: CallbackQuery, callback_data: AdmCB, session: AsyncSession, db_user: User, bot: Bot) -> None:
    prod = await session.get(Product, callback_data.id)
    if prod:
        prod.is_featured = not prod.is_featured
    await callback.answer("Хит" if prod and prod.is_featured else "Не хит")
    await prd_view(callback, callback_data, bot, session, db_user)


@router.callback_query(AdmCB.filter(F.act == "pcov"))
async def prd_cover_ask(callback: CallbackQuery, callback_data: AdmCB, state: FSMContext, db_user: User) -> None:
    if not has_admin_access(db_user):
        return
    await state.set_state(AdminStates.prd_cover)
    await state.update_data(pid=callback_data.id)
    await callback.answer()
    await callback.message.answer("Пришлите одно фото — это обложка в каталоге.", reply_markup=cancel_kb())


@router.message(StateFilter(AdminStates.prd_cover), F.photo)
async def prd_cover_set(message: Message, state: FSMContext, session: AsyncSession, shop: ShopSettings) -> None:
    data = await state.get_data()
    await state.clear()
    prod = await session.get(Product, int(data["pid"]))
    if prod is None:
        await message.answer("Товар пропал")
        return
    prod.cover_file_id = message.photo[-1].file_id
    extra = dict(shop.extra or {})
    custom = dict(extra.get("custom_covers") or {})
    custom[str(prod.id)] = True
    extra["custom_covers"] = custom
    shop.extra = extra
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(shop, "extra")
    await message.answer("Обложка сохранена.", reply_markup=admin_root_kb())


@router.callback_query(AdmCB.filter(F.act == "pgen"))
async def prd_cover_gen(callback: CallbackQuery, callback_data: AdmCB, session: AsyncSession, db_user: User, bot: Bot, shop: ShopSettings) -> None:
    prod = await session.get(Product, callback_data.id)
    if prod:
        prod.cover_file_id = None
    extra = dict(shop.extra or {})
    custom = dict(extra.get("custom_covers") or {})
    custom.pop(str(callback_data.id), None)
    extra["custom_covers"] = custom
    pages = dict(extra.get("pages") or {})
    for key in list(pages):
        if key.startswith(f"p:{callback_data.id}:"):
            pages.pop(key, None)
    extra["pages"] = pages
    shop.extra = extra
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(shop, "extra")
    await callback.answer("Будет шаблон с названием и ценой")
    await prd_view(callback, callback_data, bot, session, db_user)


@router.callback_query(AdmCB.filter(F.act == "pfl"))
async def prd_flip_mode(callback: CallbackQuery, callback_data: AdmCB, session: AsyncSession, db_user: User, bot: Bot) -> None:
    prod = await session.get(Product, callback_data.id)
    if prod:
        prod.fulfillment = (
            FulfillmentMode.AUTO if prod.fulfillment == FulfillmentMode.MANUAL else FulfillmentMode.MANUAL
        )
    await callback.answer("Ок")
    await prd_view(callback, callback_data, bot, session, db_user)


@router.callback_query(AdmCB.filter(F.act == "padd"))
async def prd_add_parts(callback: CallbackQuery, callback_data: AdmCB, state: FSMContext) -> None:
    await state.set_state(AdminStates.prd_part)
    await state.update_data(pid=callback_data.id, psort=100)
    await callback.answer()
    b = InlineKeyboardBuilder()
    b.button(text="Готово", callback_data=AdmCB(act="pdon").pack())
    await callback.message.answer("Пришлите текст/фото/файл для выдачи.", reply_markup=b.as_markup())


@router.callback_query(AdmCB.filter(F.act == "stk"))
async def stock_ask(callback: CallbackQuery, callback_data: AdmCB, state: FSMContext, db_user: User) -> None:
    if not has_admin_access(db_user):
        return
    await state.set_state(AdminStates.stock_paste)
    await state.update_data(pid=callback_data.id)
    await callback.answer()
    await callback.message.answer("Ключи/логины — каждый с новой строки.", reply_markup=cancel_kb())


@router.message(StateFilter(AdminStates.stock_paste), NotMenu(), F.text)
async def stock_paste(message: Message, state: FSMContext, session: AsyncSession, db_user: User) -> None:
    data = await state.get_data()
    await state.clear()
    pid = int(data["pid"])
    lines = [ln.strip() for ln in (message.text or "").splitlines() if ln.strip()]
    for line in lines[:5000]:
        session.add(StockItem(product_id=pid, payload=line[:4000]))
    prod = await session.get(Product, pid)
    if prod:
        prod.use_stock = True
    await write_audit(session, actor_id=db_user.id, action="stock.add", target=str(pid), details={"n": len(lines)})
    await message.answer(f"Добавлено {len(lines)} шт.", reply_markup=admin_root_kb())


@router.callback_query(AdmCB.filter(F.act == "ords"))
async def ords(callback: CallbackQuery, bot: Bot, session: AsyncSession, db_user: User) -> None:
    if await _deny(callback, db_user):
        return
    items = list((await session.execute(select(Order).order_by(Order.id.desc()).limit(12))).scalars().all())
    rows = [
        [str(o.id), o.status.value.replace("pending_manual", "ждёт выдачи").replace("delivered", "выдан"), format_rub(o.price_kopecks)]
        for o in items
    ]
    b = InlineKeyboardBuilder()
    b.button(text="Только ждут выдачи", callback_data=AdmCB(act="ordp").pack())
    b.button(text="Все заказы", callback_data=AdmCB(act="ords").pack())
    for o in items:
        if o.status == OrderStatus.PENDING_MANUAL:
            b.button(text=f"Отметить выданным #{o.id}", callback_data=AdmCB(act="ord_ok", id=o.id).pack())
        if has_admin_access(db_user) and o.status != OrderStatus.REFUNDED:
            b.button(text=f"Вернуть деньги #{o.id}", callback_data=AdmCB(act="ord_rf", id=o.id).pack())
    b.adjust(1)
    await show_screen(
        bot=bot,
        user=db_user,
        event=callback,
        html=join(h1("Заказы"), table(["№", "Статус", "Сумма"], rows) if rows else p("Заказов нет")),
        reply_markup=with_home(b),
    )


@router.callback_query(AdmCB.filter(F.act == "ordp"))
async def ords_pending(callback: CallbackQuery, bot: Bot, session: AsyncSession, db_user: User) -> None:
    if await _deny(callback, db_user):
        return
    items = list(
        (
            await session.execute(
                select(Order)
                .where(Order.status == OrderStatus.PENDING_MANUAL)
                .order_by(Order.id.desc())
                .limit(15)
            )
        ).scalars().all()
    )
    rows = [[str(o.id), format_rub(o.price_kopecks)] for o in items]
    b = InlineKeyboardBuilder()
    for o in items:
        b.button(text=f"Выдан #{o.id}", callback_data=AdmCB(act="ord_ok", id=o.id).pack())
    b.button(text="Все заказы", callback_data=AdmCB(act="ords").pack())
    b.adjust(1)
    await show_screen(
        bot=bot,
        user=db_user,
        event=callback,
        html=join(h1("Ждут выдачи"), table(["№", "Сумма"], rows) if rows else p("Очереди нет")),
        reply_markup=with_home(b),
    )


@router.callback_query(AdmCB.filter(F.act == "ord_ok"))
async def ord_ok(callback: CallbackQuery, callback_data: AdmCB, session: AsyncSession, db_user: User, bot: Bot) -> None:
    order = await session.get(Order, callback_data.id)
    if order and order.status == OrderStatus.PENDING_MANUAL:
        order.status = OrderStatus.DELIVERED
        order.delivered_at = datetime.now(timezone.utc)
        await write_audit(session, actor_id=db_user.id, action="order.deliver", target=str(order.id))
    await callback.answer("Отметили")
    await ords_pending(callback, bot, session, db_user)


@router.callback_query(AdmCB.filter(F.act == "ord_rf"))
async def ord_rf(callback: CallbackQuery, callback_data: AdmCB, session: AsyncSession, db_user: User) -> None:
    if not has_admin_access(db_user):
        return
    await refund_order(session, callback_data.id)
    await write_audit(session, actor_id=db_user.id, action="order.refund", target=str(callback_data.id))
    await callback.answer("Деньги вернули на баланс")


@router.callback_query(AdmCB.filter(F.act == "users"))
async def users_ask(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    if not has_admin_access(db_user):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.set_state(AdminStates.user_query)
    await callback.answer()
    await callback.message.answer("Напишите Telegram ID или @username человека:", reply_markup=cancel_kb())


@router.message(StateFilter(AdminStates.user_query), NotMenu(), F.text)
async def user_find(message: Message, state: FSMContext, session: AsyncSession, db_user: User) -> None:
    await state.clear()
    q = (message.text or "").strip().lstrip("@")
    stmt = select(User)
    stmt = stmt.where(User.tg_id == int(q)) if q.isdigit() else stmt.where(User.username.ilike(q))
    user = (await session.execute(stmt)).scalar_one_or_none()
    if user is None:
        await message.answer("Не нашли. Проверьте ID.")
        return
    await _user_card(message, user, db_user)


async def _user_card(event: Message | CallbackQuery, user: User, actor: User) -> None:
    html = join(
        h1(str(user.tg_id)),
        table(
            ["", ""],
            [
                ["Ник", user.username or "—"],
                ["Роль", user.role.value],
                ["Баланс", format_rub(user.balance_kopecks)],
                ["Бан", "да" if user.is_banned else "нет"],
            ],
        ),
    )
    b = InlineKeyboardBuilder()
    b.button(text="Забанить" if not user.is_banned else "Разбанить", callback_data=AdmCB(act="uban", id=user.id).pack())
    for label, rub in (("+100 ₽", 100), ("+500 ₽", 500), ("+1000 ₽", 1000)):
        b.button(text=label, callback_data=AdmCB(act="ubp", id=user.id, p=rub).pack())
    b.button(text="Своя сумма", callback_data=AdmCB(act="ubal", id=user.id).pack())
    if has_owner_access(actor):
        b.button(text="Сделать саппортом", callback_data=AdmCB(act="rl", id=user.id, p=1).pack())
        b.button(text="Сделать админом", callback_data=AdmCB(act="rl", id=user.id, p=2).pack())
        b.button(text="Снять до покупателя", callback_data=AdmCB(act="rl", id=user.id, p=0).pack())
    b.adjust(1)
    markup = with_home(b)
    bot = event.bot
    await show_screen(bot=bot, user=actor, event=event, html=html, reply_markup=markup)


@router.callback_query(AdmCB.filter(F.act == "uban"))
async def uban(callback: CallbackQuery, callback_data: AdmCB, session: AsyncSession, settings: Settings, db_user: User) -> None:
    user = await session.get(User, callback_data.id)
    if user is None or user.tg_id in settings.owners:
        await callback.answer("Этого нельзя", show_alert=True)
        return
    user.is_banned = not user.is_banned
    await write_audit(session, actor_id=db_user.id, action="user.ban", target=str(user.tg_id))
    await callback.answer("Забанен" if user.is_banned else "Разбанен")
    await _user_card(callback, user, db_user)


@router.callback_query(AdmCB.filter(F.act == "ubp"))
async def ubal_preset(callback: CallbackQuery, callback_data: AdmCB, session: AsyncSession, db_user: User) -> None:
    user = await session.get(User, callback_data.id)
    if user is None:
        return
    await credit_balance(session, user_id=user.id, amount_kopecks=callback_data.p * 100, source="admin")
    await session.refresh(user)
    await write_audit(session, actor_id=db_user.id, action="user.balance", target=str(user.tg_id))
    await callback.answer("Начислили")
    await _user_card(callback, user, db_user)


@router.callback_query(AdmCB.filter(F.act == "ubal"))
async def ubal_ask(callback: CallbackQuery, callback_data: AdmCB, state: FSMContext) -> None:
    await state.set_state(AdminStates.user_balance)
    await state.update_data(uid=callback_data.id)
    await callback.answer()
    await callback.message.answer("Напишите сумму в рублях. Минус — списать, например -50", reply_markup=cancel_kb())


@router.message(StateFilter(AdminStates.user_balance), NotMenu(), F.text)
async def ubal_set(message: Message, state: FSMContext, session: AsyncSession, db_user: User) -> None:
    data = await state.get_data()
    await state.clear()
    raw = (message.text or "").replace(",", ".").replace(" ", "")
    try:
        kopecks = rub_to_kopecks(raw.lstrip("-"))
        if raw.startswith("-"):
            kopecks = -kopecks
    except Exception:
        await message.answer("Нужны цифры")
        return
    user = await session.get(User, int(data["uid"]))
    if user is None:
        return
    if kopecks >= 0:
        await credit_balance(session, user_id=user.id, amount_kopecks=kopecks, source="admin")
    else:
        user.balance_kopecks = max(0, user.balance_kopecks + kopecks)
    await write_audit(session, actor_id=db_user.id, action="user.balance", target=str(user.tg_id), details={"k": kopecks})
    await message.answer("Готово")


@router.callback_query(AdmCB.filter(F.act == "rl"))
async def role_set_btn(
    callback: CallbackQuery,
    callback_data: AdmCB,
    session: AsyncSession,
    settings: Settings,
    db_user: User,
) -> None:
    if not has_owner_access(db_user):
        await callback.answer("Только владелец", show_alert=True)
        return
    user = await session.get(User, callback_data.id)
    if user is None or user.tg_id in settings.owners:
        await callback.answer("Нельзя", show_alert=True)
        return
    mapping = {0: Role.USER, 1: Role.SUPPORT, 2: Role.ADMIN}
    user.role = mapping.get(callback_data.p, Role.USER)
    await write_audit(session, actor_id=db_user.id, action="user.role", target=str(user.tg_id))
    await callback.answer("Роль сохранена")
    await _user_card(callback, user, db_user)


@router.callback_query(AdmCB.filter(F.act == "sub"))
async def sub_menu(callback: CallbackQuery, bot: Bot, session: AsyncSession, db_user: User, shop: ShopSettings) -> None:
    if not has_admin_access(db_user):
        return
    chans = list((await session.execute(select(RequiredChannel))).scalars().all())
    rows = [[c.title, "вкл" if c.is_active else "выкл"] for c in chans]
    b = InlineKeyboardBuilder()
    b.button(
        text="Выключить обязаловку" if shop.subscription_enabled else "Включить обязаловку",
        callback_data=AdmCB(act="sub_t").pack(),
    )
    b.button(text="Добавить канал", callback_data=AdmCB(act="sub_a").pack())
    for c in chans:
        b.button(text=f"Удалить: {c.title[:24]}", callback_data=AdmCB(act="sub_d", id=c.id).pack())
    b.adjust(1)
    await show_screen(
        bot=bot,
        user=db_user,
        event=callback,
        html=join(
            h1("Подписка"),
            p("Сейчас " + ("обязательна" if shop.subscription_enabled else "выключена") + "."),
            table(["Канал", ""], rows) if rows else p("Каналов нет"),
        ),
        reply_markup=with_home(b),
    )


@router.callback_query(AdmCB.filter(F.act == "sub_t"))
async def sub_toggle(callback: CallbackQuery, session: AsyncSession, shop: ShopSettings, db_user: User, bot: Bot) -> None:
    shop.subscription_enabled = not shop.subscription_enabled
    await callback.answer("Включили" if shop.subscription_enabled else "Выключили")
    await sub_menu(callback, bot, session, db_user, shop)


@router.callback_query(AdmCB.filter(F.act == "sub_a"))
async def sub_add(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.channel_fwd)
    await callback.answer()
    await callback.message.answer(
        "Перешлите сюда любой пост из канала. Бот должен быть админом канала.",
        reply_markup=cancel_kb(),
    )


@router.message(StateFilter(AdminStates.channel_fwd), NotMenu())
async def sub_fwd(message: Message, state: FSMContext, session: AsyncSession, bot: Bot) -> None:
    chat = message.forward_from_chat
    if chat is None:
        origin = getattr(message, "forward_origin", None)
        chat = getattr(origin, "chat", None)
    if chat is None:
        await message.answer("Нужен пересланный пост из канала, не обычное сообщение.")
        return
    username = getattr(chat, "username", None)
    url = f"https://t.me/{username}" if username else ""
    title = getattr(chat, "title", None) or str(chat.id)
    if not url:
        await state.update_data(cid=chat.id, title=title)
        await state.set_state(AdminStates.channel_url)
        await message.answer("У канала нет @username. Пришлите пригласительную ссылку.", reply_markup=cancel_kb())
        return
    await state.clear()
    session.add(RequiredChannel(chat_id=chat.id, invite_url=url, title=title[:180]))
    await message.answer(f"Канал «{title}» добавлен.", reply_markup=admin_root_kb())


@router.message(StateFilter(AdminStates.channel_url), NotMenu(), F.text)
async def sub_url(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    await state.clear()
    session.add(
        RequiredChannel(
            chat_id=int(data["cid"]),
            invite_url=(message.text or "")[:512],
            title=str(data.get("title") or "Канал")[:180],
        )
    )
    await message.answer("Канал добавлен.", reply_markup=admin_root_kb())


@router.callback_query(AdmCB.filter(F.act == "sub_d"))
async def sub_del(callback: CallbackQuery, callback_data: AdmCB, session: AsyncSession, db_user: User, bot: Bot, shop: ShopSettings) -> None:
    ch = await session.get(RequiredChannel, callback_data.id)
    if ch:
        await session.delete(ch)
    await callback.answer("Удалили")
    await sub_menu(callback, bot, session, db_user, shop)


@router.callback_query(AdmCB.filter(F.act == "ref"))
async def ref_menu(event: Message | CallbackQuery, bot: Bot, db_user: User, shop: ShopSettings) -> None:
    if not has_admin_access(db_user):
        return
    html = join(
        h1("Рефка и курс"),
        table(
            ["", ""],
            [
                ["% с пополнения", f"{shop.referral_deposit_percent}%"],
                ["% с покупки", f"{shop.referral_purchase_percent}%"],
                ["1 звезда", format_rub(shop.stars_kopecks_per_star)],
                ["Мин. пополнение", format_rub(shop.min_topup_kopecks)],
                ["Бонус новичка", format_rub(shop.welcome_bonus_kopecks)],
            ],
        ),
        p("Нажмите строку и напишите число. 0% — рефка по этому типу выкл."),
    )
    b = InlineKeyboardBuilder()
    labels = [
        f"% с пополнения · {shop.referral_deposit_percent}%",
        f"% с покупки · {shop.referral_purchase_percent}%",
        f"Курс звезды · {format_rub(shop.stars_kopecks_per_star)}",
        f"Мин. пополнение · {format_rub(shop.min_topup_kopecks)}",
        f"Бонус новичка · {format_rub(shop.welcome_bonus_kopecks)}",
    ]
    for i, label in enumerate(labels):
        b.button(text=label, callback_data=AdmCB(act="rfe", p=i).pack())
    b.adjust(1)
    await show_screen(bot=bot, user=db_user, event=event, html=html, reply_markup=with_home(b))


@router.callback_query(AdmCB.filter(F.act == "rfe"))
async def ref_pick(callback: CallbackQuery, callback_data: AdmCB, state: FSMContext, db_user: User) -> None:
    if not has_admin_access(db_user):
        return
    idx = callback_data.p
    if idx < 0 or idx >= len(REF_FIELDS):
        await callback.answer()
        return
    _key, label, kind = REF_FIELDS[idx]
    await state.set_state(AdminStates.ref_values)
    await state.update_data(ref_i=idx)
    await callback.answer()
    if kind == "percent":
        hint = f"{label}. Напишите число от 0 до 100."
    elif kind == "stars":
        hint = f"{label}. Сколько рублей за 1 звезду, например 2 или 1.50"
    else:
        hint = f"{label}. Сумма в рублях, например 50. Ноль можно."
    await callback.message.answer(hint, reply_markup=cancel_kb())


@router.message(StateFilter(AdminStates.ref_values), NotMenu(), F.text)
async def ref_set(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    shop: ShopSettings,
    db_user: User,
    bot: Bot,
) -> None:
    data = await state.get_data()
    idx = int(data.get("ref_i", -1))
    if idx < 0 or idx >= len(REF_FIELDS):
        await state.clear()
        await message.answer("Не то поле")
        return
    raw = (message.text or "").strip().replace("%", "").replace("₽", "").replace(",", ".").split()[0]
    key, _label, kind = REF_FIELDS[idx]
    try:
        if kind == "percent":
            value = int(float(raw))
            if value < 0 or value > 100:
                raise ValueError("range")
            if key == "dep":
                shop.referral_deposit_percent = value
            else:
                shop.referral_purchase_percent = value
        else:
            kopecks = rub_to_kopecks(raw)
            if kind == "stars":
                shop.stars_kopecks_per_star = max(1, kopecks)
            elif key == "min":
                shop.min_topup_kopecks = max(100, kopecks)
            else:
                shop.welcome_bonus_kopecks = max(0, kopecks)
    except Exception:
        await message.answer("Нужно число. Например 10 или 2.50")
        return
    await state.clear()
    await write_audit(session, actor_id=db_user.id, action="shop.ref", target=key)
    await ref_menu(message, bot, db_user, shop)



@router.callback_query(AdmCB.filter(F.act == "bc"))
async def bc_seg(callback: CallbackQuery, db_user: User) -> None:
    if not has_admin_access(db_user):
        await callback.answer("Нет доступа", show_alert=True)
        return
    b = InlineKeyboardBuilder()
    b.button(text="Всем", callback_data=AdmCB(act="bcs", p=0).pack())
    b.button(text="Кто покупал", callback_data=AdmCB(act="bcs", p=1).pack())
    b.button(text="У кого есть баланс", callback_data=AdmCB(act="bcs", p=2).pack())
    b.button(text="Новые за 7 дней", callback_data=AdmCB(act="bcs", p=3).pack())
    b.button(text="Отмена", callback_data=AdmCB(act="x").pack())
    b.adjust(1)
    await callback.answer()
    await callback.message.answer("Кому шлём рассылку?", reply_markup=b.as_markup())


@router.callback_query(AdmCB.filter(F.act == "bcs"))
async def bc_body(callback: CallbackQuery, callback_data: AdmCB, state: FSMContext) -> None:
    segs = {0: "all", 1: "buyers", 2: "balance", 3: "new"}
    await state.set_state(AdminStates.broadcast)
    await state.update_data(segment=segs[callback_data.p])
    await callback.answer()
    await callback.message.answer("Напишите текст рассылки. Можно HTML: <h1>Заголовок</h1><p>Текст</p>", reply_markup=cancel_kb())


@router.message(StateFilter(AdminStates.broadcast), NotMenu(), F.text)
async def bc_send(message: Message, state: FSMContext, session: AsyncSession, db_user: User, redis: Redis) -> None:
    data = await state.get_data()
    await state.clear()
    html = (message.text or "")[:30000]
    if not html.startswith("<"):
        html = f"<p>{html}</p>"
    bc = Broadcast(created_by=db_user.id, html=html, segment=data.get("segment") or "all", status="queued")
    session.add(bc)
    await session.flush()
    await enqueue_broadcast(redis, bc.id)
    await write_audit(session, actor_id=db_user.id, action="broadcast", target=str(bc.id))
    await message.answer("Рассылка в очереди.", reply_markup=admin_root_kb())


@router.callback_query(AdmCB.filter(F.act == "promo"))
async def promo_ask(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    if not has_admin_access(db_user):
        return
    await state.set_state(AdminStates.promo_code)
    await callback.answer()
    await callback.message.answer("Напишите код промо, латиницей, например SALE50", reply_markup=cancel_kb())


@router.message(StateFilter(AdminStates.promo_code), NotMenu(), F.text)
async def promo_code(message: Message, state: FSMContext) -> None:
    await state.update_data(code=(message.text or "").strip().upper()[:32])
    b = InlineKeyboardBuilder()
    for rub in (50, 100, 250, 500, 1000):
        b.button(text=f"{rub} ₽", callback_data=AdmCB(act="pra", p=rub).pack())
    b.button(text="Отмена", callback_data=AdmCB(act="x").pack())
    b.adjust(3)
    await message.answer("На сколько рублей начисляем?", reply_markup=b.as_markup())


@router.callback_query(AdmCB.filter(F.act == "pra"))
async def promo_amt(callback: CallbackQuery, callback_data: AdmCB, state: FSMContext) -> None:
    await state.update_data(amount=callback_data.p)
    b = InlineKeyboardBuilder()
    b.button(text="Без лимита", callback_data=AdmCB(act="pru", p=0).pack())
    for n in (10, 50, 100, 500):
        b.button(text=f"{n} активаций", callback_data=AdmCB(act="pru", p=n).pack())
    b.adjust(1)
    await callback.answer()
    await callback.message.answer("Сколько раз можно использовать?", reply_markup=b.as_markup())


@router.callback_query(AdmCB.filter(F.act == "pru"))
async def promo_save(
    callback: CallbackQuery,
    callback_data: AdmCB,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
) -> None:
    data = await state.get_data()
    await state.clear()
    code = str(data.get("code") or "")
    amount = rub_to_kopecks(int(data.get("amount") or 0))
    session.add(PromoCode(code=code, amount_kopecks=amount, max_uses=callback_data.p, is_active=True))
    await write_audit(session, actor_id=db_user.id, action="promo.create", target=code)
    await callback.answer("Промокод создан")
    await callback.message.answer(f"Код {code} готов.", reply_markup=admin_root_kb())


@router.callback_query(AdmCB.filter(F.act == "tix"))
async def tix(callback: CallbackQuery, bot: Bot, session: AsyncSession, db_user: User) -> None:
    if await _deny(callback, db_user):
        return
    items = list(
        (
            await session.execute(
                select(Ticket).where(Ticket.status != TicketStatus.CLOSED).order_by(Ticket.updated_at.desc()).limit(15)
            )
        ).scalars().all()
    )
    rows = [[str(tick.id), tick.status.value] for tick in items]
    b = InlineKeyboardBuilder()
    for ticket in items:
        b.button(text=f"Ответить #{ticket.id}", callback_data=AdmCB(act="tix_r", id=ticket.id).pack())
        b.button(text=f"Закрыть #{ticket.id}", callback_data=AdmCB(act="tix_c", id=ticket.id).pack())
    b.adjust(2)
    await show_screen(
        bot=bot,
        user=db_user,
        event=callback,
        html=join(h1("Обращения"), table(["№", "Статус"], rows) if rows else p("Открытых нет")),
        reply_markup=with_home(b),
    )


@router.callback_query(AdmCB.filter(F.act == "tix_c"))
async def tix_c(callback: CallbackQuery, callback_data: AdmCB, session: AsyncSession, db_user: User, bot: Bot) -> None:
    ticket = await session.get(Ticket, callback_data.id)
    if ticket:
        ticket.status = TicketStatus.CLOSED
    await callback.answer("Закрыли")
    await tix(callback, bot, session, db_user)


@router.callback_query(AdmCB.filter(F.act == "tix_r"))
async def tix_r(callback: CallbackQuery, callback_data: AdmCB, state: FSMContext) -> None:
    await state.set_state(AdminStates.ticket_reply)
    await state.update_data(tid=callback_data.id)
    await callback.answer()
    await callback.message.answer("Напишите ответ покупателю:", reply_markup=cancel_kb())


@router.message(StateFilter(AdminStates.ticket_reply), NotMenu(), F.text)
async def tix_reply(message: Message, state: FSMContext, session: AsyncSession, bot: Bot, db_user: User) -> None:
    data = await state.get_data()
    await state.clear()
    ticket = await session.get(Ticket, int(data["tid"]))
    if ticket is None:
        return
    await add_ticket_message(session, ticket=ticket, from_staff=True, text=message.text)
    user = await session.get(User, ticket.user_id)
    if user:
        try:
            await bot.send_message(user.tg_id, f"Поддержка:\n{message.text}")
        except Exception:
            pass
    await message.answer("Отправили.", reply_markup=admin_root_kb())


@router.callback_query(AdmCB.filter(F.act == "banr"))
async def banner_menu(callback: CallbackQuery, db_user: User) -> None:
    if not has_admin_access(db_user):
        return
    b = InlineKeyboardBuilder()
    b.button(text="Загрузить своё фото", callback_data=AdmCB(act="banu").pack())
    b.button(text="Снова шаблон с названием", callback_data=AdmCB(act="bang").pack())
    b.button(text="Отмена", callback_data=AdmCB(act="x").pack())
    b.adjust(1)
    await callback.answer()
    await callback.message.answer(
        "Обложка на /start. Шаблон рисуется сам: название магазина, полоса, сетка. Либо своё фото из Canva.",
        reply_markup=b.as_markup(),
    )


@router.callback_query(AdmCB.filter(F.act == "banu"))
async def banner_ask(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    if not has_admin_access(db_user):
        return
    await state.set_state(AdminStates.shop_banner)
    await callback.answer()
    await callback.message.answer("Пришлите фото 16:9, без нейрокаши — лучше простой макет.", reply_markup=cancel_kb())


@router.message(StateFilter(AdminStates.shop_banner), F.photo)
async def banner_set(message: Message, state: FSMContext, shop: ShopSettings) -> None:
    await state.clear()
    extra = dict(shop.extra or {})
    extra["banner_key"] = "custom"
    shop.extra = extra
    shop.banner_file_id = message.photo[-1].file_id
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(shop, "extra")
    await message.answer("Баннер сохранён.", reply_markup=admin_root_kb())


@router.callback_query(AdmCB.filter(F.act == "bang"))
async def banner_gen(callback: CallbackQuery, shop: ShopSettings, bot: Bot, db_user: User) -> None:
    extra = dict(shop.extra or {})
    extra.pop("banner_key", None)
    shop.extra = extra
    shop.banner_file_id = None
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(shop, "extra")
    await callback.answer("Шаблон включён")
    await _home(callback, bot, db_user)


@router.callback_query(AdmCB.filter(F.act == "txt"))
async def texts_menu(callback: CallbackQuery, db_user: User) -> None:
    if not has_admin_access(db_user):
        return
    b = InlineKeyboardBuilder()
    for i, (_field, label) in enumerate(TEXT_FIELDS):
        b.button(text=label, callback_data=AdmCB(act="txf", p=i).pack())
    b.adjust(2)
    b.button(text="Отмена", callback_data=AdmCB(act="x").pack())
    await callback.answer()
    await callback.message.answer("Что меняем?", reply_markup=b.as_markup())


@router.callback_query(AdmCB.filter(F.act == "txf"))
async def texts_pick(callback: CallbackQuery, callback_data: AdmCB, state: FSMContext) -> None:
    idx = callback_data.p
    if idx < 0 or idx >= len(TEXT_FIELDS):
        await callback.answer()
        return
    field, label = TEXT_FIELDS[idx]
    await state.set_state(AdminStates.texts)
    await state.update_data(field=field)
    await callback.answer()
    await callback.message.answer(f"Пришлите новый текст для: {label}", reply_markup=cancel_kb())


@router.message(StateFilter(AdminStates.texts), NotMenu(), F.text)
async def texts_set(message: Message, state: FSMContext, shop: ShopSettings) -> None:
    data = await state.get_data()
    await state.clear()
    field = data.get("field")
    allowed = {f for f, _ in TEXT_FIELDS}
    if field not in allowed:
        await message.answer("Не то поле")
        return
    setattr(shop, field, (message.text or "")[:8000])
    await message.answer("Текст сохранён.", reply_markup=admin_root_kb())


@router.callback_query(AdmCB.filter(F.act == "set"))
async def settings_menu(callback: CallbackQuery, bot: Bot, db_user: User, shop: ShopSettings) -> None:
    if not has_admin_access(db_user):
        return
    open_now = not shop.maintenance
    b = InlineKeyboardBuilder()
    b.button(
        text="Закрыть на техработы" if open_now else "Открыть магазин",
        callback_data=AdmCB(act="mnt").pack(),
    )
    await show_screen(
        bot=bot,
        user=db_user,
        event=callback,
        html=join(h1("Режим"), p("Сейчас магазин " + ("открыт" if open_now else "на техработах") + ".")),
        reply_markup=with_home(b),
    )


@router.callback_query(AdmCB.filter(F.act == "mnt"))
async def mnt(callback: CallbackQuery, shop: ShopSettings, db_user: User, bot: Bot) -> None:
    shop.maintenance = not shop.maintenance
    await callback.answer("Закрыли" if shop.maintenance else "Открыли")
    await settings_menu(callback, bot, db_user, shop)
