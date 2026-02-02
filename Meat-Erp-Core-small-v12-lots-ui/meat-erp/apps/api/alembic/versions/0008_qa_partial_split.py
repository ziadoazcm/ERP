"""qa partial split fields

Revision ID: 0008_qa_partial_split
Revises: 0007_lot_code_counters
Create Date: 2026-01-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_qa_partial_split"
down_revision = "0007_lot_code_counters"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("qa_checks", sa.Column("pass_qty_kg", sa.Numeric(12, 3), nullable=True))
    op.add_column("qa_checks", sa.Column("fail_qty_kg", sa.Numeric(12, 3), nullable=True))
    op.add_column("qa_checks", sa.Column("pass_lot_id", sa.Integer(), sa.ForeignKey("lots.id"), nullable=True))
    op.add_column("qa_checks", sa.Column("fail_lot_id", sa.Integer(), sa.ForeignKey("lots.id"), nullable=True))
    op.add_column("qa_checks", sa.Column("mode", sa.String(length=16), nullable=False, server_default=sa.text("'full'")))

    op.create_index("ix_qa_checks_pass_lot", "qa_checks", ["pass_lot_id"])
    op.create_index("ix_qa_checks_fail_lot", "qa_checks", ["fail_lot_id"])

def downgrade():
    op.drop_index("ix_qa_checks_fail_lot", table_name="qa_checks")
    op.drop_index("ix_qa_checks_pass_lot", table_name="qa_checks")
    op.drop_column("qa_checks", "mode")
    op.drop_column("qa_checks", "fail_lot_id")
    op.drop_column("qa_checks", "pass_lot_id")
    op.drop_column("qa_checks", "fail_qty_kg")
    op.drop_column("qa_checks", "pass_qty_kg")
