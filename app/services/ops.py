from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Ticket, TicketMessage, TicketStatus, User


async def write_audit(
    session: AsyncSession,
    *,
    actor_id: int,
    action: str,
    target: str | None = None,
    details: dict | None = None,
) -> None:
    session.add(
        AuditLog(
            actor_id=actor_id,
            action=action[:64],
            target=(target or "")[:128],
            details=details or {},
        )
    )


async def open_or_get_ticket(session: AsyncSession, user_id: int) -> Ticket:
    result = await session.execute(
        select(Ticket)
        .where(Ticket.user_id == user_id, Ticket.status != TicketStatus.CLOSED)
        .order_by(Ticket.id.desc())
        .limit(1)
    )
    ticket = result.scalar_one_or_none()
    if ticket is None:
        ticket = Ticket(user_id=user_id, status=TicketStatus.OPEN)
        session.add(ticket)
        await session.flush()
    return ticket


async def add_ticket_message(
    session: AsyncSession,
    *,
    ticket: Ticket,
    from_staff: bool,
    text: str | None,
    file_id: str | None = None,
    kind: str = "text",
) -> TicketMessage:
    ticket.updated_at = datetime.now(timezone.utc)
    ticket.status = TicketStatus.WAITING_USER if from_staff else TicketStatus.OPEN
    msg = TicketMessage(
        ticket_id=ticket.id,
        from_staff=from_staff,
        text=text,
        file_id=file_id,
        kind=kind,
    )
    session.add(msg)
    await session.flush()
    return msg


async def staff_ids(session: AsyncSession) -> list[int]:
    from app.models import Role

    result = await session.execute(
        select(User.tg_id).where(User.role.in_([Role.SUPPORT, Role.ADMIN, Role.OWNER]), User.is_banned.is_(False))
    )
    return [int(x) for x in result.scalars().all()]
