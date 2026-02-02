from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from meat_erp_core.db import get_session
from meat_erp_core.models import Lot, LotEvent
from meat_erp_core.traceability import forward_trace

router = APIRouter(prefix="/recall", tags=["recall-actions"])

class QuarantineForwardRequest(BaseModel):
    performed_by: int
    reason: str = Field(min_length=2, max_length=500)
    performed_at: datetime | None = None

class QuarantineForwardResponse(BaseModel):
    root_lot_id: int
    forward_lot_ids: list[int]
    quarantined_count: int
    already_quarantined_count: int
    lot_event_ids: list[int]

@router.post("/{lot_id}/quarantine-forward", response_model=QuarantineForwardResponse)
async def quarantine_forward(lot_id: int, req: QuarantineForwardRequest, session: AsyncSession = Depends(get_session)):
    root = (await session.execute(select(Lot).where(Lot.id == lot_id))).scalar_one_or_none()
    if not root:
        raise HTTPException(status_code=404, detail="Lot not found")

    performed_at = req.performed_at or datetime.now(timezone.utc)

    forward_ids = await forward_trace(session, lot_id)
    if not forward_ids:
        return QuarantineForwardResponse(
            root_lot_id=lot_id,
            forward_lot_ids=[],
            quarantined_count=0,
            already_quarantined_count=0,
            lot_event_ids=[],
        )

    lots = (await session.execute(select(Lot).where(Lot.id.in_(forward_ids)))).scalars().all()
    lot_map = {l.id: l for l in lots}

    lot_event_ids: list[int] = []
    quarantined = 0
    already = 0

    for lid in forward_ids:
        lot = lot_map.get(lid)
        if not lot:
            continue

        if lot.state == "quarantined":
            already += 1
            continue

        ev = LotEvent(
            lot_id=lid,
            event_type="quarantined_bulk",
            reason=req.reason,
            performed_by=req.performed_by,
            performed_at=performed_at,
        )
        session.add(ev)
        await session.flush()
        lot_event_ids.append(ev.id)

        await session.execute(
            update(Lot)
            .where(Lot.id == lid)
            .values(state="quarantined")
        )
        quarantined += 1

    await session.commit()

    return QuarantineForwardResponse(
        root_lot_id=lot_id,
        forward_lot_ids=forward_ids,
        quarantined_count=quarantined,
        already_quarantined_count=already,
        lot_event_ids=lot_event_ids,
    )
