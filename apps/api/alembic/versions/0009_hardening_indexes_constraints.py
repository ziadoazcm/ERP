"""hardening: indexes, constraints, idempotency

Revision ID: 0009_hardening_indexes_constraints
Revises: 0008_qa_partial_split
Create Date: 2026-01-30
"""

from alembic import op
import sqlalchemy as sa

revision = "0009_hardening_indexes_constraints"
down_revision = "0008_qa_partial_split"
branch_labels = None
depends_on = None


def upgrade():
    # Notes field on lot_events must be optional.
    op.alter_column(
        "lot_events",
        "reason",
        existing_type=sa.String(length=500),
        nullable=True,
    )

    # Offline queue idempotency (client_id + client_txn_id)
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'uq_offline_client_txn'
            ) THEN
                ALTER TABLE offline_queue
                ADD CONSTRAINT uq_offline_client_txn
                UNIQUE (client_id, client_txn_id);
            END IF;
        END;
        $$;
        """
    )

    # Enforce positive qty on breakdown_losses at the DB layer (idempotent).
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_breakdown_loss_qty_positive'
            ) THEN
                ALTER TABLE breakdown_losses
                ADD CONSTRAINT ck_breakdown_loss_qty_positive
                CHECK (quantity_kg > 0);
            END IF;
        END;
        $$;
        """
    )

    # Helpful indexes (use IF NOT EXISTS for safe re-runs).
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_inventory_movements_lot_moved_at "
        "ON inventory_movements (lot_id, moved_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_inventory_movements_lot_move_type "
        "ON inventory_movements (lot_id, move_type)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_lot_events_lot_performed_at "
        "ON lot_events (lot_id, performed_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_offline_queue_status_created_at "
        "ON offline_queue (status, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_reservations_lot_customer "
        "ON reservations (lot_id, customer_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_sale_lines_sale_lot "
        "ON sale_lines (sale_id, lot_id)"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_sale_lines_sale_lot")
    op.execute("DROP INDEX IF EXISTS ix_reservations_lot_customer")
    op.execute("DROP INDEX IF EXISTS ix_offline_queue_status_created_at")
    op.execute("DROP INDEX IF EXISTS ix_lot_events_lot_performed_at")
    op.execute("DROP INDEX IF EXISTS ix_inventory_movements_lot_move_type")
    op.execute("DROP INDEX IF EXISTS ix_inventory_movements_lot_moved_at")

    # Drop CHECK constraint if it exists.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_breakdown_loss_qty_positive'
            ) THEN
                ALTER TABLE breakdown_losses
                DROP CONSTRAINT ck_breakdown_loss_qty_positive;
            END IF;
        END;
        $$;
        """
    )

    # Drop UNIQUE constraint if it exists.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'uq_offline_client_txn'
            ) THEN
                ALTER TABLE offline_queue
                DROP CONSTRAINT uq_offline_client_txn;
            END IF;
        END;
        $$;
        """
    )

    op.alter_column(
        "lot_events",
        "reason",
        existing_type=sa.String(length=500),
        nullable=False,
    )

