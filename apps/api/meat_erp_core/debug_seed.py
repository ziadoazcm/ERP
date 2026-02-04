from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from meat_erp_core.db import get_session
from meat_erp_core.models import (
    Item, Supplier, Customer, Location,
    Lot, InventoryMovement, LotEvent,
    ProcessProfile,
from sqlalchemy import text, select
from meat_erp_core.models import LossType, Reservation
from meat_erp_core.receiving import ReceivingRequest, create_lot_txn
from meat_erp_core.breakdown import BreakdownRequest, BreakdownOutput, BreakdownLossIn, breakdown_txn
from meat_erp_core.mixing_api import MixRequest, MixInput, mix
from meat_erp_core.qa_api import QACheckRequest, create_qa_check
from meat_erp_core.sales_api import SaleCreateRequest, SaleLineIn, create_sale_txn
from meat_erp_core.offline_api import OfflineQueueSubmitRequest, OfflineAction, submit_queue

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

@router.post("/seed-demo-full")
async def seed_demo_full(session: AsyncSession = Depends(get_session)):
    now = datetime.now(timezone.utc)

    # IMPORTANT: TRUNCATE with RESTART IDENTITY so process_profiles id=1 again
    await session.execute(text("""
        TRUNCATE TABLE
          offline_conflicts,
          offline_queue,
          sale_lines,
          sales,
          reservations,
          inventory_movements,
          lot_events,
          qa_checks,
          production_outputs,
          production_inputs,
          production_orders,
          breakdown_losses,
          lots,
          loss_types,
          items,
          suppliers,
          customers,
          locations,
          process_profiles
        RESTART IDENTITY CASCADE;
    """))

    # ---------- Reference data ----------
    raw = Location(name="RAW", kind="storage")
    wip = Location(name="WIP", kind="storage")
    aging = Location(name="AGING", kind="aging")
    finished = Location(name="FINISHED", kind="storage")
    session.add_all([raw, wip, aging, finished])

    # Loss types required by breakdown validation
    session.add_all([
        LossType(code="DRIP", name="Drip Loss", active=True, sort_order=1),
        LossType(code="TRIM", name="Trim Loss", active=True, sort_order=2),
    ])

    # Process profiles (breakdown MUST be id=1 because breakdown_txn hardcodes it)
    breakdown_profile = ProcessProfile(name="Butchery Breakdown", allows_lot_mixing=False)
    sausage_profile = ProcessProfile(name="Sausage Mixing", allows_lot_mixing=True)
    session.add_all([breakdown_profile, sausage_profile])

    supplier = Supplier(name="Demo Abattoir")
    cust1 = Customer(name="Restaurant A")
    cust2 = Customer(name="Retail Customer")
    session.add_all([supplier, cust1, cust2])

    # Items for all screens
    items = [
        Item(sku="BEEF-SIDE", name="Beef Side", is_meat=True),
        Item(sku="BEEF-CHUCK", name="Beef Chuck", is_meat=True),
        Item(sku="BEEF-ROUND", name="Beef Round", is_meat=True),
        Item(sku="BEEF-BRISKET", name="Beef Brisket", is_meat=True),
        Item(sku="BEEF-RIBEYE", name="Beef Ribeye", is_meat=True),
        Item(sku="BEEF-STRIPLOIN", name="Beef Striploin", is_meat=True),
        Item(sku="BEEF-TENDERLOIN", name="Beef Tenderloin", is_meat=True),
        Item(sku="BEEF-SIRLOIN", name="Beef Sirloin", is_meat=True),
        Item(sku="BEEF-SHORTRIB", name="Beef Short Rib", is_meat=True),
        Item(sku="BEEF-TRIM-80CL", name="Beef Trim 80CL", is_meat=True),
        Item(sku="BEEF-FAT", name="Beef Fat", is_meat=True),
        Item(sku="BEEF-BONES", name="Beef Bones", is_meat=False),
        Item(sku="SAUSAGE", name="Beef Sausage", is_meat=True),
    ]
    session.add_all(items)
    await session.flush()

    by_sku = {i.sku: i for i in items}

    # ---------- Receiving ----------
    recv = await create_lot_txn(session, ReceivingRequest(
        item_id=by_sku["BEEF-SIDE"].id,
        supplier_id=supplier.id,
        quantity_kg=180.000,
        to_location_id=raw.id,
        notes="Demo receiving: whole beef side",
        received_at=now - timedelta(days=2),
    ))
    input_lot_id = recv["lot_id"]

    # ---------- Breakdown (full consume + no unassigned) ----------
    bd_req = BreakdownRequest(
        input_lot_id=input_lot_id,
        input_quantity_kg=180.000,
        outputs=[
            BreakdownOutput(item_id=by_sku["BEEF-CHUCK"].id, quantity_kg=55.000, to_location_id=wip.id),
            BreakdownOutput(item_id=by_sku["BEEF-ROUND"].id, quantity_kg=45.000, to_location_id=wip.id),
            BreakdownOutput(item_id=by_sku["BEEF-BRISKET"].id, quantity_kg=9.000, to_location_id=wip.id),
            BreakdownOutput(item_id=by_sku["BEEF-RIBEYE"].id, quantity_kg=12.000, to_location_id=wip.id),
            BreakdownOutput(item_id=by_sku["BEEF-STRIPLOIN"].id, quantity_kg=10.000, to_location_id=wip.id),
            BreakdownOutput(item_id=by_sku["BEEF-TENDERLOIN"].id, quantity_kg=4.000, to_location_id=wip.id),
            BreakdownOutput(item_id=by_sku["BEEF-SIRLOIN"].id, quantity_kg=11.000, to_location_id=wip.id),
            BreakdownOutput(item_id=by_sku["BEEF-SHORTRIB"].id, quantity_kg=10.000, to_location_id=wip.id),
            BreakdownOutput(item_id=by_sku["BEEF-TRIM-80CL"].id, quantity_kg=18.000, to_location_id=wip.id),
            BreakdownOutput(item_id=by_sku["BEEF-FAT"].id, quantity_kg=4.000, to_location_id=wip.id),
            BreakdownOutput(item_id=by_sku["BEEF-BONES"].id, quantity_kg=1.500, to_location_id=wip.id),
        ],
        losses=[BreakdownLossIn(loss_type="DRIP", quantity_kg=0.500, notes="Demo drip loss")],
        notes="Demo breakdown: whole beef",
        performed_at=now - timedelta(days=1),
    )
    bd_resp = await breakdown_txn(req=bd_req, session=session, performed_by=1)

    # Find lots we want to use next
    out_ids = [o["id"] for o in bd_resp.outputs]
    out_lots = (await session.execute(select(Lot).where(Lot.id.in_(out_ids)))).scalars().all()

    def find_lot(sku: str) -> Lot:
        item_id = by_sku[sku].id
        return next(l for l in out_lots if l.item_id == item_id)

    ribeye_lot = find_lot("BEEF-RIBEYE")
    trim_lot = find_lot("BEEF-TRIM-80CL")
    round_lot = find_lot("BEEF-ROUND")

    # Mark some as released + ready (needed for sales + mixing rules)
    for lot in [ribeye_lot, trim_lot, round_lot]:
        lot.state = "released"
        lot.ready_at = now - timedelta(days=1)
        lot.released_at = now - timedelta(days=1)
        lot.current_location_id = finished.id

    # Put one lot into aging (for aging screens)
    aging_lot = next(l for l in out_lots if l.id not in {ribeye_lot.id, trim_lot.id, round_lot.id})
    aging_lot.state = "aging"
    aging_lot.aging_started_at = now - timedelta(days=1)
    aging_lot.ready_at = now + timedelta(days=10)
    aging_lot.current_location_id = aging.id

    await session.flush()

    # ---------- Second trim lot for mixing ----------
    recv2 = await create_lot_txn(session, ReceivingRequest(
        item_id=by_sku["BEEF-TRIM-80CL"].id,
        supplier_id=supplier.id,
        quantity_kg=30.000,
        to_location_id=finished.id,
        notes="Demo receiving: trim for mixing",
        received_at=now - timedelta(days=3),
    ))
    trim2 = (await session.execute(select(Lot).where(Lot.id == recv2["lot_id"]))).scalar_one()
    trim2.state = "released"
    trim2.ready_at = now - timedelta(days=2)
    trim2.released_at = now - timedelta(days=2)

    await session.flush()

    # ---------- Mixing ----------
    mix_resp = await mix(MixRequest(
        process_profile_id=sausage_profile.id,
        inputs=[
            MixInput(lot_id=trim_lot.id, quantity_kg=10.000),
            MixInput(lot_id=trim2.id, quantity_kg=10.000),
        ],
        output_item_id=by_sku["SAUSAGE"].id,
        output_location_id=finished.id,
        notes="Demo mixing: sausage",
        performed_at=now - timedelta(hours=12),
    ), session=session)

    sausage_lot_id = mix_resp.output_lot_id

    # ---------- QA ----------
    # Pass ribeye
    await create_qa_check(QACheckRequest(
        lot_id=ribeye_lot.id,
        check_type="Visual",
        mode="full",
        passed=True,
        notes="Demo QA pass",
        performed_at=now - timedelta(hours=10),
    ), session=session)

    # Fail round (quarantines)
    await create_qa_check(QACheckRequest(
        lot_id=round_lot.id,
        check_type="Temp",
        mode="full",
        passed=False,
        notes="Demo QA fail",
        performed_at=now - timedelta(hours=9),
    ), session=session)

    # Partial split sausage
    await create_qa_check(QACheckRequest(
        lot_id=sausage_lot_id,
        check_type="Metal Detect",
        mode="partial",
        pass_qty_kg=18.000,
        fail_qty_kg=2.000,
        notes="Demo QA partial split",
        performed_at=now - timedelta(hours=1),
    ), session=session)

    # ---------- Reservations ----------
    session.add(Reservation(
        lot_id=ribeye_lot.id,
        customer_id=cust1.id,
        quantity_kg=5.000,
        reserved_at=now - timedelta(hours=2),
    ))
    await session.flush()

    # ---------- Sales ----------
    sale_resp = await create_sale_txn(SaleCreateRequest(
        customer_id=cust2.id,
        sold_at=now - timedelta(minutes=30),
        lines=[
            SaleLineIn(lot_id=ribeye_lot.id, quantity_kg=3.000),
        ],
        notes="Demo sale",
    ), session=session, performed_by=1)

    # ---------- Offline Queue (shows offline screen populated) ----------
    await submit_queue(OfflineQueueSubmitRequest(
        client_id="demo-ipad-01",
        submitted_by=1,
        actions=[
            OfflineAction(
                client_txn_id="txn-001",
                action_type="receiving",
                payload={
                    "item_id": by_sku["BEEF-SIDE"].id,
                    "supplier_id": supplier.id,
                    "quantity_kg": 25.000,
                    "to_location_id": raw.id,
                    "notes": "Offline receiving demo",
                },
            ),
            OfflineAction(
                client_txn_id="txn-002",
                action_type="sale",
                payload={
                    "customer_id": cust1.id,
                    "lines": [{"lot_id": ribeye_lot.id, "quantity_kg": 1.000}],
                    "notes": "Offline sale demo",
                },
            ),
        ],
    ), session=session)

    await session.commit()

    return {
        "ok": True,
        "message": "Seeded full demo dataset (receiving, breakdown, aging, mixing, QA, reservations, sales, offline).",
        "ids": {
            "input_lot_id": input_lot_id,
            "ribeye_lot_id": ribeye_lot.id,
            "trim_lot_id": trim_lot.id,
            "sausage_lot_id": sausage_lot_id,
            "sale_id": sale_resp.sale_id,
        }
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
