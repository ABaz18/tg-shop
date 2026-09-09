from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Payment, PaymentProvider, PaymentStatus
from app.security.payload import PayloadError
from app.services.shop import credit_balance


async def create_stars_invoice(
    session: AsyncSession,
    *,
    user_id: int,
    kopecks: int,
    stars: int,
    product_id: int | None = None,
) -> Payment:
    nonce = secrets.token_urlsafe(16)
    payment = Payment(
        user_id=user_id,
        provider=PaymentProvider.STARS,
        status=PaymentStatus.PENDING,
        amount_kopecks=kopecks,
        stars_amount=stars,
        invoice_nonce=nonce,
        product_id=product_id,
    )
    session.add(payment)
    await session.flush()
    return payment


async def get_pending_invoice(session: AsyncSession, nonce: str) -> Payment | None:
    result = await session.execute(select(Payment).where(Payment.invoice_nonce == nonce))
    return result.scalar_one_or_none()


async def complete_stars_payment(
    session: AsyncSession,
    *,
    user_id: int,
    nonce: str,
    telegram_charge_id: str,
    stars_paid: int,
) -> Payment:
    dup = await session.execute(select(Payment).where(Payment.telegram_charge_id == telegram_charge_id))
    if dup.scalar_one_or_none():
        raise PayloadError("duplicate charge")

    payment = (
        await session.execute(select(Payment).where(Payment.invoice_nonce == nonce).with_for_update())
    ).scalar_one_or_none()
    if payment is None or payment.status != PaymentStatus.PENDING:
        raise PayloadError("unknown invoice")
    if payment.user_id != user_id:
        raise PayloadError("payload mismatch")
    if int(payment.stars_amount or 0) != int(stars_paid):
        raise PayloadError("stars mismatch")

    payment.status = PaymentStatus.COMPLETED
    payment.telegram_charge_id = telegram_charge_id
    payment.completed_at = datetime.now(timezone.utc)
    await credit_balance(session, user_id=user_id, amount_kopecks=payment.amount_kopecks, source="deposit")
    await session.flush()
    return payment
