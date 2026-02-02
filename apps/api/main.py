from datetime import datetime, timezone
from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel, Field, condecimal
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from meat_erp_core.db import get_session
from meat_erp_core.models import Item, Supplier, Location, Lot, LotEvent, InventoryMovement
from meat_erp_core.receiving import router as receiving_router
from meat_erp_core.lookups import router as lookups_router
from meat_erp_core.breakdown import router as production_router
from meat_erp_core.reservations_api import router as reservations_router
from meat_erp_core.sales_api import router as sales_router
from meat_erp_core.aging_api import router as aging_router
from meat_erp_core.qa_api import router as qa_router
from meat_erp_core.qa_read_api import router as qa_read_router
from meat_erp_core.mixing_api import router as mixing_router
from meat_erp_core.rework_api import router as rework_router
from meat_erp_core.reports_api import router as reports_router
from meat_erp_core.offline_api import router as offline_router
from meat_erp_core.recall_api import router as recall_router
from meat_erp_core.recall_actions_api import router as recall_actions_router
from meat_erp_core.lots_api import router as lots_router
from meat_erp_core.lot_events_api import router as lot_events_router
from meat_erp_core.loss_types_admin import router as loss_types_admin_router
from meat_erp_core.debug_seed import router as debug_seed_router

Kg = condecimal(gt=0, max_digits=12, decimal_places=3)

app = FastAPI(title="Meat ERP Core API (v2.5)")
app.include_router(lookups_router)
app.include_router(receiving_router)
app.include_router(production_router)
app.include_router(reservations_router)
app.include_router(sales_router)
app.include_router(aging_router)
app.include_router(qa_router)
app.include_router(qa_read_router)
app.include_router(mixing_router)
app.include_router(rework_router)
app.include_router(reports_router)
app.include_router(offline_router)
app.include_router(recall_router)
app.include_router(recall_actions_router)
app.include_router(lots_router)
app.include_router(lot_events_router)
app.include_router(loss_types_admin_router)
app.include_router(debug_seed_router)

@app.get("/health")
async def health():
    return {"ok": True}

class SeedRequest(BaseModel):
    item_sku: str = "BEEF-QUARTER"
    item_name: str = "Beef Quarter"
    supplier_name: str = "Default Supplier"
    location_name: str = "RAW"
    location_kind: str = "raw"

@app.post("/debug/seed")
async def seed(req: SeedRequest, session: AsyncSession = Depends(get_session)):
    # idempotent-ish seed
    item = (await session.execute(select(Item).where(Item.sku == req.item_sku))).scalar_one_or_none()
    if not item:
        item = Item(sku=req.item_sku, name=req.item_name, is_meat=True)
        session.add(item)

    supplier = (await session.execute(select(Supplier).where(Supplier.name == req.supplier_name))).scalar_one_or_none()
    if not supplier:
        supplier = Supplier(name=req.supplier_name)
        session.add(supplier)

    loc = (await session.execute(select(Location).where(Location.name == req.location_name))).scalar_one_or_none()
    if not loc:
        loc = Location(name=req.location_name, kind=req.location_kind)
        session.add(loc)

    await session.commit()
    return {"item_id": item.id, "supplier_id": supplier.id, "location_id": loc.id}

class DebugCreateLotRequest(BaseModel):
    lot_code: str = Field(min_length=2, max_length=64)
    item_id: int
    supplier_id: int
    to_location_id: int
    quantity_kg: Kg
    performed_by: int = 1
    reason: str = "Receiving"

@app.post("/debug/lots")
async def debug_create_lot(req: DebugCreateLotRequest, session: AsyncSession = Depends(get_session)):
    now = datetime.now(timezone.utc)

    lot = Lot(
        lot_code=req.lot_code,
        item_id=req.item_id,
        supplier_id=req.supplier_id,
        state="received",
        received_at=now,
    )
    session.add(lot)
    await session.flush()  # get lot.id

    # audit + movement in same transaction
    session.add(LotEvent(
        lot_id=lot.id,
        event_type="received",
        reason=req.reason,
        performed_by=req.performed_by,
        performed_at=now,
    ))
    session.add(InventoryMovement(
        lot_id=lot.id,
        from_location_id=None,
        to_location_id=req.to_location_id,
        quantity_kg=req.quantity_kg,
        moved_at=now,
        move_type="receive",
    ))

    await session.commit()
    return {"lot_id": lot.id, "lot_code": lot.lot_code}

class DebugStateChangeRequest(BaseModel):
    new_state: str
    performed_by: int = 1
    reason: str = "State change"
    with_event: bool = True

@app.post("/debug/lots/{lot_id}/state")
async def debug_change_state(lot_id: int, req: DebugStateChangeRequest, session: AsyncSession = Depends(get_session)):
    now = datetime.now(timezone.utc)

    # ensure lot exists
    lot = (await session.execute(select(Lot).where(Lot.id == lot_id))).scalar_one_or_none()
    if not lot:
        raise HTTPException(status_code=404, detail="Lot not found")

    # optionally create lot_event first (required for DB trigger)
    if req.with_event:
        session.add(LotEvent(
            lot_id=lot_id,
            event_type=f"state:{req.new_state}",
            reason=req.reason,
            performed_by=req.performed_by,
            performed_at=now,
        ))
        await session.flush()

    # update lot state - trigger will enforce audit
    await session.execute(update(Lot).where(Lot.id == lot_id).values(state=req.new_state))
    try:
        await session.commit()
    except Exception as e:
        await session.rollback()
        # show the DB error
        raise HTTPException(status_code=400, detail=str(e))

    return {"lot_id": lot_id, "state": req.new_state, "with_event": req.with_event}
