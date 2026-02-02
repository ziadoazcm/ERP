from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from meat_erp_core.db import get_session
from meat_erp_core.models import Lot
from meat_erp_core.traceability import backward_trace, forward_trace, affected_customers

router = APIRouter(prefix="/recall", tags=["recall"])

class RecallResponse(BaseModel):
    lot_id: int
    backward_lot_ids: list[int]
    forward_lot_ids: list[int]
    affected_customers: list[dict]

@router.get("/{lot_id}", response_model=RecallResponse)
async def recall(lot_id: int, session: AsyncSession = Depends(get_session)):
    lot = (await session.execute(select(Lot).where(Lot.id == lot_id))).scalar_one_or_none()
    if not lot:
        raise HTTPException(status_code=404, detail="Lot not found")

    backward = await backward_trace(session, lot_id)
    forward = await forward_trace(session, lot_id)

    customer_lot_ids = list(set(forward + [lot_id]))
    customers = await affected_customers(session, customer_lot_ids)

    return RecallResponse(
        lot_id=lot_id,
        backward_lot_ids=backward,
        forward_lot_ids=forward,
        affected_customers=customers,
    )
