from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from meat_erp_core.db import get_session
from meat_erp_core.models import Lot, QACheck, Item

router = APIRouter(prefix="/qa", tags=["qa"])

@router.get("/checks/by-lot/{lot_id}")
async def list_checks_for_lot(lot_id: int, session: AsyncSession = Depends(get_session)):
    lot = (await session.execute(select(Lot).where(Lot.id == lot_id))).scalar_one_or_none()
    if not lot:
        raise HTTPException(status_code=404, detail="Lot not found")

    rows = (await session.execute(
        select(QACheck)
        .where(QACheck.lot_id == lot_id)
        .order_by(QACheck.performed_at.desc())
        .limit(200)
    )).scalars().all()

    return [{
        "id": r.id,
        "check_type": r.check_type,
        "passed": r.passed,
        "notes": r.notes,
        "performed_at": r.performed_at,
    } for r in rows]


@router.get("/quarantined")
async def list_quarantined(limit: int = 200, session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(
        select(Lot, Item)
        .join(Item, Item.id == Lot.item_id)
        .where(Lot.state == "quarantined")
        .order_by(Lot.id.desc())
        .limit(limit)
    )).all()

    return [{
        "id": lot.id,
        "lot_code": lot.lot_code,
        "state": lot.state,
        "item_id": item.id,
        "item_name": item.name,
        "received_at": lot.received_at,
    } for (lot, item) in rows]
