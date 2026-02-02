from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from meat_erp_core.db import get_session
from meat_erp_core.models import Lot, LotEvent

router = APIRouter(prefix="/lots", tags=["lots"])

@router.get("/{lot_id}/events")
async def list_lot_events(lot_id: int, limit: int = 200, session: AsyncSession = Depends(get_session)):
    lot = (await session.execute(select(Lot).where(Lot.id == lot_id))).scalar_one_or_none()
    if not lot:
        raise HTTPException(status_code=404, detail="Lot not found")

    rows = (await session.execute(
        select(LotEvent)
        .where(LotEvent.lot_id == lot_id)
        .order_by(LotEvent.performed_at.desc(), LotEvent.id.desc())
        .limit(limit)
    )).scalars().all()

    return [{
        "id": r.id,
        "event_type": r.event_type,
        "reason": r.reason,
        "performed_by": r.performed_by,
        "performed_at": r.performed_at,
    } for r in rows]
