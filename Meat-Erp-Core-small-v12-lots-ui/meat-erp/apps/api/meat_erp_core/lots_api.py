from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, case
from sqlalchemy.ext.asyncio import AsyncSession

from meat_erp_core.db import get_session
from meat_erp_core.availability import available_kg, available_for_sale_kg, reserved_kg
from meat_erp_core.models import (
    Customer,
    InventoryMovement,
    Item,
    Location,
    Lot,
    LotEvent,
    ProductionInput,
    ProductionOrder,
    ProductionOutput,
    Reservation,
    Sale,
    SaleLine,
    Supplier,
)

router = APIRouter(prefix="/lots", tags=["lots"])


@router.get("")
async def list_lots(limit: int = 200, session: AsyncSession = Depends(get_session)):
    # Quantities:
    # - received_qty_kg: sum of movements with move_type == 'receiving'
    # - available_qty_kg: (sum of to_location_id != NULL) - (sum of from_location_id != NULL)
    received_sum = func.coalesce(
        func.sum(
            case((InventoryMovement.move_type == "receiving", InventoryMovement.quantity_kg), else_=0)
        ),
        0,
    ).label("received_qty_kg")

    in_sum = func.coalesce(
        func.sum(case((InventoryMovement.to_location_id.is_not(None), InventoryMovement.quantity_kg), else_=0)),
        0,
    ).label("in_qty_kg")

    out_sum = func.coalesce(
        func.sum(case((InventoryMovement.from_location_id.is_not(None), InventoryMovement.quantity_kg), else_=0)),
        0,
    ).label("out_qty_kg")

    reserved_subq = (
        select(func.coalesce(func.sum(Reservation.quantity_kg), 0))
        .where(Reservation.lot_id == Lot.id)
        .scalar_subquery()
    )

    available_expr = (in_sum - out_sum).label("available_qty_kg")
    reserved_expr = func.coalesce(reserved_subq, 0).label("reserved_qty_kg")
    sellable_expr = func.greatest(available_expr - reserved_expr, 0).label("sellable_qty_kg")

    rows = (
        await session.execute(
            select(Lot, Item, received_sum, available_expr, reserved_expr, sellable_expr)
            .join(Item, Item.id == Lot.item_id)
            .outerjoin(InventoryMovement, InventoryMovement.lot_id == Lot.id)
            .group_by(Lot.id, Item.id)
            .order_by(Lot.id.desc())
            .limit(limit)
        )
    ).all()

    return [
        {
            "id": lot.id,
            "lot_code": lot.lot_code,
            "state": lot.state,
            "item_id": item.id,
            "item_name": item.name,
            "received_at": lot.received_at,
            "aging_started_at": getattr(lot, "aging_started_at", None),
            "ready_at": getattr(lot, "ready_at", None),
            "released_at": getattr(lot, "released_at", None),
            "expires_at": getattr(lot, "expires_at", None),
            "current_location_id": getattr(lot, "current_location_id", None),
            "received_qty_kg": float(received_qty_kg),
            "available_qty_kg": float(available_qty_kg),
            "reserved_qty_kg": float(reserved_qty_kg),
            "sellable_qty_kg": float(sellable_qty_kg),
        }
        for (lot, item, received_qty_kg, available_qty_kg, reserved_qty_kg, sellable_qty_kg) in rows
    ]


@router.get("/{lot_id}")
async def get_lot_detail(lot_id: int, session: AsyncSession = Depends(get_session)):
    lot_row = (
        await session.execute(
            select(Lot, Item, Supplier, Location)
            .join(Item, Item.id == Lot.item_id)
            .outerjoin(Supplier, Supplier.id == Lot.supplier_id)
            .outerjoin(Location, Location.id == Lot.current_location_id)
            .where(Lot.id == lot_id)
        )
    ).first()

    if not lot_row:
        raise HTTPException(status_code=404, detail="Lot not found")

    lot, item, supplier, location = lot_row
    qty_available = await available_kg(session, lot_id)
    qty_reserved = await reserved_kg(session, lot_id)
    qty_sellable = await available_for_sale_kg(session, lot_id)

    received_qty = (
        await session.execute(
            select(
                func.coalesce(
                    func.sum(
                        case(
                            (InventoryMovement.move_type == "receiving", InventoryMovement.quantity_kg),
                            else_=0,
                        )
                    ),
                    0,
                )
            ).where(InventoryMovement.lot_id == lot_id)
        )
    ).scalar_one()

    # movements
    mv_rows = (
        await session.execute(
            select(InventoryMovement, Location)
            .outerjoin(Location, Location.id == InventoryMovement.from_location_id)
            .where(InventoryMovement.lot_id == lot_id)
            .order_by(InventoryMovement.moved_at.desc(), InventoryMovement.id.desc())
            .limit(500)
        )
    ).all()

    # We also want to_location names; do a second map lookup (fast for <=500)
    to_ids = [mv.to_location_id for (mv, _from_loc) in mv_rows if mv.to_location_id]
    to_locs = {}
    if to_ids:
        loc_rows = (
            await session.execute(select(Location).where(Location.id.in_(list(set(to_ids)))))
        ).scalars().all()
        to_locs = {l.id: l.name for l in loc_rows}

    movements = [
        {
            "id": mv.id,
            "move_type": mv.move_type,
            "quantity_kg": float(mv.quantity_kg),
            "moved_at": mv.moved_at,
            "from_location_id": mv.from_location_id,
            "from_location_name": (from_loc.name if from_loc else None),
            "to_location_id": mv.to_location_id,
            "to_location_name": (to_locs.get(mv.to_location_id) if mv.to_location_id else None),
        }
        for (mv, from_loc) in mv_rows
    ]

    # events
    ev_rows = (
        await session.execute(
            select(LotEvent)
            .where(LotEvent.lot_id == lot_id)
            .order_by(LotEvent.performed_at.desc(), LotEvent.id.desc())
            .limit(500)
        )
    ).scalars().all()
    events = [
        {
            "id": e.id,
            "event_type": e.event_type,
            "notes": e.reason,
            "performed_by": e.performed_by,
            "performed_at": e.performed_at,
        }
        for e in ev_rows
    ]

    # reservations
    res_rows = (
        await session.execute(
            select(Reservation, Customer)
            .join(Customer, Customer.id == Reservation.customer_id)
            .where(Reservation.lot_id == lot_id)
            .order_by(Reservation.reserved_at.desc(), Reservation.id.desc())
            .limit(200)
        )
    ).all()
    reservations = [
        {
            "id": r.id,
            "customer_id": c.id,
            "customer_name": c.name,
            "quantity_kg": float(r.quantity_kg),
            "reserved_at": r.reserved_at,
        }
        for (r, c) in res_rows
    ]

    # sales lines
    sl_rows = (
        await session.execute(
            select(SaleLine, Sale, Customer)
            .join(Sale, Sale.id == SaleLine.sale_id)
            .outerjoin(Customer, Customer.id == Sale.customer_id)
            .where(SaleLine.lot_id == lot_id)
            .order_by(Sale.sold_at.desc(), Sale.id.desc())
            .limit(200)
        )
    ).all()
    sales = [
        {
            "sale_id": s.id,
            "sold_at": s.sold_at,
            "customer_id": (c.id if c else None),
            "customer_name": (c.name if c else None),
            "quantity_kg": float(sl.quantity_kg),
        }
        for (sl, s, c) in sl_rows
    ]

    # genealogy (direct)
    as_input_rows = (
        await session.execute(
            select(ProductionInput, ProductionOrder)
            .join(ProductionOrder, ProductionOrder.id == ProductionInput.production_order_id)
            .where(ProductionInput.lot_id == lot_id)
            .order_by(ProductionOrder.started_at.desc().nullslast(), ProductionOrder.id.desc())
            .limit(50)
        )
    ).all()

    input_orders = []
    for (pi, po) in as_input_rows:
        outs = (
            await session.execute(
                select(ProductionOutput, Lot)
                .join(Lot, Lot.id == ProductionOutput.output_lot_id)
                .where(ProductionOutput.production_order_id == po.id)
            )
        ).all()
        input_orders.append(
            {
                "production_order_id": po.id,
                "process_type": po.process_type,
                "is_rework": po.is_rework,
                "started_at": po.started_at,
                "outputs": [
                    {
                        "lot_id": out_lot.id,
                        "lot_code": out_lot.lot_code,
                        "quantity_kg": float(po_out.quantity_kg),
                    }
                    for (po_out, out_lot) in outs
                ],
            }
        )

    as_output_rows = (
        await session.execute(
            select(ProductionOutput, ProductionOrder)
            .join(ProductionOrder, ProductionOrder.id == ProductionOutput.production_order_id)
            .where(ProductionOutput.output_lot_id == lot_id)
            .order_by(ProductionOrder.started_at.desc().nullslast(), ProductionOrder.id.desc())
            .limit(50)
        )
    ).all()

    output_orders = []
    for (po_out, po) in as_output_rows:
        ins = (
            await session.execute(
                select(ProductionInput, Lot)
                .join(Lot, Lot.id == ProductionInput.lot_id)
                .where(ProductionInput.production_order_id == po.id)
            )
        ).all()
        output_orders.append(
            {
                "production_order_id": po.id,
                "process_type": po.process_type,
                "is_rework": po.is_rework,
                "started_at": po.started_at,
                "inputs": [
                    {
                        "lot_id": in_lot.id,
                        "lot_code": in_lot.lot_code,
                        "quantity_kg": float(po_in.quantity_kg),
                    }
                    for (po_in, in_lot) in ins
                ],
            }
        )

    return {
        "id": lot.id,
        "lot_code": lot.lot_code,
        "state": lot.state,
        "item_id": item.id,
        "item_name": item.name,
        "supplier_id": (supplier.id if supplier else None),
        "supplier_name": (supplier.name if supplier else None),
        "location_id": (location.id if location else None),
        "location_name": (location.name if location else None),
        "received_at": lot.received_at,
        "aging_started_at": getattr(lot, "aging_started_at", None),
        "ready_at": getattr(lot, "ready_at", None),
        "released_at": getattr(lot, "released_at", None),
        "expires_at": getattr(lot, "expires_at", None),
        "quantities": {
            "received_qty_kg": float(received_qty),
            "available_qty_kg": float(qty_available),
            "reserved_qty_kg": float(qty_reserved),
            "sellable_qty_kg": float(qty_sellable),
        },
        "movements": movements,
        "events": events,
        "reservations": reservations,
        "sales": sales,
        "genealogy": {
            "as_input": input_orders,
            "as_output": output_orders,
        },
    }
