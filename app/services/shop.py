from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    FulfillmentMode,
    Order,
    OrderStatus,
    Product,
    ReferralPayout,
    ReferralSource,
    StockItem,
    User,
)
from app.security.money import percent_of
from app.services.settings import get_settings


class ShopError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass
class PurchaseResult:
    order: Order
    product: Product
    stock_payload: str | None


async def purchase(session: AsyncSession, *, user_id: int, product_id: int) -> PurchaseResult:
    user = await session.get(User, user_id, with_for_update=True)
    if user is None or user.is_banned:
        raise ShopError("banned")

    product = (
        await session.execute(
            select(Product)
            .options(selectinload(Product.parts))
            .where(Product.id == product_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if product is None or not product.is_active:
        raise ShopError("inactive")
    if product.price_kopecks <= 0:
        raise ShopError("inactive")

    stock_payload: str | None = None
    stock_item: StockItem | None = None
    if product.use_stock:
        stock_item = (
            await session.execute(
                select(StockItem)
                .where(StockItem.product_id == product.id, StockItem.is_sold.is_(False))
                .order_by(StockItem.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
        ).scalar_one_or_none()
        if stock_item is None:
            raise ShopError("no_stock")
        stock_payload = stock_item.payload

    if user.balance_kopecks < product.price_kopecks:
        raise ShopError("no_funds")

    user.balance_kopecks -= product.price_kopecks
    status = (
        OrderStatus.PENDING_MANUAL
        if product.fulfillment == FulfillmentMode.MANUAL
        else OrderStatus.DELIVERED
    )
    order = Order(
        user_id=user.id,
        product_id=product.id,
        price_kopecks=product.price_kopecks,
        status=status,
        stock_payload=stock_payload,
    )
    session.add(order)
    await session.flush()

    if stock_item is not None:
        stock_item.is_sold = True
        stock_item.order_id = order.id

    await _referral_on_purchase(session, buyer=user, order=order)
    await session.flush()
    return PurchaseResult(order=order, product=product, stock_payload=stock_payload)


async def _referral_on_purchase(session: AsyncSession, *, buyer: User, order: Order) -> None:
    if not buyer.referrer_id:
        return
    shop = await get_settings(session)
    amount = percent_of(order.price_kopecks, shop.referral_purchase_percent)
    if amount <= 0:
        return
    referrer = await session.get(User, buyer.referrer_id, with_for_update=True)
    if referrer is None or referrer.is_banned:
        return
    referrer.balance_kopecks += amount
    session.add(
        ReferralPayout(
            beneficiary_id=referrer.id,
            from_user_id=buyer.id,
            source=ReferralSource.PURCHASE,
            amount_kopecks=amount,
            order_id=order.id,
        )
    )


async def credit_balance(
    session: AsyncSession,
    *,
    user_id: int,
    amount_kopecks: int,
    source: str,
) -> User:
    if amount_kopecks <= 0:
        raise ShopError("bad_amount")
    user = await session.get(User, user_id, with_for_update=True)
    if user is None or user.is_banned:
        raise ShopError("banned")
    user.balance_kopecks += amount_kopecks
    if source == "deposit" and user.referrer_id:
        shop = await get_settings(session)
        bonus = percent_of(amount_kopecks, shop.referral_deposit_percent)
        if bonus > 0:
            referrer = await session.get(User, user.referrer_id, with_for_update=True)
            if referrer and not referrer.is_banned:
                referrer.balance_kopecks += bonus
                session.add(
                    ReferralPayout(
                        beneficiary_id=referrer.id,
                        from_user_id=user.id,
                        source=ReferralSource.DEPOSIT,
                        amount_kopecks=bonus,
                    )
                )
    await session.flush()
    return user


async def refund_order(session: AsyncSession, order_id: int) -> Order:
    order = await session.get(Order, order_id, with_for_update=True)
    if order is None or order.status == OrderStatus.REFUNDED:
        raise ShopError("inactive")
    user = await session.get(User, order.user_id, with_for_update=True)
    if user is None:
        raise ShopError("inactive")
    user.balance_kopecks += order.price_kopecks
    order.status = OrderStatus.REFUNDED
    await session.flush()
    return order


async def count_orders(session: AsyncSession, user_id: int) -> int:
    result = await session.execute(select(func.count(Order.id)).where(Order.user_id == user_id))
    return int(result.scalar_one())
