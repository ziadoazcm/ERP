from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession

from meat_erp_core.db import get_session
from meat_erp_core.models import (
    Item, Supplier, Customer, Location, Lot,
    InventoryMovement, LotEvent,
    ProcessProfile, Reservation, LossType
)

from meat_erp_core.receiving import ReceivingRequest, create_lot_txn
from meat_erp_core.breakdown import (
    BreakdownRequest, BreakdownOutput, BreakdownLossIn, breakdown_txn
)
from meat_erp_core.mixing_api import MixRequest, MixInput, mix
from meat_erp_core.qa_api import QACheckRequest, create_qa_check
from meat_erp_core.sales_api import SaleCreateRequest, SaleLineIn, create_sale_txn
from meat_erp_core.offline_api import (
    OfflineQueueSubmitRequest, OfflineAction, submit_queue
)

router = APIRouter(prefix="/debug", tags=["debug"])


@router.post("/seed-demo-full")
async def seed_demo_full(session: AsyncSession = Depends(get_session)):
    """
    FULL demo seed:
    - Receiving
    - Breakdown (whole beef)
    - Aging
    - Mixing (sausage)
    - QA (pass / fail / partial)
    - Reservations
    - Sales
    - Offline queue
    """

    now = datetime.now(timezone.utc)

    # --------------------------------------------------
    # HARD RESET (demo DB only)
    # IMPORTANT: RESTART IDENTITY so breakdown profile = id 1
    # --------------------------------------------------
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

    # --------------------------------------------------
    # LOCATIONS
    # --------------------------------------------------
    raw = Location(name="RAW", kind="storage")
    wip = Location(name="WIP", kind="storage")
    aging = Location(name="AGING", kind="aging")
    finished = Location(name="FINISHED", kind="storage")
    session.add_all([raw, wip, aging, finished])

    # --------------------------------------------------
    # LOSS TYPES (required for breakdown)
    # --------------------------------------------------
    session.add_all([
        LossType(code="DRIP", name="Drip Loss", active=True, sort_order=1),
        LossType(code="TRIM", name="Trim Loss", active=True, sort_order=2),
    ])

    # --------------------------------------------------
    # PROCESS PROFILES
    # NOTE: breakdown_txn hardcodes process_profile_id=1
    # --------------------------------------------------
    breakdown_profile = ProcessProfile(
        name="Butchery Breakdown",
        allows_lot_mixing=False
    )
    sausage_profile = ProcessProfile(
        name="Sausage Mixing",
        allows_lot_mixing=True
    )
    session.add_all([breakdown_profile, sausage_profile])

    # --------------------------------------------------
    # SUPPLIERS + CUSTOMERS
    # --------------------------------------------------
    supplier = Supplier(name="Demo Abattoir")
    cust_restaurant = Customer(name="Restaurant A")
    cust_retail = Customer(name="Retail Customer")
    session.add_all([supplier, cust_restaurant, cust_retail])

    # --------------------------------------------------
    # ITEMS
    # --------------------------------------------------
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

    # --------------------------------------------------
    # RECEIVING – WHOLE BEEF
    # --------------------------------------------------
    recv = await create_lot_txn(
        session,
        ReceivingRequest(
            item_id=by_sku["BEEF-SIDE"].id,
            supplier_id=supplier.id,
            quantity_kg=180.000,
            to_location_id=raw.id,
            notes="Demo receiving – whole beef",
            received_at=now - timedelta(days=2),
        ),
    )
    input_lot_id = recv["lot_id"]

    # --------------------------------------------------
    # BREAKDOWN – FULL CONSUMPTION
    # --------------------------------------------------
    bd_req = BreakdownRequest(
        input_lot_id=input_lot_id,
        input_quantity_kg=180.000,
        outputs=[
            BreakdownOutput(by_sku["BEEF-CHUCK"].id, 55.0, wip.id),
            BreakdownOutput(by_sku["BEEF-ROUND"].id, 45.0, wip.id),
            BreakdownOutput(by_sku["BEEF-BRISKET"].id, 9.0, wip.id),
            BreakdownOutput(by_sku["BEEF-RIBEYE"].id, 12.0, wip.id),
            BreakdownOutput(by_sku["BEEF-STRIPLOIN"].id, 10.0, wip.id),
            BreakdownOutput(by_sku["BEEF-TENDERLOIN"].id, 4.0, wip.id),
            BreakdownOutput(by_sku["BEEF-SIRLOIN"].id, 11.0, wip.id),
            BreakdownOutput(by_sku["BEEF-SHORTRIB"].id, 10.0, wip.id),
            BreakdownOutput(by_sku["BEEF-TRIM-80CL"].id, 18.0, wip.id),
            BreakdownOutput(by_sku["BEEF-FAT"].id, 4.0, wip.id),
            BreakdownOutput(by_sku["BEEF-BONES"].id, 1.5, wip.id),
        ],
        losses=[
            BreakdownLossIn(loss_type="DRIP", quantity_kg=0.5, notes="Demo drip loss")
        ],
        notes="Demo whole-beef breakdown",
        performed_at=now - timedelta(days=1),
    )
    bd_resp = await breakdown_txn(bd_req, session, performed_by=1)

    out_ids = [o["id"] for o in bd_resp.outputs]
    out_lots: List[Lot] = (
        await session.execute(select(Lot).where(Lot.id.in_(out_ids)))
    ).scalars().all()

    def lot_by_sku(sku: str) -> Lot:
        iid = by_sku[sku].id
        return next(l for l in out_lots if l.item_id == iid)

    ribeye = lot_by_sku("BEEF-RIBEYE")
    trim = lot_by_sku("BEEF-TRIM-80CL")
    round_ = lot_by_sku("BEEF-ROUND")

    # --------------------------------------------------
    # RELEASE SOME LOTS
    # --------------------------------------------------
    for lot in [ribeye, trim, round_]:
        lot.state = "released"
        lot.ready_at = now - timedelta(days=1)
        lot.released_at = now - timedelta(days=1)
        lot.current_location_id = finished.id

    # --------------------------------------------------
    # AGING LOT
    # --------------------------------------------------
    aging_lot = next(l for l in out_lots if l not in {ribeye, trim, round_})
    aging_lot.state = "aging"
    aging_lot.aging_started_at = now - timedelta(days=1)
    aging_lot.ready_at = now + timedelta(days=10)
    aging_lot.current_location_id = aging.id

    await session.flush()

    # --------------------------------------------------
    # SECOND TRIM LOT (for mixing)
    # --------------------------------------------------
    recv2 = await create_lot_txn(
        session,
        ReceivingRequest(
            item_id=by_sku["BEEF-TRIM-80CL"].id,
            supplier_id=supplier.id,
            quantity_kg=30.0,
            to_location_id=finished.id,
            notes="Trim for sausage",
            received_at=now - timedelta(days=3),
        ),
    )
    trim2 = (
        await session.execute(select(Lot).where(Lot.id == recv2["lot_id"]))
    ).scalar_one()

    trim2.state = "released"
    trim2.ready_at = now - timedelta(days=2)
    trim2.released_at = now - timedelta(days=2)

    # --------------------------------------------------
    # MIXING – SAUSAGE
    # --------------------------------------------------
    mix_resp = await mix(
        MixRequest(
            process_profile_id=sausage_profile.id,
            inputs=[
                MixInput(trim.id, 10.0),
                MixInput(trim2.id, 10.0),
            ],
            output_item_id=by_sku["SAUSAGE"].id,
            output_location_id=finished.id,
            notes="Demo sausage batch",
            performed_at=now - timedelta(hours=12),
        ),
        session=session,
    )
    sausage_lot_id = mix_resp.output_lot_id

    # --------------------------------------------------
    # QA
    # --------------------------------------------------
    await create_qa_check(
        QACheckRequest(
            lot_id=ribeye.id,
            check_type="Visual",
            mode="full",
            passed=True,
            notes="QA pass",
            performed_at=now - timedelta(hours=8),
        ),
        session=session,
    )

    await create_qa_check(
        QACheckRequest(
            lot_id=round_.id,
            check_type="Temp",
            mode="full",
            passed=False,
            notes="QA fail",
            performed_at=now - timedelta(hours=7),
        ),
        session=session,
    )

    await create_qa_check(
        QACheckRequest(
            lot_id=sausage_lot_id,
            check_type="Metal Detect",
            mode="partial",
            pass_qty_kg=18.0,
            fail_qty_kg=2.0,
            notes="Partial split",
            performed_at=now - timedelta(hours=2),
        ),
        session=session,
    )

    # --------------------------------------------------
    # RESERVATION
    # --------------------------------------------------
    session.add(
        Reservation(
            lot_id=ribeye.id,
            customer_id=cust_restaurant.id,
            quantity_kg=5.0,
            reserved_at=now - timedelta(hours=3),
        )
    )

    # --------------------------------------------------
    # SALE
    # --------------------------------------------------
    sale = await create_sale_txn(
        SaleCreateRequest(
            customer_id=cust_retail.id,
            sold_at=now - timedelta(minutes=30),
            lines=[SaleLineIn(lot_id=ribeye.id, quantity_kg=3.0)],
            notes="Demo sale",
        ),
        session=session,
        performed_by=1,
    )

    # --------------------------------------------------
    # OFFLINE QUEUE
    # --------------------------------------------------
    await submit_queue(
        OfflineQueueSubmitRequest(
            client_id="demo-ipad-01",
            submitted_by=1,
            actions=[
                OfflineAction(
                    client_txn_id="offline-001",
                    action_type="receiving",
                    payload={
                        "item_id": by_sku["BEEF-SIDE"].id,
                        "supplier_id": supplier.id,
                        "quantity_kg": 25.0,
                        "to_location_id": raw.id,
                        "notes": "Offline receiving",
                    },
                ),
                OfflineAction(
                    client_txn_id="offline-002",
                    action_type="sale",
                    payload={
                        "customer_id": cust_restaurant.id,
                        "lines": [
                            {"lot_id": ribeye.id, "quantity_kg": 1.0}
                        ],
                        "notes": "Offline sale",
                    },
                ),
            ],
        ),
        session=session,
    )

    await session.commit()

    return {
        "ok": True,
        "message": "Full demo dataset seeded",
        "ids": {
            "input_lot_id": input_lot_id,
            "ribeye_lot_id": ribeye.id,
            "sausage_lot_id": sausage_lot_id,
            "sale_id": sale.sale_id,
        },
    }

