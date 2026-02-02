"""lot code counters (atomic)

Revision ID: 0007_lot_code_counters
Revises: 0006_loss_types_master
Create Date: 2026-01-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_lot_code_counters"
down_revision = "0006_loss_types_master"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "lot_code_counters",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("code_date", sa.Date(), nullable=False),
        sa.Column("prefix", sa.String(length=16), nullable=False),
        sa.Column("last_seq", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.create_unique_constraint("uq_lot_code_counters_date_prefix", "lot_code_counters", ["code_date", "prefix"])

def downgrade():
    op.drop_constraint("uq_lot_code_counters_date_prefix", "lot_code_counters", type_="unique")
    op.drop_table("lot_code_counters")
