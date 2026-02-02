from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, condecimal
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from meat_erp_core.db import get_session
from meat_erp_core.models import Sale, SaleLine, Lot, Customer, LotEvent, InventoryMovement
from meat_erp_core.availability import available_for_sale_kg, available_kg

Kg = condecimal(gt=0, max_digits=12, decimal_places=3)

router = APIRouter(prefix="/sales", tags=["sales"])


class SaleLineIn(BaseModel):
    lot_id: int
    quantity_kg: Kg


class SaleCreateRequest(BaseModel):
    customer_id: int
    sold_at: datetime | None = None
    lines: List[SaleLineIn] = Field(min_length=1)
    notes: str | None = Field(default=None, max_length=500)


class SaleCreateResponse(BaseModel):
    sale_id: int
    sale_line_ids: List[int]
    movement_ids: List[int]
    lot_event_ids: List[int]


def _is_sellable(lot: Lot, now: datetime) -> tuple[bool, str]:
    if lot.state == "quarantined":
        return False, "Lot is quarantined"
    if lot.state != "released":
        return False, "Lot is not released"
    if not lot.ready_at:
        return False, "Lot has no ready_at"
    if lot.ready_at > now:
        return False, "Lot is not ready yet"
    return True, ""


async def create_sale_txn(req: SaleCreateRequest, session: AsyncSession, performed_by: int = 1):
    """Sell-by-lot with hard eligibility + availability gates.

    Notes:
    - performed_by comes from login (JWT) in the real system.
      For now we use a dev fallback.
    - Quantity truth is inventory_movements.
    - Reservations reduce sellable quantity.
    """

    cust = (await session.execute(select(Customer).where(Customer.id == req.customer_id))).scalar_one_or_none()
    if not cust:
        raise HTTPException(status_code=400, detail="Invalid customer_id")

    now = req.sold_at or datetime.now(timezone.utc)

    # Load lots
    lot_ids = [l.lot_id for l in req.lines]
    # Lock lots to prevent concurrent sales/reservations consuming the same availability.
    lots = (await session.execute(
        select(Lot)
        .where(Lot.id.in_(lot_ids))
        .order_by(Lot.id)
        .with_for_update()
    )).scalars().all()
    lot_map = {l.id: l for l in lots}
    if len(lot_map) != len(set(lot_ids)):
        raise HTTPException(status_code=400, detail="One or more lot_id invalid")

    # Collapse repeated lot lines
    by_lot: Dict[int, float] = {}
    for ln in req.lines:
        by_lot[ln.lot_id] = by_lot.get(ln.lot_id, 0.0) + float(ln.quantity_kg)

    # Validate gates
    for lot_id, qty in by_lot.items():
        lot = lot_map[lot_id]
        ok, msg = _is_sellable(lot, now)
        if not ok:
            raise HTTPException(status_code=400, detail=f"Lot {lot.lot_code}: {msg}")

        avail = await available_for_sale_kg(session, lot_id)
        if qty - avail > 0.001:
            raise HTTPException(
                status_code=400,
                detail=f"Lot {lot.lot_code}: insufficient available (reservations included). requested={qty:.3f} available={avail:.3f}",
            )

    # Create sale header
    sale = Sale(customer_id=req.customer_id, sold_at=now)
    session.add(sale)
    await session.flush()

    sale_line_ids: List[int] = []
    movement_ids: List[int] = []
    event_ids: List[int] = []

    # Create per-line records + movements
    for ln in req.lines:
        sl = SaleLine(sale_id=sale.id, lot_id=ln.lot_id, quantity_kg=ln.quantity_kg)
        session.add(sl)
        await session.flush()
        sale_line_ids.append(sl.id)

        lot = lot_map[ln.lot_id]

        ev = LotEvent(
            lot_id=ln.lot_id,
            event_type="sold",
            reason=req.notes,  # stored in DB column 'reason' but treated as notes
            performed_by=performed_by,
            performed_at=now,
        )
        session.add(ev)
        await session.flush()
        event_ids.append(ev.id)

        # IMPORTANT: set from_location_id so availability decreases.
        mv = InventoryMovement(
            lot_id=ln.lot_id,
            from_location_id=getattr(lot, "current_location_id", None),
            to_location_id=None,
            quantity_kg=ln.quantity_kg,
            moved_at=now,
            move_type="sale",
        )
        session.add(mv)
        await session.flush()
        movement_ids.append(mv.id)

    # If a lot has been fully sold (on-hand goes to ~0), mark it sold for clarity.
    for lot_id in by_lot.keys():
        on_hand = await available_kg(session, lot_id)
        if on_hand <= 0.001:
            await session.execute(update(Lot).where(Lot.id == lot_id).values(state="sold"))

    return SaleCreateResponse(
        sale_id=sale.id,
        sale_line_ids=sale_line_ids,
        movement_ids=movement_ids,
        lot_event_ids=event_ids,
    )

@router.post("", response_model=SaleCreateResponse)
async def create_sale(req: SaleCreateRequest, session: AsyncSession = Depends(get_session)):
    # TODO: performed_by from JWT current_user
    performed_by = 1
    resp = await create_sale_txn(req=req, session=session, performed_by=performed_by)
    await session.commit()
    return resp

