from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from meat_erp_core.models import InventoryMovement, Reservation

async def available_kg(session: AsyncSession, lot_id: int) -> float:
    result = await session.execute(
        select(
            func.coalesce(
                func.sum(
                    func.case(
                        (InventoryMovement.to_location_id.isnot(None), InventoryMovement.quantity_kg),
                        else_=0
                    )
                ) - func.sum(
                    func.case(
                        (InventoryMovement.from_location_id.isnot(None), InventoryMovement.quantity_kg),
                        else_=0
                    )
                ),
                0
            )
        ).where(InventoryMovement.lot_id == lot_id)
    )
    return float(result.scalar() or 0)


async def reserved_kg(session: AsyncSession, lot_id: int) -> float:
    """Soft allocations for restaurant/wholesale reservations."""
    result = await session.execute(
        select(func.coalesce(func.sum(Reservation.quantity_kg), 0)).where(Reservation.lot_id == lot_id)
    )
    return float(result.scalar() or 0)


async def available_for_sale_kg(session: AsyncSession, lot_id: int) -> float:
    """Available quantity after subtracting reservations."""
    avail = await available_kg(session, lot_id)
    resv = await reserved_kg(session, lot_id)
    x = avail - resv
    return float(x) if x > 0 else 0.0
