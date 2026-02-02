from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

async def next_lot_code(session: AsyncSession, prefix: str, at: datetime | None = None) -> str:
    if at is None:
        at = datetime.now(timezone.utc)
    d = at.date()

    await session.execute(
        text("""
        INSERT INTO lot_code_counters(code_date, prefix, last_seq)
        VALUES (:d, :p, 0)
        ON CONFLICT (code_date, prefix) DO NOTHING
        """),
        {"d": d, "p": prefix},
    )

    row = await session.execute(
        text("""
        SELECT id, last_seq
        FROM lot_code_counters
        WHERE code_date = :d AND prefix = :p
        FOR UPDATE
        """),
        {"d": d, "p": prefix},
    )
    r = row.first()
    last_seq = int(r[1])
    next_seq = last_seq + 1

    await session.execute(
        text("""
        UPDATE lot_code_counters
        SET last_seq = :next_seq
        WHERE code_date = :d AND prefix = :p
        """),
        {"next_seq": next_seq, "d": d, "p": prefix},
    )

    return f"{prefix}-{d.strftime('%Y%m%d')}-{next_seq:04d}"
