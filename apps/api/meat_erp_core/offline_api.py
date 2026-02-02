from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from meat_erp_core.db import get_session
from meat_erp_core.models import OfflineQueue, OfflineConflict

from meat_erp_core.receiving import create_lot_txn as receiving_create_lot, ReceivingCreateLotRequest
from meat_erp_core.breakdown import breakdown_txn as breakdown_handler, BreakdownRequest
from meat_erp_core.sales_api import create_sale_txn as sales_create_sale, SaleCreateRequest

router = APIRouter(prefix="/offline", tags=["offline"])

AllowedAction = Literal["receiving", "breakdown", "sale"]

class OfflineAction(BaseModel):
    client_txn_id: str = Field(min_length=3, max_length=200)
    action_type: AllowedAction
    payload: Dict[str, Any]

class OfflineQueueSubmitRequest(BaseModel):
    client_id: str = Field(min_length=1, max_length=200)
    submitted_by: int
    actions: List[OfflineAction] = Field(min_length=1)

class OfflineQueueSubmitResult(BaseModel):
    client_txn_id: str
    status: str
    offline_queue_id: Optional[int] = None

class OfflineQueueSubmitResponse(BaseModel):
    results: List[OfflineQueueSubmitResult]

@router.post("/queue", response_model=OfflineQueueSubmitResponse)
async def submit_queue(req: OfflineQueueSubmitRequest, session: AsyncSession = Depends(get_session)):
    results: List[OfflineQueueSubmitResult] = []
    for a in req.actions:
        row = OfflineQueue(
            client_id=req.client_id,
            client_txn_id=a.client_txn_id,
            action_type=a.action_type,
            payload=a.payload,
            submitted_by=req.submitted_by,
            status="queued",
            created_at=datetime.now(timezone.utc),
        )
        session.add(row)
        try:
            await session.flush()
            results.append(OfflineQueueSubmitResult(client_txn_id=a.client_txn_id, status="queued", offline_queue_id=row.id))
        except IntegrityError:
            await session.rollback()
            results.append(OfflineQueueSubmitResult(client_txn_id=a.client_txn_id, status="duplicate", offline_queue_id=None))
            session = session

    await session.commit()
    return OfflineQueueSubmitResponse(results=results)

class ApplyRequest(BaseModel):
    client_id: str
    limit: int = 200

class ApplyResult(BaseModel):
    offline_queue_id: int
    client_txn_id: str
    status: str
    server_refs: Dict[str, Any] | None = None
    reason: str | None = None

class ApplyResponse(BaseModel):
    applied: int
    conflicts: int
    rejected: int
    results: List[ApplyResult]

def _make_conflict(session: AsyncSession, oq: OfflineQueue, conflict_type: str, details: dict, reason: str):
    return OfflineConflict(
        offline_queue_id=oq.id,
        conflict_type=conflict_type,
        details=details,
        created_at=datetime.now(timezone.utc),
    ), reason

async def _apply_one(session: AsyncSession, oq: OfflineQueue) -> tuple[str, dict | None, str | None]:
    try:
        if oq.action_type == "receiving":
            req = ReceivingCreateLotRequest(**oq.payload)
            resp = await receiving_create_lot(req, session)
            return "applied", {"lot_id": resp.lot_id}, None

        if oq.action_type == "breakdown":
            req = BreakdownRequest(**oq.payload)
            resp = await breakdown_handler(req, session)
            return "applied", {"production_order_id": resp.production_order_id}, None

        if oq.action_type == "sale":
            req = SaleCreateRequest(**oq.payload)
            resp = await sales_create_sale(req, session)
            return "applied", {"sale_id": resp.sale_id}, None

        return "rejected", None, "Unknown action_type"
    except HTTPException as e:
        msg = str(e.detail)

        conflict_signals = [
            "insufficient available",
            "not released",
            "not ready",
            "quarantined",
            "Weight mismatch",
            "lot_code already exists",
            "Invalid",
        ]
        conflict = any(s.lower() in msg.lower() for s in conflict_signals)

        if conflict:
            return "conflict", None, msg
        return "rejected", None, msg
    except Exception as e:
        return "conflict", None, str(e)

@router.post("/sync/apply", response_model=ApplyResponse)
async def apply_queue(req: ApplyRequest, session: AsyncSession = Depends(get_session)):
    """
    Apply queued offline actions grouped by client_txn_id as an atomic transaction.
    - If any action in a client_txn_id group fails, the whole group is rolled back.
    - A conflict record is written for every action in the group with shared txn context.
    """
    q = (await session.execute(
        select(OfflineQueue)
        .where(OfflineQueue.client_id == req.client_id)
        .where(OfflineQueue.status == "queued")
        .order_by(OfflineQueue.created_at.asc(), OfflineQueue.id.asc())
        .limit(req.limit)
    )).scalars().all()

    # group by client_txn_id while preserving order
    groups: list[list[OfflineQueue]] = []
    cur: list[OfflineQueue] = []
    cur_id: str | None = None
    for row in q:
        if cur_id is None or row.client_txn_id == cur_id:
            cur.append(row)
            cur_id = row.client_txn_id
        else:
            groups.append(cur)
            cur = [row]
            cur_id = row.client_txn_id
    if cur:
        groups.append(cur)

    applied = conflicts = rejected = 0
    results: List[ApplyResult] = []

    for group in groups:
        txn_id = group[0].client_txn_id

        # Try to apply all actions in a SAVEPOINT so we can roll back this group cleanly.
        refs_by_oq: dict[int, dict] = {}
        failed: tuple[str, str] | None = None  # (status, reason)

        try:
            async with session.begin_nested():
                for oq in group:
                    status, refs, reason = await _apply_one(session, oq)
                    if status != "applied":
                        failed = (status, reason or "unknown")
                        # raise to trigger rollback of the SAVEPOINT
                        raise HTTPException(status_code=400, detail=reason or "offline txn failed")
                    if refs:
                        refs_by_oq[oq.id] = refs

                # If we get here, the whole group is valid. Mark applied inside the same transaction.
                now = datetime.now(timezone.utc)
                for oq in group:
                    await session.execute(
                        update(OfflineQueue)
                        .where(OfflineQueue.id == oq.id)
                        .values(status="applied", applied_at=now, conflict_reason=None)
                    )
                    results.append(ApplyResult(
                        offline_queue_id=oq.id,
                        client_txn_id=oq.client_txn_id,
                        status="applied",
                        server_refs=refs_by_oq.get(oq.id),
                    ))
                    applied += 1

        except HTTPException as e:
            # Group failed: record txn-level conflicts and mark statuses.
            reason = (failed[1] if failed else str(e.detail)) if hasattr(e, "detail") else str(e)
            now = datetime.now(timezone.utc)

            # Decide whether this is a "conflict" or "rejected" outcome for the group.
            # We treat safety/inventory validation errors as conflicts (needs supervisor review).
            conflict_signals = [
                "insufficient available",
                "insufficient sellable",
                "not released",
                "not ready",
                "quarantined",
                "Weight mismatch",
                "already used",
                "must consume full available",
                "Invalid",
            ]
            is_conflict = any(s.lower() in reason.lower() for s in conflict_signals)

            # Write one conflict per queue row, with shared txn context.
            for oq in group:
                if is_conflict:
                    await session.execute(
                        update(OfflineQueue)
                        .where(OfflineQueue.id == oq.id)
                        .values(status="conflict", conflict_reason=f"txn:{txn_id} | {reason}")
                    )
                    c = OfflineConflict(
                        offline_queue_id=oq.id,
                        conflict_type="txn_conflict",
                        details={
                            "client_txn_id": txn_id,
                            "reason": reason,
                            "failed_action_type": group[0].action_type if group else None,
                            "actions_in_txn": [
                                {"offline_queue_id": x.id, "action_type": x.action_type, "payload": x.payload}
                                for x in group
                            ],
                        },
                        created_at=now,
                    )
                    session.add(c)
                    results.append(ApplyResult(
                        offline_queue_id=oq.id,
                        client_txn_id=oq.client_txn_id,
                        status="conflict",
                        reason=reason,
                    ))
                    conflicts += 1
                else:
                    await session.execute(
                        update(OfflineQueue)
                        .where(OfflineQueue.id == oq.id)
                        .values(status="rejected", conflict_reason=f"txn:{txn_id} | {reason}")
                    )
                    results.append(ApplyResult(
                        offline_queue_id=oq.id,
                        client_txn_id=oq.client_txn_id,
                        status="rejected",
                        reason=reason,
                    ))
                    rejected += 1

        except Exception as e:
            # Unexpected error: treat as conflict and include exception string.
            reason = str(e)
            now = datetime.now(timezone.utc)
            for oq in group:
                await session.execute(
                    update(OfflineQueue)
                    .where(OfflineQueue.id == oq.id)
                    .values(status="conflict", conflict_reason=f"txn:{txn_id} | {reason}")
                )
                c = OfflineConflict(
                    offline_queue_id=oq.id,
                    conflict_type="txn_exception",
                    details={
                        "client_txn_id": txn_id,
                        "reason": reason,
                        "actions_in_txn": [
                            {"offline_queue_id": x.id, "action_type": x.action_type, "payload": x.payload}
                            for x in group
                        ],
                    },
                    created_at=now,
                )
                session.add(c)
                results.append(ApplyResult(
                    offline_queue_id=oq.id,
                    client_txn_id=oq.client_txn_id,
                    status="conflict",
                    reason=reason,
                ))
                conflicts += 1

        await session.commit()

    return ApplyResponse(applied=applied, conflicts=conflicts, rejected=rejected, results=results)

@router.get("/conflicts")
async def list_conflicts(status: str = "conflict", session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(
        select(OfflineQueue)
        .where(OfflineQueue.status == status)
        .order_by(OfflineQueue.created_at.desc())
        .limit(200)
    )).scalars().all()

    return [{
        "id": r.id,
        "client_id": r.client_id,
        "client_txn_id": r.client_txn_id,
        "action_type": r.action_type,
        "status": r.status,
        "created_at": r.created_at,
        "conflict_reason": r.conflict_reason,
        "payload": r.payload,
    } for r in rows]

class ResolveRequest(BaseModel):
    resolution: Literal["rejected"]
    resolved_by: int
    reason: str = Field(min_length=2, max_length=500)

@router.post("/conflicts/{offline_queue_id}/resolve")
async def resolve_conflict(offline_queue_id: int, req: ResolveRequest, session: AsyncSession = Depends(get_session)):
    oq = (await session.execute(select(OfflineQueue).where(OfflineQueue.id == offline_queue_id))).scalar_one_or_none()
    if not oq:
        raise HTTPException(status_code=404, detail="offline_queue_id not found")
    if oq.status != "conflict":
        raise HTTPException(status_code=400, detail="Only conflict items can be resolved")

    await session.execute(
        update(OfflineQueue)
        .where(OfflineQueue.id == offline_queue_id)
        .values(status=req.resolution, conflict_reason=f"Resolved: {req.reason}")
    )

    await session.execute(
        update(OfflineConflict)
        .where(OfflineConflict.offline_queue_id == offline_queue_id)
        .values(
            resolved_by=req.resolved_by,
            resolved_at=datetime.now(timezone.utc),
            resolution=req.resolution,
        )
    )

    await session.commit()
    return {"ok": True, "offline_queue_id": offline_queue_id, "resolution": req.resolution}
