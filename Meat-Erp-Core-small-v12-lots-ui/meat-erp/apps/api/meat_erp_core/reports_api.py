from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from meat_erp_core.availability import available_kg, reserved_kg, available_for_sale_kg
from meat_erp_core.db import get_session
from meat_erp_core.models import Lot, Item, Location


router = APIRouter(prefix="/reports", tags=["reports"])


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


@router.get("/at-risk")
async def at_risk(days: int = 7, include_quarantined: bool = True, session: AsyncSession = Depends(get_session)):
    """Operational reporting view:

    - Aging lots that are NOT READY yet
    - Lots expiring within the next N days
    - Quarantined lots (optional)
    """
    now = _now_utc()
    horizon = now + timedelta(days=max(1, min(days, 60)))

    rows = (await session.execute(
        select(Lot, Item, Location)
        .join(Item, Item.id == Lot.item_id)
        .outerjoin(Location, Location.id == Lot.current_location_id)
        .where(Lot.state.in_(["aging", "released", "quarantined"]))
        .order_by(Lot.id.desc())
        .limit(2000)
    )).all()

    out = []
    for lot, item, loc in rows:
        if lot.state == "quarantined" and not include_quarantined:
            continue

        flags: list[str] = []
        days_to_ready = None
        days_to_expiry = None

        if lot.state == "aging":
            if lot.ready_at is None:
                flags.append("aging_missing_ready_at")
            else:
                if lot.ready_at > now:
                    flags.append("aging_not_ready")
                    days_to_ready = round((lot.ready_at - now).total_seconds() / 86400, 2)

        if lot.expires_at is not None and lot.expires_at <= horizon:
            flags.append("expiring_soon")
            days_to_expiry = round((lot.expires_at - now).total_seconds() / 86400, 2)

        if lot.state == "quarantined":
            flags.append("quarantined")

        if not flags:
            continue

        avail = await available_kg(session, lot.id)
        resv = await reserved_kg(session, lot.id)
        sellable = await available_for_sale_kg(session, lot.id)

        out.append({
            "lot_id": lot.id,
            "lot_code": lot.lot_code,
            "item_name": item.name,
            "state": lot.state,
            "location_name": loc.name if loc else None,
            "ready_at": lot.ready_at,
            "expires_at": lot.expires_at,
            "flags": flags,
            "days_to_ready": days_to_ready,
            "days_to_expiry": days_to_expiry,
            "available_qty_kg": avail,
            "reserved_qty_kg": resv,
            "sellable_qty_kg": sellable,
        })

    return {"now": now, "horizon": horizon, "rows": out}


@router.get("/stock")
async def stock(include_zero: bool = False, session: AsyncSession = Depends(get_session)):
    """Lot-level stock view used for operations.

    Returns lots with computed available/reserved/sellable quantities.
    """
    rows = (await session.execute(
        select(Lot, Item, Location)
        .join(Item, Item.id == Lot.item_id)
        .outerjoin(Location, Location.id == Lot.current_location_id)
        .where(Lot.state.notin_(["disposed"]))
        .order_by(Lot.id.desc())
        .limit(3000)
    )).all()

    out = []
    for lot, item, loc in rows:
        avail = await available_kg(session, lot.id)
        if (not include_zero) and avail <= 0:
            continue
        resv = await reserved_kg(session, lot.id)
        sellable = await available_for_sale_kg(session, lot.id)

        out.append({
            "lot_id": lot.id,
            "lot_code": lot.lot_code,
            "item_name": item.name,
            "state": lot.state,
            "location_name": loc.name if loc else None,
            "received_at": lot.received_at,
            "ready_at": lot.ready_at,
            "expires_at": lot.expires_at,
            "available_qty_kg": avail,
            "reserved_qty_kg": resv,
            "sellable_qty_kg": sellable,
        })

    return {"rows": out}
