from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from meat_erp_core.db import get_session
from meat_erp_core.models import LossType

router = APIRouter(prefix="/admin/loss-types", tags=["admin"])

class LossTypeCreate(BaseModel):
    code: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=2, max_length=128)
    sort_order: int = 0
    active: bool = True

class LossTypeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=128)
    sort_order: int | None = None
    active: bool | None = None

@router.get("")
async def admin_list(session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(
        select(LossType).order_by(LossType.active.desc(), LossType.sort_order.asc(), LossType.name.asc())
    )).scalars().all()
    return [{"id": r.id, "code": r.code, "name": r.name, "active": r.active, "sort_order": r.sort_order} for r in rows]

@router.post("")
async def admin_create(req: LossTypeCreate, session: AsyncSession = Depends(get_session)):
    exists = (await session.execute(select(LossType).where(LossType.code == req.code))).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=409, detail="code already exists")

    row = LossType(code=req.code.strip(), name=req.name.strip(), active=req.active, sort_order=req.sort_order)
    session.add(row)
    await session.commit()
    return {"id": row.id, "code": row.code, "name": row.name, "active": row.active, "sort_order": row.sort_order}

@router.patch("/{code}")
async def admin_update(code: str, req: LossTypeUpdate, session: AsyncSession = Depends(get_session)):
    row = (await session.execute(select(LossType).where(LossType.code == code))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="not found")

    values = {}
    if req.name is not None: values["name"] = req.name.strip()
    if req.sort_order is not None: values["sort_order"] = req.sort_order
    if req.active is not None: values["active"] = req.active

    if not values:
        return {"ok": True}

    await session.execute(update(LossType).where(LossType.code == code).values(**values))
    await session.commit()
    return {"ok": True}
