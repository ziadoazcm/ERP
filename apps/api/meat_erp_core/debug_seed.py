from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from meat_erp_core.db import get_session
from meat_erp_core.models import (
    Item, Supplier, Customer, Location,
    Lot, InventoryMovement, LotEvent,
    ProcessProfile,
)

router = APIRouter(prefix="/debug", tags=["debug"])

@router.post("/seed-all")
async def seed_all(session: AsyncSession = Depends(get_session)):
    now = datetime.now(timezone.utc)

    for tbl in [
        "sale_lines", "sales", "reservations",
        "inventory_movements", "lot_events",
        "qa_checks", "production_outputs", "production_inputs",
        "production_orders", "breakdown_losses",
        "lots", "items", "suppliers", "customers",
        "locations", "process_profiles",
    ]:
        await session.execute(text(f"DELETE FROM {tbl}"))

    beef = Item(sku="BEEF-PRIMAL", name="Beef Primal", is_meat=True)
    trim = Item(sku="BEEF-TRIM", name="Beef Trim", is_meat=True)
    sausage = Item(sku="SAUSAGE", name="Beef Sausage", is_meat=True)
    session.add_all([beef, trim, sausage])

    supplier = Supplier(name="Test Abattoir")
    customer = Customer(name="Test Restaurant")
    session.add_all([supplier, customer])

    raw = Location(name="Raw Chiller", kind="storage")
    aging = Location(name="Dry Aging Room", kind="aging")
    session.add_all([raw, aging])

    breakdown_profile = ProcessProfile(name="Butchery Breakdown", allows_lot_mixing=False)
    sausage_profile = ProcessProfile(name="Sausage Mixing", allows_lot_mixing=True)
    session.add_all([breakdown_profile, sausage_profile])

    await session.flush()

    lot = Lot(
        lot_code="REC-TEST-001",
        item_id=beef.id,
        supplier_id=supplier.id,
        received_at=now - timedelta(days=10),
        state="received",
        current_location_id=raw.id,
    )
    session.add(lot)
    await session.flush()

    session.add(InventoryMovement(
        lot_id=lot.id,
        from_location_id=None,
        to_location_id=raw.id,
        quantity_kg=100.000,
        moved_at=now - timedelta(days=10),
        move_type="receiving",
    ))

    session.add(LotEvent(
        lot_id=lot.id,
        event_type="received",
        reason="Seed data",
        performed_by=1,
        performed_at=now - timedelta(days=10),
    ))
    await session.flush()

    session.add(LotEvent(
        lot_id=lot.id,
        event_type="aging_started",
        reason="Seed aging",
        performed_by=1,
        performed_at=now - timedelta(days=7),
    ))
    lot.state = "aging"
    lot.aging_started_at = now - timedelta(days=7)
    lot.ready_at = now - timedelta(days=2)
    await session.flush()

    session.add(LotEvent(
        lot_id=lot.id,
        event_type="released",
        reason="Seed release",
        performed_by=1,
        performed_at=now - timedelta(days=2),
    ))
    lot.state = "released"
    lot.released_at = now - timedelta(days=2)
    await session.flush()

    await session.commit()

    return {
        "ok": True,
        "lot_id": lot.id,
        "message": "Seed complete: 1 received → aged → released lot (100kg)",
    }


@router.post("/seed-rich")
async def seed_rich(session: AsyncSession = Depends(get_session)):
    """Create rich test data with multiple lots in various states for testing."""
    now = datetime.now(timezone.utc)

    for tbl in [
        "sale_lines", "sales", "reservations",
        "inventory_movements", "lot_events",
        "qa_checks", "production_outputs", "production_inputs",
        "production_orders", "breakdown_losses",
        "lots", "items", "suppliers", "customers",
        "locations", "process_profiles",
    ]:
        await session.execute(text(f"DELETE FROM {tbl}"))

    beef = Item(sku="BEEF-PRIMAL", name="Beef Primal", is_meat=True)
    ribeye = Item(sku="BEEF-RIBEYE", name="Beef Ribeye", is_meat=True)
    trim = Item(sku="BEEF-TRIM", name="Beef Trim", is_meat=True)
    sausage = Item(sku="SAUSAGE", name="Beef Sausage", is_meat=True)
    session.add_all([beef, ribeye, trim, sausage])

    supplier1 = Supplier(name="Premium Farms")
    supplier2 = Supplier(name="Valley Abattoir")
    customer1 = Customer(name="Fine Dining Restaurant")
    customer2 = Customer(name="Butcher Shop Chain")
    session.add_all([supplier1, supplier2, customer1, customer2])

    raw = Location(name="Raw Chiller", kind="storage")
    aging = Location(name="Dry Aging Room", kind="aging")
    finished = Location(name="Finished Goods", kind="storage")
    quarantine = Location(name="Quarantine Hold", kind="quarantine")
    session.add_all([raw, aging, finished, quarantine])

    breakdown_profile = ProcessProfile(name="Butchery Breakdown", allows_lot_mixing=False)
    sausage_profile = ProcessProfile(name="Sausage Mixing", allows_lot_mixing=True)
    session.add_all([breakdown_profile, sausage_profile])

    await session.flush()

    lots_created = []

    lot1 = Lot(
        lot_code="REC-2026-001",
        item_id=beef.id,
        supplier_id=supplier1.id,
        received_at=now - timedelta(days=14),
        state="received",
        current_location_id=raw.id,
    )
    session.add(lot1)
    await session.flush()
    session.add(InventoryMovement(lot_id=lot1.id, from_location_id=None, to_location_id=raw.id, quantity_kg=150.0, moved_at=now - timedelta(days=14), move_type="receiving"))
    session.add(LotEvent(lot_id=lot1.id, event_type="received", reason="Initial receiving", performed_by=1, performed_at=now - timedelta(days=14)))
    await session.flush()
    session.add(LotEvent(lot_id=lot1.id, event_type="aging_started", reason="Start dry aging", performed_by=1, performed_at=now - timedelta(days=12)))
    lot1.state = "aging"
    lot1.aging_started_at = now - timedelta(days=12)
    lot1.ready_at = now - timedelta(days=5)
    await session.flush()
    session.add(LotEvent(lot_id=lot1.id, event_type="released", reason="Aging complete, QA passed", performed_by=1, performed_at=now - timedelta(days=5)))
    lot1.state = "released"
    lot1.released_at = now - timedelta(days=5)
    await session.flush()
    lots_created.append({"lot_code": lot1.lot_code, "state": "released", "qty_kg": 150})

    lot2 = Lot(
        lot_code="REC-2026-002",
        item_id=ribeye.id,
        supplier_id=supplier2.id,
        received_at=now - timedelta(days=7),
        state="received",
        current_location_id=aging.id,
    )
    session.add(lot2)
    await session.flush()
    session.add(InventoryMovement(lot_id=lot2.id, from_location_id=None, to_location_id=aging.id, quantity_kg=80.0, moved_at=now - timedelta(days=7), move_type="receiving"))
    session.add(LotEvent(lot_id=lot2.id, event_type="received", reason="Premium ribeye received", performed_by=1, performed_at=now - timedelta(days=7)))
    await session.flush()
    session.add(LotEvent(lot_id=lot2.id, event_type="aging_started", reason="Start aging", performed_by=1, performed_at=now - timedelta(days=6)))
    lot2.state = "aging"
    lot2.aging_started_at = now - timedelta(days=6)
    lot2.ready_at = now + timedelta(days=8)
    await session.flush()
    lots_created.append({"lot_code": lot2.lot_code, "state": "aging", "qty_kg": 80})

    lot3 = Lot(
        lot_code="REC-2026-003",
        item_id=beef.id,
        supplier_id=supplier1.id,
        received_at=now - timedelta(days=3),
        state="received",
        current_location_id=raw.id,
    )
    session.add(lot3)
    await session.flush()
    session.add(InventoryMovement(lot_id=lot3.id, from_location_id=None, to_location_id=raw.id, quantity_kg=200.0, moved_at=now - timedelta(days=3), move_type="receiving"))
    session.add(LotEvent(lot_id=lot3.id, event_type="received", reason="Fresh batch", performed_by=1, performed_at=now - timedelta(days=3)))
    await session.flush()
    lots_created.append({"lot_code": lot3.lot_code, "state": "received", "qty_kg": 200})

    lot4 = Lot(
        lot_code="QF-2026-001",
        item_id=trim.id,
        supplier_id=supplier2.id,
        received_at=now - timedelta(days=10),
        state="received",
        current_location_id=quarantine.id,
    )
    session.add(lot4)
    await session.flush()
    session.add(InventoryMovement(lot_id=lot4.id, from_location_id=None, to_location_id=quarantine.id, quantity_kg=50.0, moved_at=now - timedelta(days=10), move_type="receiving"))
    session.add(LotEvent(lot_id=lot4.id, event_type="received", reason="Trim received", performed_by=1, performed_at=now - timedelta(days=10)))
    await session.flush()
    session.add(LotEvent(lot_id=lot4.id, event_type="quarantined", reason="Failed temperature check", performed_by=1, performed_at=now - timedelta(days=9)))
    lot4.state = "quarantined"
    await session.flush()
    lots_created.append({"lot_code": lot4.lot_code, "state": "quarantined", "qty_kg": 50})

    lot5 = Lot(
        lot_code="QF-2026-002",
        item_id=beef.id,
        supplier_id=supplier1.id,
        received_at=now - timedelta(days=5),
        state="received",
        current_location_id=quarantine.id,
    )
    session.add(lot5)
    await session.flush()
    session.add(InventoryMovement(lot_id=lot5.id, from_location_id=None, to_location_id=quarantine.id, quantity_kg=75.0, moved_at=now - timedelta(days=5), move_type="receiving"))
    session.add(LotEvent(lot_id=lot5.id, event_type="received", reason="Primal received", performed_by=1, performed_at=now - timedelta(days=5)))
    await session.flush()
    session.add(LotEvent(lot_id=lot5.id, event_type="quarantined", reason="Contamination suspected", performed_by=1, performed_at=now - timedelta(days=4)))
    lot5.state = "quarantined"
    await session.flush()
    lots_created.append({"lot_code": lot5.lot_code, "state": "quarantined", "qty_kg": 75})

    await session.commit()

    return {
        "ok": True,
        "message": "Rich seed complete",
        "lots": lots_created,
        "summary": {
            "items": 4,
            "suppliers": 2,
            "customers": 2,
            "locations": 4,
            "lots": 5,
            "quarantined": 2,
        },
    }
