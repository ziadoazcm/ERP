"""breakdown losses (type + kg)

Revision ID: 0005_breakdown_losses
Revises: 0004_offline_queue
Create Date: 2026-01-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_breakdown_losses"
down_revision = "0004_offline_queue"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "breakdown_losses",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("production_order_id", sa.Integer(), sa.ForeignKey("production_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("loss_type", sa.String(length=64), nullable=False),
        sa.Column("quantity_kg", sa.Numeric(12, 3), nullable=False),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("quantity_kg > 0", name="ck_breakdown_loss_qty_positive"),
    )
    op.create_index("ix_breakdown_losses_po", "breakdown_losses", ["production_order_id"])
    op.create_index("ix_breakdown_losses_type", "breakdown_losses", ["loss_type"])

def downgrade():
    op.drop_index("ix_breakdown_losses_type", table_name="breakdown_losses")
    op.drop_index("ix_breakdown_losses_po", table_name="breakdown_losses")
    op.drop_table("breakdown_losses")
