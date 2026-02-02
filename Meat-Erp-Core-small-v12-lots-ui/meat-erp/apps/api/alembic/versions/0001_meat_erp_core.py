"""meat erp core tables

Revision ID: 0001_meat_erp_core
Revises:
Create Date: 2026-01-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_meat_erp_core"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("is_meat", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_index("ix_items_sku", "items", ["sku"], unique=True)

    op.create_table(
        "suppliers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
    )
    op.create_index("ix_suppliers_name", "suppliers", ["name"], unique=True)

    op.create_table(
        "customers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
    )
    op.create_index("ix_customers_name", "customers", ["name"], unique=True)

    op.create_table(
        "locations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
    )
    op.create_index("ix_locations_name", "locations", ["name"], unique=True)

    op.create_table(
        "lots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lot_code", sa.String(length=64), nullable=False),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id"), nullable=True),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("aging_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "state in ('received','aging','released','sold','disposed','quarantined')",
            name="ck_lot_state",
        ),
    )
    op.create_index("ix_lots_lot_code", "lots", ["lot_code"], unique=True)
    op.create_index("ix_lots_item_id", "lots", ["item_id"])
    op.create_index("ix_lots_state", "lots", ["state"])

    op.create_table(
        "inventory_movements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lot_id", sa.Integer(), sa.ForeignKey("lots.id"), nullable=False),
        sa.Column("from_location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=True),
        sa.Column("to_location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=True),
        sa.Column("quantity_kg", sa.Numeric(12, 3), nullable=False),
        sa.Column("moved_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("move_type", sa.String(length=32), nullable=False),
        sa.CheckConstraint("quantity_kg > 0", name="ck_move_qty_positive"),
    )
    op.create_index("ix_moves_lot_id", "inventory_movements", ["lot_id"])
    op.create_index("ix_moves_type", "inventory_movements", ["move_type"])

    op.create_table(
        "lot_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lot_id", sa.Integer(), sa.ForeignKey("lots.id"), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("performed_by", sa.Integer(), nullable=False),
        sa.Column("performed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_events_lot_id", "lot_events", ["lot_id"])
    op.create_index("ix_events_type", "lot_events", ["event_type"])
    op.create_index("ix_events_performed_by", "lot_events", ["performed_by"])

    op.create_table(
        "process_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("allows_lot_mixing", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("default_aging_mode", sa.String(length=32), nullable=True),
        sa.Column("default_aging_days", sa.Integer(), nullable=True),
    )
    op.create_index("ix_profiles_name", "process_profiles", ["name"], unique=True)

    op.create_table(
        "production_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("process_profile_id", sa.Integer(), sa.ForeignKey("process_profiles.id"), nullable=False),
        sa.Column("process_type", sa.String(length=32), nullable=False),
        sa.Column("is_rework", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_orders_profile", "production_orders", ["process_profile_id"])
    op.create_index("ix_orders_type", "production_orders", ["process_type"])

    op.create_table(
        "production_inputs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("production_order_id", sa.Integer(), sa.ForeignKey("production_orders.id"), nullable=False),
        sa.Column("lot_id", sa.Integer(), sa.ForeignKey("lots.id"), nullable=False),
        sa.Column("quantity_kg", sa.Numeric(12, 3), nullable=False),
    )
    op.create_index("ix_inputs_order", "production_inputs", ["production_order_id"])
    op.create_index("ix_inputs_lot", "production_inputs", ["lot_id"])

    op.create_table(
        "production_outputs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("production_order_id", sa.Integer(), sa.ForeignKey("production_orders.id"), nullable=False),
        sa.Column("output_lot_id", sa.Integer(), sa.ForeignKey("lots.id"), nullable=False),
        sa.Column("quantity_kg", sa.Numeric(12, 3), nullable=False),
    )
    op.create_index("ix_outputs_order", "production_outputs", ["production_order_id"])
    op.create_index("ix_outputs_lot", "production_outputs", ["output_lot_id"])

    op.create_table(
        "qa_checks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lot_id", sa.Integer(), sa.ForeignKey("lots.id"), nullable=False),
        sa.Column("check_type", sa.String(length=64), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("performed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_qa_lot", "qa_checks", ["lot_id"])

    op.create_table(
        "env_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("log_type", sa.String(length=64), nullable=False),
        sa.Column("temperature_c", sa.Numeric(6, 2), nullable=True),
        sa.Column("humidity_pct", sa.Numeric(6, 2), nullable=True),
        sa.Column("logged_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_env_location", "env_logs", ["location_id"])

    op.create_table(
        "reservations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lot_id", sa.Integer(), sa.ForeignKey("lots.id"), nullable=False),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("quantity_kg", sa.Numeric(12, 3), nullable=False),
        sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("quantity_kg > 0", name="ck_res_qty_positive"),
    )
    op.create_index("ix_res_lot", "reservations", ["lot_id"])
    op.create_index("ix_res_customer", "reservations", ["customer_id"])

    op.create_table(
        "sales",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("sold_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_sales_customer", "sales", ["customer_id"])

    op.create_table(
        "sale_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sale_id", sa.Integer(), sa.ForeignKey("sales.id"), nullable=False),
        sa.Column("lot_id", sa.Integer(), sa.ForeignKey("lots.id"), nullable=False),
        sa.Column("quantity_kg", sa.Numeric(12, 3), nullable=False),
        sa.CheckConstraint("quantity_kg > 0", name="ck_sale_qty_positive"),
    )
    op.create_index("ix_sale_lines_sale", "sale_lines", ["sale_id"])
    op.create_index("ix_sale_lines_lot", "sale_lines", ["lot_id"])

def downgrade():
    op.drop_index("ix_sale_lines_lot", table_name="sale_lines")
    op.drop_index("ix_sale_lines_sale", table_name="sale_lines")
    op.drop_table("sale_lines")

    op.drop_index("ix_sales_customer", table_name="sales")
    op.drop_table("sales")

    op.drop_index("ix_res_customer", table_name="reservations")
    op.drop_index("ix_res_lot", table_name="reservations")
    op.drop_table("reservations")

    op.drop_index("ix_env_location", table_name="env_logs")
    op.drop_table("env_logs")

    op.drop_index("ix_qa_lot", table_name="qa_checks")
    op.drop_table("qa_checks")

    op.drop_index("ix_outputs_lot", table_name="production_outputs")
    op.drop_index("ix_outputs_order", table_name="production_outputs")
    op.drop_table("production_outputs")

    op.drop_index("ix_inputs_lot", table_name="production_inputs")
    op.drop_index("ix_inputs_order", table_name="production_inputs")
    op.drop_table("production_inputs")

    op.drop_index("ix_orders_type", table_name="production_orders")
    op.drop_index("ix_orders_profile", table_name="production_orders")
    op.drop_table("production_orders")

    op.drop_index("ix_profiles_name", table_name="process_profiles")
    op.drop_table("process_profiles")

    op.drop_index("ix_events_performed_by", table_name="lot_events")
    op.drop_index("ix_events_type", table_name="lot_events")
    op.drop_index("ix_events_lot_id", table_name="lot_events")
    op.drop_table("lot_events")

    op.drop_index("ix_moves_type", table_name="inventory_movements")
    op.drop_index("ix_moves_lot_id", table_name="inventory_movements")
    op.drop_table("inventory_movements")

    op.drop_index("ix_lots_state", table_name="lots")
    op.drop_index("ix_lots_item_id", table_name="lots")
    op.drop_index("ix_lots_lot_code", table_name="lots")
    op.drop_table("lots")

    op.drop_index("ix_locations_name", table_name="locations")
    op.drop_table("locations")

    op.drop_index("ix_customers_name", table_name="customers")
    op.drop_table("customers")

    op.drop_index("ix_suppliers_name", table_name="suppliers")
    op.drop_table("suppliers")

    op.drop_index("ix_items_sku", table_name="items")
    op.drop_table("items")
