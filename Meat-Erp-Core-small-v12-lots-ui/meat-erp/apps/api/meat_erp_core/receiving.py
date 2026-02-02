from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, condecimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from meat_erp_core.db import get_session
from meat_erp_core.models import Lot, LotEvent, InventoryMovement, Item, Supplier, Location
from meat_erp_core.lot_codes import next_lot_code

router = APIRouter(prefix="/receiving", tags=["receiving"])

Kg = condecimal(gt=0, max_digits=12, decimal_places=3)

class ReceivingRequest(BaseModel):
    item_id: int
    supplier_id: int
    quantity_kg: Kg
    to_location_id: int
    notes: str | None = Field(default=None, max_length=500)
    received_at: datetime | None = None

ReceivingCreateLotRequest = ReceivingRequest


async def create_lot_txn(session: AsyncSession, req: ReceivingRequest, performed_by: int = 1):
    """Create receiving lot + movement + lot_event without committing (caller controls transaction)."""
    item = (await session.execute(select(Item).where(Item.id == req.item_id))).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=400, detail="Invalid item_id")

    supplier = (await session.execute(select(Supplier).where(Supplier.id == req.supplier_id))).scalar_one_or_none()
    if not supplier:
        raise HTTPException(status_code=400, detail="Invalid supplier_id")

    loc = (await session.execute(select(Location).where(Location.id == req.to_location_id))).scalar_one_or_none()
    if not loc:
        raise HTTPException(status_code=400, detail="Invalid to_location_id")

    received_at = req.received_at or datetime.now(timezone.utc)

    lot_code = await next_lot_code(session, "REC", received_at)

    lot = Lot(
        lot_code=lot_code,
        item_id=req.item_id,
        supplier_id=req.supplier_id,
        received_at=received_at,
        state="received",
        current_location_id=req.to_location_id,
    )
    session.add(lot)
    await session.flush()

    mv = InventoryMovement(
        lot_id=lot.id,
        from_location_id=None,
        to_location_id=req.to_location_id,
        quantity_kg=req.quantity_kg,
        moved_at=received_at,
        move_type="receiving",
    )
    session.add(mv)
    await session.flush()

    ev = LotEvent(
        lot_id=lot.id,
        event_type="received",
        reason=req.notes,  # notes stored in reason column
        performed_by=performed_by,
        performed_at=received_at,
    )
    session.add(ev)
    await session.flush()

    return {
        "lot_id": lot.id,
        "lot_code": lot.lot_code,
        "movement_id": mv.id,
        "lot_event_id": ev.id,
    }

@router.post("/lots")
async def create_lot(req: ReceivingRequest, session: AsyncSession = Depends(get_session)):
    # TODO: replace performed_by with current_user.id from JWT
    performed_by = 1
    resp = await create_lot_txn(session, req, performed_by=performed_by)
    await session.commit()
    return resp
