from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from decimal import Decimal
from pydantic import BaseModel, Field, condecimal
from typing import Annotated, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update

from meat_erp_core.db import get_session
from meat_erp_core.models import (
    Lot, LotEvent, InventoryMovement,
    ProcessProfile, ProductionOrder, ProductionInput, ProductionOutput,
    Location, Item, BreakdownLoss, LossType
)
from meat_erp_core.availability import available_kg
from meat_erp_core.lot_codes import next_lot_code

router = APIRouter(prefix="/production", tags=["production"])

Kg = condecimal(gt=0, max_digits=12, decimal_places=3)

TOLERANCE = 0.001

class BreakdownOutput(BaseModel):
    item_id: int
    quantity_kg: Kg
    to_location_id: int

class BreakdownLossIn(BaseModel):
    loss_type: str = Field(min_length=2, max_length=64)
    quantity_kg: Kg
    notes: Optional[str] = Field(default=None, max_length=500)
    output_lot_code: str | None = None

class BreakdownRequest(BaseModel):
    input_lot_id: int
    input_quantity_kg: Kg
    outputs: List[BreakdownOutput] = Field(min_length=1)
    losses: List[BreakdownLossIn] = Field(default_factory=list)
    notes: str | None = Field(default=None, max_length=500)
    performed_at: datetime | None = None

class BreakdownResponse(BaseModel):
    production_order_id: int
    input_movement_id: int
    outputs: List[dict]  # [{id, lot_code}]
    output_movement_ids: List[int]
    loss_ids: List[int]
    loss_movement_ids: List[int]
    lot_event_ids: List[int]

async def breakdown_txn(req: BreakdownRequest, session: AsyncSession, performed_by: int = 1):
    reason = req.notes or "Breakdown"

    # Lock input lot to prevent concurrent consumption (sale/reservation/breakdown).
    input_lot = (await session.execute(
        select(Lot).where(Lot.id == req.input_lot_id).with_for_update()
    )).scalar_one_or_none()
    if not input_lot:
        raise HTTPException(status_code=400, detail="Invalid input_lot_id")

    if input_lot.state == "quarantined":
        raise HTTPException(status_code=400, detail="Cannot breakdown a quarantined lot")

    if input_lot.state in ("disposed", "sold"):
        raise HTTPException(status_code=400, detail=f"Lot is not eligible for breakdown (state={input_lot.state})")

    received_qty = (await session.execute(
        select(func.coalesce(func.sum(InventoryMovement.quantity_kg), 0))
        .where(InventoryMovement.lot_id == req.input_lot_id)
        .where(InventoryMovement.move_type == "receiving")
    )).scalar_one()

    if float(req.input_quantity_kg) - float(received_qty) > 0.001:
        raise HTTPException(
            status_code=400,
            detail=f"Input weight cannot exceed received weight. received={float(received_qty):.3f} input={float(req.input_quantity_kg):.3f}",
        )

    # Output lot codes are ALWAYS auto-assigned by the server.

    item_ids = list({o.item_id for o in req.outputs})
    loc_ids = list({o.to_location_id for o in req.outputs})

    items = (await session.execute(select(Item.id).where(Item.id.in_(item_ids)))).scalars().all()
    if len(items) != len(item_ids):
        raise HTTPException(status_code=400, detail="One or more output item_id invalid")

    locs = (await session.execute(select(Location.id).where(Location.id.in_(loc_ids)))).scalars().all()
    if len(locs) != len(loc_ids):
        raise HTTPException(status_code=400, detail="One or more to_location_id invalid")

    loss_codes = list({l.loss_type.strip() for l in (req.losses or [])})
    if loss_codes:
        rows = (await session.execute(
            select(LossType.code).where(LossType.code.in_(loss_codes)).where(LossType.active == True)  # noqa
        )).scalars().all()
        if len(rows) != len(loss_codes):
            raise HTTPException(status_code=400, detail="One or more loss_type is invalid or inactive")

    # No need to check for output lot_code collisions from client; server generates unique codes.

    performed_at = req.performed_at or datetime.now(timezone.utc)

    sum_outputs = sum([float(o.quantity_kg) for o in req.outputs])
    sum_losses = sum([float(l.quantity_kg) for l in (req.losses or [])])
    total_out = sum_outputs + sum_losses
    input_qty = float(req.input_quantity_kg)

    if abs(total_out - input_qty) > TOLERANCE:
        raise HTTPException(
            status_code=400,
            detail=f"Weight mismatch. input={input_qty:.3f} outputs+losses={total_out:.3f} (no unassigned weight allowed)",
        )

    available = await available_kg(session, req.input_lot_id)
    if input_qty - available > TOLERANCE:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient available quantity on input lot. requested={input_qty:.3f} available={available:.3f}",
        )

    # Breakdown is single-input and MUST fully consume the lot's remaining availability.
    # This prevents breaking down the same physical lot multiple times.
    if abs(input_qty - float(available)) > TOLERANCE:
        raise HTTPException(
            status_code=400,
            detail=f"Breakdown must consume full available quantity. available={float(available):.3f} input={input_qty:.3f}",
        )

    po = ProductionOrder(
        process_profile_id=1,  # Default breakdown profile
        process_type="breakdown",
        is_rework=False,
        started_at=performed_at,
        completed_at=performed_at,
    )
    session.add(po)
    await session.flush()

    pi = ProductionInput(
        production_order_id=po.id,
        lot_id=req.input_lot_id,
        quantity_kg=req.input_quantity_kg,
    )
    session.add(pi)

    ev_ids: List[int] = []
    ev_start = LotEvent(
        lot_id=req.input_lot_id,
        event_type="breakdown",
        reason=reason,
        performed_by=performed_by,
        performed_at=performed_at,
    )
    session.add(ev_start)
    await session.flush()
    ev_ids.append(ev_start.id)

    # Consume material from the lot's current location.
    input_mv = InventoryMovement(
        lot_id=req.input_lot_id,
        from_location_id=getattr(input_lot, "current_location_id", None),
        to_location_id=None,
        quantity_kg=req.input_quantity_kg,
        moved_at=performed_at,
        move_type="breakdown_input",
    )
    session.add(input_mv)
    await session.flush()

    outputs_created: List[dict] = []
    output_mv_ids: List[int] = []

    for o in req.outputs:
        code = await next_lot_code(session, "BD", performed_at)

        out_lot = Lot(
            lot_code=code,
            item_id=o.item_id,
            supplier_id=input_lot.supplier_id,
            received_at=input_lot.received_at,
            state=input_lot.state,
            current_location_id=o.to_location_id,
            ready_at=getattr(input_lot, "ready_at", None),
            released_at=getattr(input_lot, "released_at", None),
            expires_at=getattr(input_lot, "expires_at", None),
        )
        if not out_lot.lot_code:
            raise HTTPException(status_code=500, detail="Output lot_code was not generated")
        session.add(out_lot)
        await session.flush()
        outputs_created.append({"id": out_lot.id, "lot_code": out_lot.lot_code})

        session.add(ProductionOutput(
            production_order_id=po.id,
            output_lot_id=out_lot.id,
            quantity_kg=o.quantity_kg,
        ))

        ev_out = LotEvent(
            lot_id=out_lot.id,
            event_type="created_from_breakdown",
            reason=reason,
            performed_by=performed_by,
            performed_at=performed_at,
        )
        session.add(ev_out)
        await session.flush()
        ev_ids.append(ev_out.id)

        mv_out = InventoryMovement(
            lot_id=out_lot.id,
            from_location_id=None,
            to_location_id=o.to_location_id,
            quantity_kg=o.quantity_kg,
            moved_at=performed_at,
            move_type="breakdown_output",
        )
        session.add(mv_out)
        await session.flush()
        output_mv_ids.append(mv_out.id)

    loss_movement_ids: List[int] = []
    loss_ids: List[int] = []

    for loss in (req.losses or []):
        bl = BreakdownLoss(
            production_order_id=po.id,
            loss_type=loss.loss_type.strip(),
            quantity_kg=loss.quantity_kg,
            notes=loss.notes,
            created_at=performed_at,
        )
        session.add(bl)
        await session.flush()
        loss_ids.append(bl.id)

        ev_loss = LotEvent(
            lot_id=req.input_lot_id,
            event_type=f"breakdown_loss:{loss.loss_type.strip()}",
            reason=reason,
            performed_by=performed_by,
            performed_at=performed_at,
        )
        session.add(ev_loss)
        await session.flush()
        ev_ids.append(ev_loss.id)

        mv_loss = InventoryMovement(
            lot_id=req.input_lot_id,
            from_location_id=getattr(input_lot, "current_location_id", None),
            to_location_id=None,
            quantity_kg=loss.quantity_kg,
            moved_at=performed_at,
            move_type=f"breakdown_loss:{loss.loss_type.strip()}",
        )
        session.add(mv_loss)
        await session.flush()
        loss_movement_ids.append(mv_loss.id)

    # Mark input lot as disposed after full consumption.
    await session.execute(
        update(Lot).where(Lot.id == req.input_lot_id).values(state="disposed")
    )
    ev_disposed = LotEvent(
        lot_id=req.input_lot_id,
        event_type="disposed",
        reason=reason,
        performed_by=performed_by,
        performed_at=performed_at,
    )
    session.add(ev_disposed)
    await session.flush()
    ev_ids.append(ev_disposed.id)


    return BreakdownResponse(
        production_order_id=po.id,
        input_movement_id=input_mv.id,
        outputs=outputs_created,
        output_movement_ids=output_mv_ids,
        lot_event_ids=ev_ids,
        loss_ids=loss_ids,
        loss_movement_ids=loss_movement_ids,
    )

@router.post("/breakdown", response_model=BreakdownResponse)
async def breakdown(req: BreakdownRequest, session: AsyncSession = Depends(get_session)):
    # TODO: performed_by from JWT current_user
    performed_by = 1
    resp = await breakdown_txn(req=req, session=session, performed_by=performed_by)
    await session.commit()
    return resp
