"""enforce lot audit on state changes

Revision ID: 0002_lot_audit_trigger
Revises: 0001_meat_erp_core
Create Date: 2026-01-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_lot_audit_trigger"
down_revision = "0001_meat_erp_core"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column(
        "lot_events",
        sa.Column("txid", sa.BigInteger(), nullable=False, server_default=sa.text("txid_current()")),
    )
    op.create_index("ix_lot_events_lot_txid", "lot_events", ["lot_id", "txid"])

    op.execute(
        """
        CREATE OR REPLACE FUNCTION enforce_lot_state_audit()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          current_tx BIGINT := txid_current();
          has_event BOOLEAN;
        BEGIN
          IF (NEW.state IS DISTINCT FROM OLD.state)
             OR (NEW.released_at IS DISTINCT FROM OLD.released_at)
             OR (NEW.aging_started_at IS DISTINCT FROM OLD.aging_started_at)
             OR (NEW.ready_at IS DISTINCT FROM OLD.ready_at)
             OR (NEW.expires_at IS DISTINCT FROM OLD.expires_at) THEN

            SELECT EXISTS (
              SELECT 1
              FROM lot_events e
              WHERE e.lot_id = NEW.id
                AND e.txid = current_tx
              LIMIT 1
            ) INTO has_event;

            IF NOT has_event THEN
              RAISE EXCEPTION
                'Lot % change requires lot_event in same transaction (no silent state changes).', NEW.id
                USING ERRCODE = '23514';
            END IF;
          END IF;

          RETURN NEW;
        END;
        $$;
        """
    )

    op.execute("DROP TRIGGER IF EXISTS trg_enforce_lot_state_audit ON lots;")
    op.execute(
        """
        CREATE TRIGGER trg_enforce_lot_state_audit
        AFTER UPDATE OF state, released_at, aging_started_at, ready_at, expires_at
        ON lots
        FOR EACH ROW
        EXECUTE FUNCTION enforce_lot_state_audit();
        """
    )

def downgrade():
    op.execute("DROP TRIGGER IF EXISTS trg_enforce_lot_state_audit ON lots;")
    op.execute("DROP FUNCTION IF EXISTS enforce_lot_state_audit();")
    op.drop_index("ix_lot_events_lot_txid", table_name="lot_events")
    op.drop_column("lot_events", "txid")
