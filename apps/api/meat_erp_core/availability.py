from __future__ import annotations

from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from meat_erp_core.models import InventoryMovement


async def available_kg(session: AsyncSession, lot_id: int) -> float:
    """
    Compute AVAILABLE quantity (kg) for a lot from inventory_movements.

    IMPORTANT:
    - This implementation is SQLAlchemy 2.x compatible.
    - It supports breakdown loss move types like: "breakdown_loss:DRIP" (prefix match).
    """

    # IN movements add inventory
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

    # OUT movements subtract inventory
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

    # Breakdown losses are recorded as move_type="breakdown_loss:{CODE}"
    loss_case = case(
        (
            InventoryMovement.move_type.like("breakdown_loss:%"),
            InventoryMovement.quantity_kg,
        ),
        else_=0,
    )

    stmt = (
        select(
            func.coalesce(
                func.sum(in_case - out_case - loss_case),
                0,
            )
        )
        .where(InventoryMovement.lot_id == lot_id)
    )

    res = await session.execute(stmt)
    return float(res.scalar_one())
