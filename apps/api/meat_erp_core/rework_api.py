from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, condecimal
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from meat_erp_core.availability import available_kg
from meat_erp_core.db import get_session
from meat_erp_core.lot_codes import next_lot_code
from meat_erp_core.models import (
    BreakdownLoss,
    InventoryMovement,
    Item,
    Location,
    Lot,
    LotEvent,
    ProcessProfile,
    ProductionInput,
    ProductionOrder,
    ProductionOutput,
)


Kg = condecimal(gt=0, max_digits=12, decimal_places=3)

router = APIRouter(prefix="/rework", tags=["rework"])


class ReworkLossIn(BaseModel):
    loss_type: str = Field(min_length=1, max_length=32)
    quantity_kg: Kg
    notes: str | None = Field(default=None, max_length=300)


class ReworkRequest(BaseModel):
    input_lot_id: int
    output_item_id: int
    to_location_id: int
    # Partial rework: how much of the input lot is reworked.
    # The remainder becomes a new lot (same item as input) so the original lot is
    # fully consumed exactly once (prevents double-counting / repeated rework).
    rework_quantity_kg: Kg
    losses: List[ReworkLossIn] = Field(default_factory=list)
    notes: str | None = Field(default=None, max_length=500)
    performed_at: datetime | None = None


async def _get_or_create_rework_profile(session: AsyncSession) -> ProcessProfile:
    prof = (
        await session.execute(select(ProcessProfile).where(ProcessProfile.name == "Rework / Regrade"))
    ).scalar_one_or_none()
    if prof:
        return prof

    prof = ProcessProfile(name="Rework / Regrade", allows_lot_mixing=False)
    session.add(prof)
    await session.flush()
    return prof


@router.post("", summary="Rework/Regrade a lot into a new lot (traceable)")
async def create_rework(req: ReworkRequest, session: AsyncSession = Depends(get_session)):
    performed_at = req.performed_at or datetime.now(timezone.utc)
    performed_by = 1  # TODO: current_user.id from JWT

    # Lock input lot to prevent double-consumption
    input_lot = (
        await session.execute(
            select(Lot).where(Lot.id == req.input_lot_id).with_for_update()
        )
    ).scalar_one_or_none()
    if not input_lot:
        raise HTTPException(status_code=404, detail="Input lot not found")

    if input_lot.state in ("quarantined", "disposed", "sold"):
        raise HTTPException(status_code=400, detail=f"Lot not eligible for rework (state={input_lot.state})")

    out_item = (
        await session.execute(select(Item).where(Item.id == req.output_item_id))
    ).scalar_one_or_none()
    if not out_item:
        raise HTTPException(status_code=404, detail="Output item not found")

    to_loc = (
        await session.execute(select(Location).where(Location.id == req.to_location_id))
    ).scalar_one_or_none()
    if not to_loc:
        raise HTTPException(status_code=404, detail="Destination location not found")

    avail = await available_kg(session, req.input_lot_id)
    avail_qty = float(avail)
    rework_qty = float(req.rework_quantity_kg)
    if rework_qty > avail_qty + 0.001:
        raise HTTPException(status_code=400, detail="Rework quantity cannot exceed available quantity")
    if rework_qty <= 0.0:
        raise HTTPException(status_code=400, detail="Rework quantity must be > 0")

    remainder_qty = max(0.0, avail_qty - rework_qty)

    loss_total = sum(float(x.quantity_kg) for x in req.losses)
    if loss_total > rework_qty + 0.001:
        raise HTTPException(status_code=400, detail="Losses cannot exceed rework quantity")

    # Production order
    prof = await _get_or_create_rework_profile(session)
    po = ProductionOrder(
        process_profile_id=prof.id,
        process_type="rework",
        is_rework=True,
        started_at=performed_at,
        completed_at=performed_at,
    )
    session.add(po)
    await session.flush()

    # Consume the original lot exactly once; remainder (if any) becomes a new lot.
    session.add(ProductionInput(production_order_id=po.id, lot_id=input_lot.id, quantity_kg=avail_qty))

    # Consume input: FROM current location -> None so availability drops
    session.add(
        InventoryMovement(
            lot_id=input_lot.id,
            from_location_id=getattr(input_lot, "current_location_id", None),
            to_location_id=None,
            quantity_kg=avail_qty,
            moved_at=performed_at,
            move_type="rework_input",
        )
    )

    session.add(
        LotEvent(
            lot_id=input_lot.id,
            event_type="rework_consumed",
            reason=req.notes,
            performed_by=performed_by,
            performed_at=performed_at,
        )
    )
    await session.flush()

    # Output (reworked) lot
    code = await next_lot_code(session, "RW", performed_at)
    out_lot = Lot(
        lot_code=code,
        item_id=out_item.id,
        supplier_id=getattr(input_lot, "supplier_id", None),
        received_at=getattr(input_lot, "received_at", performed_at),
        state=input_lot.state,  # keep same sellability state; sales gate still enforces rules
        aging_started_at=getattr(input_lot, "aging_started_at", None),
        ready_at=getattr(input_lot, "ready_at", None),
        released_at=getattr(input_lot, "released_at", None),
        expires_at=getattr(input_lot, "expires_at", None),
        current_location_id=req.to_location_id,
    )
    session.add(out_lot)
    await session.flush()

    reworked_out_qty = max(0.0, rework_qty - loss_total)
    session.add(ProductionOutput(production_order_id=po.id, output_lot_id=out_lot.id, quantity_kg=reworked_out_qty))

    session.add(
        InventoryMovement(
            lot_id=out_lot.id,
            from_location_id=None,
            to_location_id=req.to_location_id,
            quantity_kg=reworked_out_qty,
            moved_at=performed_at,
            move_type="rework_output",
        )
    )
    session.add(
        LotEvent(
            lot_id=out_lot.id,
            event_type="rework_output",
            reason=req.notes,
            performed_by=performed_by,
            performed_at=performed_at,
        )
    )

    # Remainder lot (if partial)
    remainder_lot = None
    if remainder_qty > 0.001:
        rm_code = await next_lot_code(session, "RM", performed_at)
        remainder_lot = Lot(
            lot_code=rm_code,
            item_id=getattr(input_lot, "item_id", None),
            supplier_id=getattr(input_lot, "supplier_id", None),
            received_at=getattr(input_lot, "received_at", performed_at),
            state=input_lot.state,
            aging_started_at=getattr(input_lot, "aging_started_at", None),
            ready_at=getattr(input_lot, "ready_at", None),
            released_at=getattr(input_lot, "released_at", None),
            expires_at=getattr(input_lot, "expires_at", None),
            current_location_id=getattr(input_lot, "current_location_id", None),
        )
        session.add(remainder_lot)
        await session.flush()

        session.add(ProductionOutput(production_order_id=po.id, output_lot_id=remainder_lot.id, quantity_kg=remainder_qty))
        session.add(
            InventoryMovement(
                lot_id=remainder_lot.id,
                from_location_id=None,
                to_location_id=getattr(input_lot, "current_location_id", None),
                quantity_kg=remainder_qty,
                moved_at=performed_at,
                move_type="rework_remainder",
            )
        )
        session.add(
            LotEvent(
                lot_id=remainder_lot.id,
                event_type="rework_remainder",
                reason=req.notes,
                performed_by=performed_by,
                performed_at=performed_at,
            )
        )

    # Losses (reuse breakdown_losses table for typed losses)
    for loss in req.losses:
        session.add(
            BreakdownLoss(
                production_order_id=po.id,
                loss_type=loss.loss_type,
                quantity_kg=loss.quantity_kg,
                notes=loss.notes,
                created_at=performed_at,
            )
        )
        session.add(
            LotEvent(
                lot_id=input_lot.id,
                event_type=f"rework_loss:{loss.loss_type}",
                reason=loss.notes,
                performed_by=performed_by,
                performed_at=performed_at,
            )
        )

    # Mark input lot disposed after successful rework
    await session.execute(update(Lot).where(Lot.id == input_lot.id).values(state="disposed"))
    session.add(
        LotEvent(
            lot_id=input_lot.id,
            event_type="disposed",
            reason="Rework consumed lot",
            performed_by=performed_by,
            performed_at=performed_at,
        )
    )

    await session.commit()
    resp = {
        "ok": True,
        "production_order_id": po.id,
        "input_lot_id": input_lot.id,
        "output_lot": {"id": out_lot.id, "lot_code": out_lot.lot_code, "quantity_kg": float(reworked_out_qty)},
        "loss_total_kg": float(loss_total),
    }
    if remainder_lot is not None:
        resp["remainder_lot"] = {
            "id": remainder_lot.id,
            "lot_code": remainder_lot.lot_code,
            "quantity_kg": float(remainder_qty),
        }
    return resp
