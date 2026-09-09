from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Category, Favorite, Order, OrderStatus, Product, StockItem


async def list_categories_with_counts(session: AsyncSession) -> list[tuple[Category, int]]:
    result = await session.execute(
        select(Category, func.count(Product.id))
        .outerjoin(
            Product,
            (Product.category_id == Category.id) & (Product.is_active.is_(True)),
        )
        .where(Category.is_active.is_(True))
        .group_by(Category.id)
        .order_by(Category.sort, Category.id)
    )
    return [(row[0], int(row[1])) for row in result.all()]


async def list_products(session: AsyncSession, category_id: int) -> list[Product]:
    result = await session.execute(
        select(Product)
        .where(Product.category_id == category_id, Product.is_active.is_(True))
        .order_by(Product.is_featured.desc(), Product.sort, Product.id)
    )
    return list(result.scalars().all())


async def list_featured(session: AsyncSession, limit: int = 4) -> list[Product]:
    result = await session.execute(
        select(Product)
        .where(Product.is_active.is_(True), Product.is_featured.is_(True))
        .order_by(Product.sort, Product.id)
        .limit(limit)
    )
    return list(result.scalars().all())


async def sold_count(session: AsyncSession, product_id: int) -> int:
    result = await session.execute(
        select(func.count(Order.id)).where(
            Order.product_id == product_id,
            Order.status.in_((OrderStatus.DELIVERED, OrderStatus.PAID, OrderStatus.PENDING_MANUAL)),
        )
    )
    return int(result.scalar_one())


async def get_product(session: AsyncSession, product_id: int, *, with_parts: bool = True) -> Product | None:
    if not with_parts:
        return await session.get(Product, product_id)
    result = await session.execute(
        select(Product)
        .options(selectinload(Product.parts), selectinload(Product.category))
        .where(Product.id == product_id)
    )
    return result.scalar_one_or_none()


async def stock_left(session: AsyncSession, product_id: int) -> int:
    result = await session.execute(
        select(func.count(StockItem.id)).where(
            StockItem.product_id == product_id,
            StockItem.is_sold.is_(False),
        )
    )
    return int(result.scalar_one())


async def is_favorite(session: AsyncSession, user_id: int, product_id: int) -> bool:
    result = await session.execute(
        select(Favorite.id).where(Favorite.user_id == user_id, Favorite.product_id == product_id)
    )
    return result.scalar_one_or_none() is not None


async def toggle_favorite(session: AsyncSession, user_id: int, product_id: int) -> bool:
    result = await session.execute(
        select(Favorite).where(Favorite.user_id == user_id, Favorite.product_id == product_id)
    )
    row = result.scalar_one_or_none()
    if row:
        await session.delete(row)
        return False
    session.add(Favorite(user_id=user_id, product_id=product_id))
    return True
