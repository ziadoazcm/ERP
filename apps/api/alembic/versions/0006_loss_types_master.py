"""loss types master

Revision ID: 0006_loss_types_master
Revises: 0005_breakdown_losses
Create Date: 2026-01-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_loss_types_master"
down_revision = "0005_breakdown_losses"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "loss_types",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=64), nullable=False, unique=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_loss_types_active_sort", "loss_types", ["active", "sort_order", "name"])

    op.execute("""
        INSERT INTO loss_types(code, name, active, sort_order) VALUES
        ('trim', 'Trim', true, 10),
        ('bone', 'Bone', true, 20),
        ('purge', 'Purge', true, 30),
        ('spoilage', 'Spoilage', true, 40),
        ('damage', 'Damage', true, 50),
        ('other', 'Other', true, 90)
        ON CONFLICT (code) DO NOTHING;
    """)

def downgrade():
    op.drop_index("ix_loss_types_active_sort", table_name="loss_types")
    op.drop_table("loss_types")
