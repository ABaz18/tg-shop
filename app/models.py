from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Role(str, enum.Enum):
    USER = "user"
    SUPPORT = "support"
    ADMIN = "admin"
    OWNER = "owner"


class OrderStatus(str, enum.Enum):
    PAID = "paid"
    DELIVERED = "delivered"
    PENDING_MANUAL = "pending_manual"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    FAILED = "failed"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class PaymentProvider(str, enum.Enum):
    STARS = "stars"
    CRYPTOBOT = "cryptobot"
    FIAT = "fiat"


class TicketStatus(str, enum.Enum):
    OPEN = "open"
    WAITING_USER = "waiting_user"
    CLOSED = "closed"


class DeliveryKind(str, enum.Enum):
    TEXT = "text"
    PHOTO = "photo"
    DOCUMENT = "document"
    VIDEO = "video"
    ANIMATION = "animation"
    AUDIO = "audio"


class FulfillmentMode(str, enum.Enum):
    AUTO = "auto"
    MANUAL = "manual"


class ReferralSource(str, enum.Enum):
    DEPOSIT = "deposit"
    PURCHASE = "purchase"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))
    language: Mapped[str] = mapped_column(String(8), default="ru", server_default="ru")
    balance_kopecks: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    role: Mapped[Role] = mapped_column(Enum(Role, name="role"), default=Role.USER)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    ban_reason: Mapped[str | None] = mapped_column(Text)
    admin_note: Mapped[str | None] = mapped_column(Text)
    referrer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    menu_message_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    referrer: Mapped[User | None] = relationship(remote_side="User.id")

    __table_args__ = (
        Index("ix_users_referrer_id", "referrer_id"),
        Index("ix_users_role", "role"),
    )


class ShopSettings(Base):
    __tablename__ = "shop_settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    maintenance: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    stars_kopecks_per_star: Mapped[int] = mapped_column(Integer, default=200, server_default="200")
    min_topup_kopecks: Mapped[int] = mapped_column(Integer, default=5000, server_default="5000")
    max_topup_kopecks: Mapped[int] = mapped_column(Integer, default=100_000_00, server_default="10000000")
    referral_deposit_percent: Mapped[int] = mapped_column(Integer, default=10, server_default="10")
    referral_purchase_percent: Mapped[int] = mapped_column(Integer, default=5, server_default="5")
    welcome_bonus_kopecks: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    subscription_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    shop_title_ru: Mapped[str] = mapped_column(String(120), default="Shop")
    shop_title_en: Mapped[str] = mapped_column(String(120), default="Shop")
    welcome_ru: Mapped[str] = mapped_column(
        Text,
        default="Каталог — товары. Пополнить — деньги на счёт. После оплаты товар приходит в этот чат.",
    )
    welcome_en: Mapped[str] = mapped_column(
        Text,
        default="Catalog is the shop. Top up your balance, then buy. Items arrive in this chat.",
    )
    rules_ru: Mapped[str] = mapped_column(
        Text,
        default="Оплата списывается с баланса. Автотовар приходит сразу. Если что-то не пришло — напишите в Помощь, разберёмся. Возврат — если товар не выдан.",
    )
    rules_en: Mapped[str] = mapped_column(
        Text,
        default="We charge your balance. Instant items arrive at once. If nothing arrives, write to Help. Refund if we fail to deliver.",
    )
    faq_ru: Mapped[str] = mapped_column(
        Text,
        default="Как купить: пополните счёт, откройте каталог, нажмите Купить. Где товар: в этом чате, сразу после оплаты. Поддержка: кнопка Помощь.",
    )
    faq_en: Mapped[str] = mapped_column(
        Text,
        default="How to buy: top up, open Catalog, tap Buy. Where is the item: this chat, right after payment. Support: Help button.",
    )
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    banner_file_id: Mapped[str | None] = mapped_column(String(256))


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    title_ru: Mapped[str] = mapped_column(String(120))
    title_en: Mapped[str] = mapped_column(String(120))
    sort: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    cover_file_id: Mapped[str | None] = mapped_column(String(256))

    products: Mapped[list[Product]] = relationship(back_populates="category")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="RESTRICT"))
    title_ru: Mapped[str] = mapped_column(String(180))
    title_en: Mapped[str] = mapped_column(String(180))
    description_ru: Mapped[str] = mapped_column(Text, default="")
    description_en: Mapped[str] = mapped_column(Text, default="")
    price_kopecks: Mapped[int] = mapped_column(BigInteger)
    fulfillment: Mapped[FulfillmentMode] = mapped_column(
        Enum(FulfillmentMode, name="fulfillment_mode"),
        default=FulfillmentMode.AUTO,
    )
    use_stock: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    stock_alert: Mapped[int] = mapped_column(Integer, default=5, server_default="5")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    sort: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    cover_file_id: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    category: Mapped[Category] = relationship(back_populates="products")
    parts: Mapped[list[ProductPart]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductPart.sort",
    )


class ProductPart(Base):
    __tablename__ = "product_parts"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    sort: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    kind: Mapped[DeliveryKind] = mapped_column(Enum(DeliveryKind, name="delivery_kind"))
    text: Mapped[str | None] = mapped_column(Text)
    file_id: Mapped[str | None] = mapped_column(String(256))
    caption: Mapped[str | None] = mapped_column(Text)

    product: Mapped[Product] = relationship(back_populates="parts")


class StockItem(Base):
    __tablename__ = "stock_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    payload: Mapped[str] = mapped_column(Text)
    is_sold: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index(
            "ix_stock_available",
            "product_id",
            postgresql_where=text("is_sold = false"),
        ),
    )


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    price_kopecks: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus, name="order_status"))
    stock_payload: Mapped[str | None] = mapped_column(Text)
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    provider: Mapped[PaymentProvider] = mapped_column(Enum(PaymentProvider, name="payment_provider"))
    status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus, name="payment_status"))
    amount_kopecks: Mapped[int] = mapped_column(BigInteger)
    stars_amount: Mapped[int | None] = mapped_column(Integer)
    invoice_nonce: Mapped[str] = mapped_column(String(64), unique=True)
    telegram_charge_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReferralPayout(Base):
    __tablename__ = "referral_payouts"

    id: Mapped[int] = mapped_column(primary_key=True)
    beneficiary_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    from_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    source: Mapped[ReferralSource] = mapped_column(Enum(ReferralSource, name="referral_source"))
    amount_kopecks: Mapped[int] = mapped_column(BigInteger)
    payment_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id"))
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RequiredChannel(Base):
    __tablename__ = "required_channels"

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    title: Mapped[str] = mapped_column(String(180))
    invite_url: Mapped[str] = mapped_column(String(512))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class PromoCode(Base):
    __tablename__ = "promo_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    amount_kopecks: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    percent: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    max_uses: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    used_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class PromoRedemption(Base):
    __tablename__ = "promo_redemptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    promo_id: Mapped[int] = mapped_column(ForeignKey("promo_codes.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("promo_id", "user_id", name="uq_promo_user"),)


class Favorite(Base):
    __tablename__ = "favorites"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))

    __table_args__ = (UniqueConstraint("user_id", "product_id", name="uq_fav"),)


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[TicketStatus] = mapped_column(
        Enum(TicketStatus, name="ticket_status"),
        default=TicketStatus.OPEN,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TicketMessage(Base):
    __tablename__ = "ticket_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), index=True)
    from_staff: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    text: Mapped[str | None] = mapped_column(Text)
    file_id: Mapped[str | None] = mapped_column(String(256))
    kind: Mapped[str] = mapped_column(String(16), default="text", server_default="text")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Broadcast(Base):
    __tablename__ = "broadcasts"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    html: Mapped[str] = mapped_column(Text)
    segment: Mapped[str] = mapped_column(String(32), default="all")
    status: Mapped[str] = mapped_column(String(16), default="queued")
    sent: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    failed: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(64), index=True)
    target: Mapped[str | None] = mapped_column(String(128))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


def load_models() -> None:
    """Import side-effect so metadata is populated."""
    return None
