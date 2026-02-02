from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

BACKWARD_SQL = text("""
WITH RECURSIVE backward(lot_id, source_lot_id) AS (
    SELECT
        po.output_lot_id AS lot_id,
        pi.lot_id        AS source_lot_id
    FROM production_outputs po
    JOIN production_inputs pi
      ON pi.production_order_id = po.production_order_id
    WHERE po.output_lot_id = :lot_id

    UNION ALL

    SELECT
        b.lot_id,
        pi.lot_id
    FROM backward b
    JOIN production_outputs po
      ON po.output_lot_id = b.source_lot_id
    JOIN production_inputs pi
      ON pi.production_order_id = po.production_order_id
)
SELECT DISTINCT source_lot_id FROM backward;
""")

FORWARD_SQL = text("""
WITH RECURSIVE forward(lot_id, derived_lot_id) AS (
    SELECT
        pi.lot_id        AS lot_id,
        po.output_lot_id AS derived_lot_id
    FROM production_inputs pi
    JOIN production_outputs po
      ON po.production_order_id = pi.production_order_id
    WHERE pi.lot_id = :lot_id

    UNION ALL

    SELECT
        f.derived_lot_id,
        po.output_lot_id
    FROM forward f
    JOIN production_inputs pi
      ON pi.lot_id = f.derived_lot_id
    JOIN production_outputs po
      ON po.production_order_id = pi.production_order_id
)
SELECT DISTINCT derived_lot_id FROM forward;
""")

CUSTOMERS_SQL = text("""
SELECT DISTINCT
    c.id,
    c.name
FROM sale_lines sl
JOIN sales s ON s.id = sl.sale_id
JOIN customers c ON c.id = s.customer_id
WHERE sl.lot_id = ANY(:lot_ids);
""")

async def backward_trace(session: AsyncSession, lot_id: int) -> list[int]:
    res = await session.execute(BACKWARD_SQL, {"lot_id": lot_id})
    return [r[0] for r in res.fetchall()]

async def forward_trace(session: AsyncSession, lot_id: int) -> list[int]:
    res = await session.execute(FORWARD_SQL, {"lot_id": lot_id})
    return [r[0] for r in res.fetchall()]

async def affected_customers(session: AsyncSession, lot_ids: list[int]) -> list[dict]:
    if not lot_ids:
        return []
    res = await session.execute(CUSTOMERS_SQL, {"lot_ids": lot_ids})
    return [{"id": r[0], "name": r[1]} for r in res.fetchall()]
