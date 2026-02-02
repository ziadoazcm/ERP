"""offline queue (policy b)

Revision ID: 0004_offline_queue
Revises: 0003_lot_current_location
Create Date: 2026-01-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_offline_queue"
down_revision = "0003_lot_current_location"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "offline_queue",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("client_id", sa.Text(), nullable=False),
        sa.Column("client_txn_id", sa.Text(), nullable=False),
        sa.Column("action_type", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("submitted_by", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'queued'")),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("conflict_reason", sa.Text(), nullable=True),
    )
    op.create_index("ix_offline_status_created", "offline_queue", ["status", "created_at"])
    op.create_unique_constraint("uq_offline_client_txn", "offline_queue", ["client_id", "client_txn_id"])

    op.create_table(
        "offline_conflicts",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("offline_queue_id", sa.BigInteger(), sa.ForeignKey("offline_queue.id", ondelete="CASCADE"), nullable=False),
        sa.Column("conflict_type", sa.Text(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("resolved_by", sa.Integer(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
    )
    op.create_index("ix_offline_conflicts_queue", "offline_conflicts", ["offline_queue_id"])

def downgrade():
    op.drop_index("ix_offline_conflicts_queue", table_name="offline_conflicts")
    op.drop_table("offline_conflicts")

    op.drop_constraint("uq_offline_client_txn", "offline_queue", type_="unique")
    op.drop_index("ix_offline_status_created", table_name="offline_queue")
    op.drop_table("offline_queue")
