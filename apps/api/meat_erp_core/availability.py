from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from meat_erp_core.models import InventoryMovement, Reservation, Lot


async def reserved_kg(session: AsyncSession, lot_id: int) -> float:
    """
    Total reserved kg for a lot (not yet sold/consumed).
    """
    stmt = select(func.coalesce(func.sum(Reservation.quantity_kg), 0)).where(
        Reservation.lot_id == lot_id
    )
    res = await session.execute(stmt)
    return float(res.scalar_one())


async def available_kg(session: AsyncSession, lot_id: int) -> float:
    """
    Available kg for a lot = net inventory movements - reserved kg.

    SQLAlchemy 2.x compatible: uses sqlalchemy.case (NOT func.case).
    Supports breakdown loss move types like "breakdown_loss:DRIP" (prefix match).
    Assumes InventoryMovement.quantity_kg stored as positive numbers.
    """

    # IN movements add inventory to the lot
    in_case = case(
        (
            InventoryMovement.move_type.in_(
                [
                    "receiving",
                    "breakdown_output",
                    "mix_output",
                    "adjustment_in",
                ]
            ),
            InventoryMovement.quantity_kg,
        ),
        else_=0,
    )

    # OUT movements subtract inventory from the lot
    out_case = case(
        (
            InventoryMovement.move_type.in_(
                [
                    "sale",
                    "breakdown_input",
                    "mix_input",
                    "adjustment_out",
                ]
            ),
            InventoryMovement.quantity_kg,
        ),
        else_=0,
    )

    # Breakdown losses subtract inventory from the INPUT lot
    # move_type stored like "breakdown_loss:{CODE}"
    loss_case = case(
        (
            InventoryMovement.move_type.like("breakdown_loss:%"),
            InventoryMovement.quantity_kg,
        ),
        else_=0,
    )

    inv_stmt = select(
        func.coalesce(func.sum(in_case - out_case - loss_case), 0)
    ).where(InventoryMovement.lot_id == lot_id)

    inv_res = await session.execute(inv_stmt)
    on_hand = float(inv_res.scalar_one())

    rsv = await reserved_kg(session, lot_id)

    # Never return negative available
    avail = on_hand - rsv
    if avail < 0:
        avail = 0.0

    return avail


async def available_for_sale_kg(session: AsyncSession, lot_id: int) -> float:
    """
    Sale-eligible available quantity for a lot.

    This is a safe default implementation:
    - Lot must be in a sale-safe state (released).
    - If ready_at is set, selling before ready_at returns 0.
    - Returns available_kg (already accounts for reservations).
    """
    lot = (
        await session.execute(select(Lot).where(Lot.id == lot_id))
    ).scalar_one_or_none()

    if not lot:
        return 0.0

    # Enforce typical sale-safe rules
    if getattr(lot, "state", None) != "released":
        return 0.0

    ready_at = getattr(lot, "ready_at", None)
    if ready_at:
        now = datetime.now(timezone.utc)
        if now < ready_at:
            return 0.0

    return await available_kg(session, lot_id)
