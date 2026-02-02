from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from meat_erp_core.db import get_session
from meat_erp_core.models import Item, Supplier, Location, LossType, ProcessProfile, Customer

router = APIRouter(prefix="/lookups", tags=["lookups"])

@router.get("/items")
async def list_items(session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(Item).order_by(Item.name))).scalars().all()
    return [{"id": r.id, "sku": r.sku, "name": r.name, "is_meat": r.is_meat} for r in rows]

@router.get("/suppliers")
async def list_suppliers(session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(Supplier).order_by(Supplier.name))).scalars().all()
    return [{"id": r.id, "name": r.name} for r in rows]


@router.get("/customers")
async def list_customers(session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(Customer).order_by(Customer.name))).scalars().all()
    return [{"id": r.id, "name": r.name} for r in rows]

@router.get("/locations")
async def list_locations(session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(Location).order_by(Location.name))).scalars().all()
    return [{"id": r.id, "name": r.name, "kind": r.kind} for r in rows]

@router.get("/loss-types")
async def list_loss_types(session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(
        select(LossType)
        .where(LossType.active == True)  # noqa
        .order_by(LossType.sort_order.asc(), LossType.name.asc())
    )).scalars().all()
    return [{"code": r.code, "name": r.name} for r in rows]


@router.get("/process-profiles")
async def list_process_profiles(allows_lot_mixing: bool | None = None, session: AsyncSession = Depends(get_session)):
    q = select(ProcessProfile).order_by(ProcessProfile.name.asc())
    if allows_lot_mixing is not None:
        q = q.where(ProcessProfile.allows_lot_mixing == allows_lot_mixing)  # noqa
    rows = (await session.execute(q)).scalars().all()
    return [{"id": r.id, "name": r.name, "allows_lot_mixing": r.allows_lot_mixing} for r in rows]
