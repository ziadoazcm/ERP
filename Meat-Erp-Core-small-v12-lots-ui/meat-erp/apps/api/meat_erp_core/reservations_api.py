from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, condecimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from meat_erp_core.db import get_session
from meat_erp_core.models import Reservation, Lot, Customer, LotEvent
from meat_erp_core.availability import available_kg, reserved_kg

Kg = condecimal(gt=0, max_digits=12, decimal_places=3)

router = APIRouter(prefix="/reservations", tags=["reservations"])

class ReservationCreateRequest(BaseModel):
    lot_id: int
    customer_id: int
    quantity_kg: Kg
    reserved_at: datetime | None = None

class ReservationCreateResponse(BaseModel):
    reservation_id: int


@router.get("")
async def list_reservations(
    limit: int = 200,
    lot_id: int | None = None,
    customer_id: int | None = None,
    session: AsyncSession = Depends(get_session),
):
    q = (
        select(Reservation, Lot, Customer)
        .join(Lot, Lot.id == Reservation.lot_id)
        .join(Customer, Customer.id == Reservation.customer_id)
        .order_by(Reservation.reserved_at.desc(), Reservation.id.desc())
        .limit(limit)
    )
    if lot_id is not None:
        q = q.where(Reservation.lot_id == lot_id)
    if customer_id is not None:
        q = q.where(Reservation.customer_id == customer_id)

    rows = (await session.execute(q)).all()
    return [
        {
            "id": r.id,
            "lot_id": lot.id,
            "lot_code": lot.lot_code,
            "lot_state": lot.state,
            "customer_id": c.id,
            "customer_name": c.name,
            "quantity_kg": float(r.quantity_kg),
            "reserved_at": r.reserved_at,
        }
        for (r, lot, c) in rows
    ]


class ReservationCancelRequest(BaseModel):
    notes: str = ""
    canceled_at: datetime | None = None

@router.post("", response_model=ReservationCreateResponse)
async def create_reservation(req: ReservationCreateRequest, session: AsyncSession = Depends(get_session)):
    # Lock lot to prevent concurrent reservations/sales from oversubscribing availability.
    lot = (await session.execute(
        select(Lot).where(Lot.id == req.lot_id).with_for_update()
    )).scalar_one_or_none()
    if not lot:
        raise HTTPException(status_code=400, detail="Invalid lot_id")

    cust = (await session.execute(select(Customer).where(Customer.id == req.customer_id))).scalar_one_or_none()
    if not cust:
        raise HTTPException(status_code=400, detail="Invalid customer_id")

    reserved_at = req.reserved_at or datetime.now(timezone.utc)

    # Soft allocation must not exceed on-hand quantity.
    # We allow reserving even if lot isn't ready yet, but never if quarantined/disposed.
    if lot.state in ("quarantined", "disposed", "sold"):
        raise HTTPException(status_code=400, detail=f"Lot is not eligible for reservation (state={lot.state})")

    on_hand = await available_kg(session, req.lot_id)
    already_reserved = await reserved_kg(session, req.lot_id)
    remaining = on_hand - already_reserved
    if float(req.quantity_kg) - float(remaining) > 0.001:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Insufficient reservable quantity. on_hand={on_hand:.3f} "
                f"reserved={already_reserved:.3f} remaining={remaining:.3f} requested={float(req.quantity_kg):.3f}"
            ),
        )

    r = Reservation(
        lot_id=req.lot_id,
        customer_id=req.customer_id,
        quantity_kg=req.quantity_kg,
        reserved_at=reserved_at,
    )
    session.add(r)
    await session.commit()
    return ReservationCreateResponse(reservation_id=r.id)


@router.post("/{reservation_id}/cancel")
async def cancel_reservation(reservation_id: int, req: ReservationCancelRequest, session: AsyncSession = Depends(get_session)):
    notes = (req.notes or "").strip()
    if len(notes) < 2:
        raise HTTPException(status_code=400, detail="Notes are required to cancel a reservation")

    canceled_at = req.canceled_at or datetime.now(timezone.utc)
    performed_by = 1  # TODO: current_user.id from JWT

    res = (await session.execute(
        select(Reservation).where(Reservation.id == reservation_id)
    )).scalar_one_or_none()
    if not res:
        raise HTTPException(status_code=404, detail="Reservation not found")

    # Lock lot to avoid races with sale/reservation changes.
    lot = (await session.execute(
        select(Lot).where(Lot.id == res.lot_id).with_for_update()
    )).scalar_one_or_none()
    if not lot:
        raise HTTPException(status_code=400, detail="Invalid lot_id")

    # Delete reservation (soft allocation); keep audit via lot_event.
    await session.delete(res)

    ev = LotEvent(
        lot_id=lot.id,
        event_type="reservation_canceled",
        reason=notes,
        performed_by=performed_by,
        performed_at=canceled_at,
    )
    session.add(ev)
    await session.commit()
    return {"ok": True, "lot_id": lot.id, "lot_code": lot.lot_code, "lot_event_id": ev.id}
