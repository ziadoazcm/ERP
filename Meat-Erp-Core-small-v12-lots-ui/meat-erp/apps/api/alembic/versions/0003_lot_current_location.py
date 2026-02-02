"""add current_location_id to lots

Revision ID: 0003_lot_current_location
Revises: 0002_lot_audit_trigger
Create Date: 2026-01-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_lot_current_location"
down_revision = "0002_lot_audit_trigger"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("lots", sa.Column("current_location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=True))
    op.create_index("ix_lots_current_location", "lots", ["current_location_id"])

def downgrade():
    op.drop_index("ix_lots_current_location", table_name="lots")
    op.drop_column("lots", "current_location_id")
