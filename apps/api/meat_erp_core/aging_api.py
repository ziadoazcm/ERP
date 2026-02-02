from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from meat_erp_core.db import get_session
from meat_erp_core.models import Lot, LotEvent, InventoryMovement, ProcessProfile, Location

router = APIRouter(prefix="/aging", tags=["aging"])

class AgingStartRequest(BaseModel):
    lot_id: int
    aging_location_id: int
    process_profile_id: int
    performed_by: int
    reason: str = Field(min_length=2, max_length=500)
    started_at: datetime | None = None

class AgingStartResponse(BaseModel):
    lot_id: int
    state: str
    aging_started_at: datetime
    ready_at: datetime
    lot_event_id: int
    movement_id: int

class AgingReleaseRequest(BaseModel):
    lot_id: int
    performed_by: int
    reason: str = Field(min_length=2, max_length=500)
    released_at: datetime | None = None

class AgingReleaseResponse(BaseModel):
    lot_id: int
    state: str
    released_at: datetime
    lot_event_id: int

def compute_ready_at(started_at: datetime, profile: ProcessProfile) -> datetime:
    if profile.default_aging_days is None:
        raise ValueError("Process profile missing default_aging_days")
    return started_at + timedelta(days=int(profile.default_aging_days))

@router.post("/start", response_model=AgingStartResponse)
async def start_aging(req: AgingStartRequest, session: AsyncSession = Depends(get_session)):
    lot = (await session.execute(select(Lot).where(Lot.id == req.lot_id))).scalar_one_or_none()
    if not lot:
        raise HTTPException(status_code=400, detail="Invalid lot_id")

    if lot.state == "quarantined":
        raise HTTPException(status_code=400, detail="Cannot age a quarantined lot")

    profile = (await session.execute(select(ProcessProfile).where(ProcessProfile.id == req.process_profile_id))).scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=400, detail="Invalid process_profile_id")

    loc = (await session.execute(select(Location).where(Location.id == req.aging_location_id))).scalar_one_or_none()
    if not loc:
        raise HTTPException(status_code=400, detail="Invalid aging_location_id")

    started_at = req.started_at or datetime.now(timezone.utc)

    try:
        ready_at = compute_ready_at(started_at, profile)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    ev = LotEvent(
        lot_id=req.lot_id,
        event_type="aging_started",
        reason=req.reason,
        performed_by=req.performed_by,
        performed_at=started_at,
    )
    session.add(ev)
    await session.flush()

    await session.execute(
        update(Lot)
        .where(Lot.id == req.lot_id)
        .values(
            state="aging",
            aging_started_at=started_at,
            ready_at=ready_at,
        )
    )

    await session.commit()

    return AgingStartResponse(
        lot_id=req.lot_id,
        state="aging",
        aging_started_at=started_at,
        ready_at=ready_at,
        lot_event_id=ev.id,
        movement_id=0,
    )

@router.post("/release", response_model=AgingReleaseResponse)
async def release_aging(req: AgingReleaseRequest, session: AsyncSession = Depends(get_session)):
    lot = (await session.execute(select(Lot).where(Lot.id == req.lot_id))).scalar_one_or_none()
    if not lot:
        raise HTTPException(status_code=400, detail="Invalid lot_id")

    if lot.state == "quarantined":
        raise HTTPException(status_code=400, detail="Cannot release a quarantined lot")

    if lot.state != "aging":
        raise HTTPException(status_code=400, detail="Lot is not in aging state")

    now = req.released_at or datetime.now(timezone.utc)

    if lot.ready_at is None:
        raise HTTPException(status_code=400, detail="Lot has no ready_at")

    if lot.ready_at > now:
        raise HTTPException(status_code=400, detail="Lot is not ready to release yet")

    ev = LotEvent(
        lot_id=req.lot_id,
        event_type="released",
        reason=req.reason,
        performed_by=req.performed_by,
        performed_at=now,
    )
    session.add(ev)
    await session.flush()

    await session.execute(
        update(Lot)
        .where(Lot.id == req.lot_id)
        .values(
            state="released",
            released_at=now,
        )
    )

    await session.commit()
    return AgingReleaseResponse(
        lot_id=req.lot_id,
        state="released",
        released_at=now,
        lot_event_id=ev.id,
    )
