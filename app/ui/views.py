from __future__ import annotations

from app.i18n import t
from app.models import FulfillmentMode, Product, ShopSettings, User
from app.security.money import format_rub
from app.ui.rich import details, e, h1, join, p, raw_p, table


def loc(obj, field: str, lang: str) -> str:
    ru = getattr(obj, f"{field}_ru")
    en = getattr(obj, f"{field}_en")
    return en if lang == "en" and en else ru


def shop_heading(shop: ShopSettings, lang: str, bot_title: str) -> str:
    title = loc(shop, "shop_title", lang).strip()
    if not title or title.lower() == "shop":
        return bot_title or title or "Магазин"
    return title


def home_caption(user: User, shop: ShopSettings, bot_title: str = "") -> str:
    lang = user.language
    title = shop_heading(shop, lang, bot_title)
    welcome = loc(shop, "welcome", lang)
    return (
        f"<b>{e(title)}</b>\n"
        f"{e(welcome)}\n\n"
        f"{e(t(lang, 'profile.bal'))}: <b>{e(format_rub(user.balance_kopecks, lang))}</b>\n"
        f"{e(t(lang, 'trust.instant'))}"
    )


def home_html(user: User, shop: ShopSettings, bot_title: str = "") -> str:
    lang = user.language
    return join(
        h1(shop_heading(shop, lang, bot_title)),
        p(loc(shop, "welcome", lang)),
        raw_p(f"{e(t(lang, 'profile.bal'))}: <b>{e(format_rub(user.balance_kopecks, lang))}</b>"),
        p(t(lang, "trust.instant")),
    )


def catalog_html(lang: str, featured: list[list[str]], empty: bool = False) -> str:
    parts = [h1(t(lang, "catalog.title")), p(t(lang, "catalog.empty" if empty else "catalog.pick"))]
    if featured:
        parts.append(p(t(lang, "catalog.hits")))
        parts.append(table([t(lang, "catalog.products"), t(lang, "product.price")], featured))
    return join(*parts)


def cap(*parts: str) -> str:
    return "\n".join(p for p in parts if p)[:1024]


def catalog_caption(lang: str, empty: bool = False) -> str:
    return cap(
        f"<b>{e(t(lang, 'catalog.title'))}</b>",
        e(t(lang, "catalog.empty" if empty else "catalog.pick")),
    )


def products_caption(lang: str, title: str, n: int) -> str:
    return f"<b>{e(title)}</b>\n{e(t(lang, 'catalog.in_cat', n=n))}"


def products_html(lang: str, title: str, rows: list[list[str]]) -> str:
    return join(h1(title), table([t(lang, "catalog.products"), t(lang, "product.price")], rows))


def product_caption(
    lang: str,
    product: Product,
    stock: int | None,
    sold: int,
) -> str:
    title = loc(product, "title", lang)
    desc = loc(product, "description", lang)
    mode = t(lang, "product.manual" if product.fulfillment == FulfillmentMode.MANUAL else "product.auto")
    if product.use_stock:
        stock_s = t(lang, "stock.n", n=stock or 0)
    else:
        stock_s = t(lang, "unlimited")
    lines = [
        f"<b>{e(title)}</b>",
        f"{e(t(lang, 'product.price'))}: <b>{e(format_rub(product.price_kopecks, lang))}</b>",
        e(mode),
        f"{e(t(lang, 'product.stock'))}: {e(stock_s)}",
        f"{e(t(lang, 'product.sold'))}: {sold}",
    ]
    if desc:
        lines.append("")
        lines.append(e(desc[:400]))
    return "\n".join(lines)[:1024]


def product_html(
    lang: str,
    product: Product,
    stock: int | None,
    shop: ShopSettings,
    sold: int = 0,
) -> str:
    title = loc(product, "title", lang)
    desc = loc(product, "description", lang)
    mode = t(lang, "product.manual" if product.fulfillment == FulfillmentMode.MANUAL else "product.auto")
    stock_s = t(lang, "stock.n", n=stock or 0) if product.use_stock else t(lang, "unlimited")
    body = join(
        h1(title),
        raw_p(f"{e(t(lang, 'product.price'))}: <b>{e(format_rub(product.price_kopecks, lang))}</b>"),
        p(mode),
        p(f"{t(lang, 'product.stock')}: {stock_s}"),
        p(f"{t(lang, 'product.sold')}: {sold}"),
    )
    if desc:
        body += details(t(lang, "product.desc"), f"<p>{e(desc)}</p>")
    return body


def receipt_html(lang: str, order_id: int, title: str, amount: str, balance: str, manual: bool) -> str:
    note = t(lang, "buy.manual") if manual else t(lang, "buy.ok")
    return join(
        h1(t(lang, "receipt.title")),
        table(
            ["", ""],
            [
                [t(lang, "receipt.order"), f"№ {order_id}"],
                [t(lang, "receipt.item"), title],
                [t(lang, "receipt.sum"), amount],
                [t(lang, "profile.bal"), balance],
            ],
        ),
        p(note),
        p(t(lang, "receipt.help")),
    )


def profile_html(lang: str, user: User, orders: int, refs: int) -> str:
    return join(
        h1(t(lang, "profile.title")),
        table(
            ["", ""],
            [
                [t(lang, "profile.id"), str(user.tg_id)],
                [t(lang, "profile.bal"), format_rub(user.balance_kopecks, lang)],
                [t(lang, "profile.orders"), str(orders)],
                [t(lang, "profile.refs"), str(refs)],
            ],
        ),
        p(t(lang, "trust.support")),
    )


def profile_caption(lang: str, user: User, orders: int, refs: int) -> str:
    return cap(
        f"<b>{e(t(lang, 'profile.title'))}</b>",
        f"{e(t(lang, 'profile.bal'))}: <b>{e(format_rub(user.balance_kopecks, lang))}</b>",
        f"{e(t(lang, 'profile.orders'))}: {orders}",
        f"{e(t(lang, 'profile.refs'))}: {refs}",
        e(t(lang, "trust.support")),
    )


def balance_html(lang: str, user: User, shop: ShopSettings) -> str:
    return join(
        h1(t(lang, "balance.title")),
        raw_p(f"{e(t(lang, 'balance.current'))}: <b>{e(format_rub(user.balance_kopecks, lang))}</b>"),
        p(t(lang, "balance.stars_rate", rate=format_rub(shop.stars_kopecks_per_star, lang))),
        p(t(lang, "balance.choose")),
    )


def balance_caption(lang: str, user: User, shop: ShopSettings) -> str:
    return cap(
        f"<b>{e(t(lang, 'balance.title'))}</b>",
        f"{e(t(lang, 'balance.current'))}: <b>{e(format_rub(user.balance_kopecks, lang))}</b>",
        e(t(lang, "balance.stars_rate", rate=format_rub(shop.stars_kopecks_per_star, lang))),
        e(t(lang, "balance.choose")),
    )


def referral_html(lang: str, link: str, shop: ShopSettings, invited: int, earned: int) -> str:
    return join(
        h1(t(lang, "ref.title")),
        p(t(lang, "ref.how")),
        p(t(lang, "ref.link")),
        raw_p(f"<code>{e(link)}</code>"),
        table(
            ["", ""],
            [
                [t(lang, "ref.deposit"), f"{shop.referral_deposit_percent}%"],
                [t(lang, "ref.purchase"), f"{shop.referral_purchase_percent}%"],
                [t(lang, "ref.count"), str(invited)],
                [t(lang, "ref.earned"), format_rub(earned, lang)],
            ],
        ),
    )


def referral_caption(lang: str, link: str, shop: ShopSettings, invited: int, earned: int) -> str:
    return cap(
        f"<b>{e(t(lang, 'ref.title'))}</b>",
        e(t(lang, "ref.how")),
        f"<code>{e(link)}</code>",
        f"{e(t(lang, 'ref.deposit'))}: {shop.referral_deposit_percent}% · {e(t(lang, 'ref.purchase'))}: {shop.referral_purchase_percent}%",
        f"{e(t(lang, 'ref.count'))}: {invited} · {e(t(lang, 'ref.earned'))}: {e(format_rub(earned, lang))}",
    )


def sub_html(lang: str) -> str:
    return join(h1(t(lang, "sub.title")), p(t(lang, "sub.body")))


def sub_caption(lang: str) -> str:
    return cap(f"<b>{e(t(lang, 'sub.title'))}</b>", e(t(lang, "sub.body")))


def settings_html(lang: str) -> str:
    return join(h1(t(lang, "settings.title")), p(t(lang, "settings.body")))


def settings_caption(lang: str) -> str:
    return cap(f"<b>{e(t(lang, 'settings.title'))}</b>", e(t(lang, "settings.body")))


def support_html(lang: str, rules: str = "") -> str:
    parts = [h1(t(lang, "support.title")), p(t(lang, "support.body")), p(t(lang, "trust.support"))]
    if rules.strip():
        parts.append(details(t(lang, "btn.rules"), f"<p>{e(rules[:800])}</p>"))
    else:
        parts.append(p(t(lang, "support.rules_default")))
    return join(*parts)


def support_caption(lang: str, rules: str = "") -> str:
    body = rules.strip()[:400] if rules.strip() else t(lang, "support.rules_default")
    return cap(
        f"<b>{e(t(lang, 'support.title'))}</b>",
        e(t(lang, "support.body")),
        e(t(lang, "trust.support")),
        e(body),
    )


def receipt_caption(lang: str, order_id: int, title: str, amount: str, balance: str, manual: bool) -> str:
    note = t(lang, "buy.manual") if manual else t(lang, "buy.ok")
    return cap(
        f"<b>{e(t(lang, 'receipt.title'))}</b>",
        f"{e(t(lang, 'receipt.order'))}: № {order_id}",
        f"{e(t(lang, 'receipt.item'))}: {e(title)}",
        f"{e(t(lang, 'receipt.sum'))}: <b>{e(amount)}</b>",
        f"{e(t(lang, 'profile.bal'))}: {e(balance)}",
        e(note),
        e(t(lang, "receipt.help")),
    )


def orders_caption(lang: str, rows: list[list[str]]) -> str:
    lines = [f"{r[0]} · {r[1]} · {r[2]}" for r in rows[:8]]
    return cap(f"<b>{e(t(lang, 'orders.title'))}</b>", *[e(x) for x in lines])


def text_caption(title: str, body: str) -> str:
    return cap(f"<b>{e(title)}</b>", e(body[:700]))
