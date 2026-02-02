from datetime import datetime, timezone
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, condecimal

Kg = condecimal(gt=0, max_digits=12, decimal_places=3)
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from meat_erp_core.db import get_session
from meat_erp_core.models import Lot, QACheck, LotEvent, ProductionOrder, ProductionInput, ProductionOutput, InventoryMovement
from meat_erp_core.availability import available_kg
from meat_erp_core.lot_codes import next_lot_code

router = APIRouter(prefix="/qa", tags=["qa"])

class QACheckRequest(BaseModel):
    lot_id: int
    check_type: str = Field(min_length=2, max_length=64)

    # full mode
    passed: bool | None = None

    # partial mode
    mode: str = Field(default="full")  # "full" | "partial"
    pass_qty_kg: Kg | None = None
    fail_qty_kg: Kg | None = None

    notes: str | None = None
    # Performed_by is determined from login (JWT). Keep optional for backwards compatibility.
    performed_by: int | None = None
    performed_at: datetime | None = None

class QACheckResponse(BaseModel):
    qa_check_id: int
    quarantined: bool
    lot_event_id: int | None = None

@router.post("/checks", response_model=QACheckResponse)
async def create_qa_check(req: QACheckRequest, session: AsyncSession = Depends(get_session)):
    # Lock lot to prevent concurrent consumption (sale/breakdown/qa split).
    lot = (await session.execute(
        select(Lot).where(Lot.id == req.lot_id).with_for_update()
    )).scalar_one_or_none()
    if not lot:
        raise HTTPException(status_code=400, detail="Invalid lot_id")

    performed_by = req.performed_by or 1  # TODO: current_user.id

    performed_at = req.performed_at or datetime.now(timezone.utc)

    mode = req.mode.lower().strip()
    if mode not in ("full", "partial"):
        raise HTTPException(status_code=400, detail="mode must be 'full' or 'partial'")

    # ---------- FULL MODE (existing behavior) ----------
    if mode == "full":
        if req.passed is None:
            raise HTTPException(status_code=400, detail="passed is required for full mode")

        qa = QACheck(
            lot_id=req.lot_id,
            check_type=req.check_type,
            passed=req.passed,
            notes=req.notes,
            performed_at=performed_at,
            mode="full",
        )
        session.add(qa)
        await session.flush()

        lot_event_id = None
        quarantined = False

        if not req.passed:
            if lot.state != "quarantined":
                ev = LotEvent(
                    lot_id=req.lot_id,
                    event_type="quarantined",
                    reason=f"QA fail: {req.check_type}",
                    performed_by=performed_by,
                    performed_at=performed_at,
                )
                session.add(ev)
                await session.flush()
                lot_event_id = ev.id

                await session.execute(update(Lot).where(Lot.id == req.lot_id).values(state="quarantined"))

            quarantined = True

        await session.commit()
        return QACheckResponse(qa_check_id=qa.id, quarantined=quarantined, lot_event_id=lot_event_id)

    # ---------- PARTIAL MODE (split into pass + fail lots) ----------
    pass_qty = float(req.pass_qty_kg or 0)
    fail_qty = float(req.fail_qty_kg or 0)
    if pass_qty <= 0 and fail_qty <= 0:
        raise HTTPException(status_code=400, detail="Partial mode requires pass_qty_kg and/or fail_qty_kg")

    avail = await available_kg(session, req.lot_id)
    total = pass_qty + fail_qty
    if abs(total - avail) > 0.001:
        raise HTTPException(
            status_code=400,
            detail=f"Partial QA must split full available qty. available={avail:.3f} pass+fail={total:.3f}",
        )

    qa = QACheck(
        lot_id=req.lot_id,
        check_type=req.check_type,
        passed=(fail_qty <= 0),
        notes=req.notes,
        performed_at=performed_at,
        mode="partial",
        pass_qty_kg=req.pass_qty_kg,
        fail_qty_kg=req.fail_qty_kg,
    )
    session.add(qa)
    await session.flush()

    po = ProductionOrder(
        # Keep a concrete profile id to avoid null FK issues.
        process_profile_id=1,
        process_type="qa_split",
        is_rework=False,
        started_at=performed_at,
        completed_at=performed_at,
    )
    session.add(po)
    await session.flush()

    session.add(ProductionInput(production_order_id=po.id, lot_id=req.lot_id, quantity_kg=total))

    ev_root = LotEvent(
        lot_id=req.lot_id,
        event_type="qa_split",
        reason=req.notes or f"QA partial split: {req.check_type}",
        performed_by=performed_by,
        performed_at=performed_at,
    )
    session.add(ev_root)
    await session.flush()

    # Consume from current location so availability drops to 0 for the original lot.
    mv_in = InventoryMovement(
        lot_id=req.lot_id,
        from_location_id=getattr(lot, "current_location_id", None),
        to_location_id=None,
        quantity_kg=total,
        moved_at=performed_at,
        move_type="qa_split_input",
    )
    session.add(mv_in)
    await session.flush()

    pass_lot_id = None
    fail_lot_id = None
    event_ids = [ev_root.id]

    def copy_state_fields(src: Lot) -> dict:
        return dict(
            state=src.state,
            received_at=src.received_at,
            aging_started_at=getattr(src, "aging_started_at", None),
            ready_at=getattr(src, "ready_at", None),
            released_at=getattr(src, "released_at", None),
            expires_at=getattr(src, "expires_at", None),
            current_location_id=getattr(src, "current_location_id", None),
        )

    if pass_qty > 0:
        code = await next_lot_code(session, "QA", performed_at)
        pass_lot = Lot(
            lot_code=code,
            item_id=lot.item_id,
            supplier_id=getattr(lot, "supplier_id", None),
            **copy_state_fields(lot),
        )
        session.add(pass_lot)
        await session.flush()
        pass_lot_id = pass_lot.id

        session.add(ProductionOutput(production_order_id=po.id, output_lot_id=pass_lot.id, quantity_kg=pass_qty))

        ev_pass = LotEvent(
            lot_id=pass_lot.id,
            event_type="qa_pass_output",
            reason=req.notes or req.check_type,
            performed_by=performed_by,
            performed_at=performed_at,
        )
        session.add(ev_pass)
        await session.flush()
        event_ids.append(ev_pass.id)

        mv_pass = InventoryMovement(
            lot_id=pass_lot.id,
            from_location_id=None,
            to_location_id=getattr(lot, "current_location_id", None),
            quantity_kg=pass_qty,
            moved_at=performed_at,
            move_type="qa_pass_output",
        )
        session.add(mv_pass)
        await session.flush()

        qa.pass_lot_id = pass_lot.id

    if fail_qty > 0:
        code = await next_lot_code(session, "QF", performed_at)
        fail_lot = Lot(
            lot_code=code,
            item_id=lot.item_id,
            supplier_id=getattr(lot, "supplier_id", None),
            **copy_state_fields(lot),
        )
        fail_lot.state = "quarantined"
        session.add(fail_lot)
        await session.flush()
        fail_lot_id = fail_lot.id

        session.add(ProductionOutput(production_order_id=po.id, output_lot_id=fail_lot.id, quantity_kg=fail_qty))

        ev_fail = LotEvent(
            lot_id=fail_lot.id,
            event_type="qa_fail_output",
            reason=req.notes or req.check_type,
            performed_by=performed_by,
            performed_at=performed_at,
        )
        session.add(ev_fail)
        await session.flush()
        event_ids.append(ev_fail.id)

        mv_fail = InventoryMovement(
            lot_id=fail_lot.id,
            from_location_id=None,
            to_location_id=getattr(lot, "current_location_id", None),
            quantity_kg=fail_qty,
            moved_at=performed_at,
            move_type="qa_fail_output",
        )
        session.add(mv_fail)
        await session.flush()

        qa.fail_lot_id = fail_lot.id

    ev_dispose = LotEvent(
        lot_id=req.lot_id,
        event_type="disposed",
        reason="QA partial split consumed lot",
        performed_by=performed_by,
        performed_at=performed_at,
    )
    session.add(ev_dispose)
    await session.flush()
    event_ids.append(ev_dispose.id)

    await session.execute(update(Lot).where(Lot.id == req.lot_id).values(state="disposed"))

    await session.commit()

    quarantined = fail_qty > 0
    return QACheckResponse(
        qa_check_id=qa.id,
        quarantined=quarantined,
        lot_event_id=ev_root.id,
    )
