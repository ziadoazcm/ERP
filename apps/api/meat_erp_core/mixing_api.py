from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, condecimal
from typing import List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from meat_erp_core.db import get_session
from meat_erp_core.models import (
    Lot, LotEvent, InventoryMovement,
    ProcessProfile, ProductionOrder, ProductionInput, ProductionOutput,
    Location, Item
)
from meat_erp_core.availability import available_kg
from meat_erp_core.lot_codes import next_lot_code

router = APIRouter(prefix="/production", tags=["production"])

Kg = condecimal(gt=0, max_digits=12, decimal_places=3)
TOLERANCE = 0.001

class MixInput(BaseModel):
    lot_id: int
    quantity_kg: Kg

class MixRequest(BaseModel):
    process_profile_id: int
    inputs: List[MixInput] = Field(min_length=2)

    output_item_id: int
    output_location_id: int

    notes: str | None = Field(default=None, max_length=500)
    performed_at: datetime | None = None

class MixResponse(BaseModel):
    production_order_id: int
    output_lot_id: int
    output_lot_code: str
    input_movement_ids: List[int]
    output_movement_id: int
    lot_event_ids: List[int]

@router.post("/mix", response_model=MixResponse)
async def mix(req: MixRequest, session: AsyncSession = Depends(get_session)):
    performed_at = req.performed_at or datetime.now(timezone.utc)
    performed_by = 1  # TODO: current_user.id from JWT

    profile = (await session.execute(
        select(ProcessProfile).where(ProcessProfile.id == req.process_profile_id)
    )).scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=400, detail="Invalid process_profile_id")
    if not profile.allows_lot_mixing:
        raise HTTPException(status_code=400, detail="This process profile does not allow lot mixing")

    out_item = (await session.execute(select(Item).where(Item.id == req.output_item_id))).scalar_one_or_none()
    if not out_item:
        raise HTTPException(status_code=400, detail="Invalid output_item_id")

    out_loc = (await session.execute(select(Location).where(Location.id == req.output_location_id))).scalar_one_or_none()
    if not out_loc:
        raise HTTPException(status_code=400, detail="Invalid output_location_id")

    out_code = await next_lot_code(session, "MIX", performed_at)
    existing_out = (await session.execute(select(Lot).where(Lot.lot_code == out_code))).scalar_one_or_none()
    if existing_out:
        raise HTTPException(status_code=409, detail=f"output_lot_code already exists: {out_code}")

    by_lot: dict[int, float] = {}
    for i in req.inputs:
        by_lot[i.lot_id] = by_lot.get(i.lot_id, 0.0) + float(i.quantity_kg)

    lots = (await session.execute(select(Lot).where(Lot.id.in_(list(by_lot.keys()))))).scalars().all()
    lot_map = {l.id: l for l in lots}
    if len(lot_map) != len(by_lot):
        raise HTTPException(status_code=400, detail="One or more input lot_id invalid")

    for lot_id, qty in by_lot.items():
        lot = lot_map[lot_id]
        if lot.state == "quarantined":
            raise HTTPException(status_code=400, detail=f"Input lot {lot.lot_code} is quarantined")

        # Mixing is for sausages/burgers; enforce sale-safe inputs.
        if lot.state != "released":
            raise HTTPException(status_code=400, detail=f"Input lot {lot.lot_code} must be released")
        if lot.ready_at and performed_at < lot.ready_at:
            raise HTTPException(status_code=400, detail=f"Input lot {lot.lot_code} is not ready yet")

        avail = await available_kg(session, lot_id)
        if qty - avail > TOLERANCE:
            raise HTTPException(
                status_code=400,
                detail=f"Input lot {lot.lot_code}: insufficient available. requested={qty:.3f} available={avail:.3f}",
            )

    po = ProductionOrder(
        process_profile_id=req.process_profile_id,
        process_type="mix",
        is_rework=False,
        started_at=performed_at,
        completed_at=performed_at,
    )
    session.add(po)
    await session.flush()

    event_ids: List[int] = []
    input_movement_ids: List[int] = []

    for lot_id, qty in by_lot.items():
        session.add(ProductionInput(
            production_order_id=po.id,
            lot_id=lot_id,
            quantity_kg=qty,
        ))

        ev = LotEvent(
            lot_id=lot_id,
            event_type="mix_input",
            reason=req.notes,
            performed_by=performed_by,
            performed_at=performed_at,
        )
        session.add(ev)
        await session.flush()
        event_ids.append(ev.id)

        mv = InventoryMovement(
            lot_id=lot_id,
            from_location_id=getattr(lot_map[lot_id], "current_location_id", None),
            to_location_id=None,
            quantity_kg=qty,
            moved_at=performed_at,
            move_type="mix_input",
        )
        session.add(mv)
        await session.flush()
        input_movement_ids.append(mv.id)

    out_lot = Lot(
        lot_code=out_code,
        item_id=req.output_item_id,
        supplier_id=None,
        state="released",
        received_at=performed_at,
        ready_at=performed_at,
        released_at=performed_at,
        current_location_id=req.output_location_id,
    )
    session.add(out_lot)
    await session.flush()

    total_out_qty = sum(by_lot.values())

    session.add(ProductionOutput(
        production_order_id=po.id,
        output_lot_id=out_lot.id,
        quantity_kg=total_out_qty,
    ))

    ev_out = LotEvent(
        lot_id=out_lot.id,
        event_type="mix_output",
        reason=req.notes,
        performed_by=performed_by,
        performed_at=performed_at,
    )
    session.add(ev_out)
    await session.flush()
    event_ids.append(ev_out.id)

    mv_out = InventoryMovement(
        lot_id=out_lot.id,
        from_location_id=None,
        to_location_id=req.output_location_id,
        quantity_kg=total_out_qty,
        moved_at=performed_at,
        move_type="mix_output",
    )
    session.add(mv_out)
    await session.flush()

    await session.commit()

    return MixResponse(
        production_order_id=po.id,
        output_lot_id=out_lot.id,
        output_lot_code=out_code,
        input_movement_ids=input_movement_ids,
        output_movement_id=mv_out.id,
        lot_event_ids=event_ids,
    )
