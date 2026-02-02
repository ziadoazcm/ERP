from __future__ import annotations

from datetime import datetime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey,
    Integer, JSON, Numeric, String, Text, text
)
from sqlalchemy import UniqueConstraint

class Base(DeclarativeBase):
    pass

class Item(Base):
    __tablename__ = "items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    is_meat: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

class Supplier(Base):
    __tablename__ = "suppliers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)

class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)

class LossType(Base):
    __tablename__ = "loss_types"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class Location(Base):
    __tablename__ = "locations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)

class Lot(Base):
    __tablename__ = "lots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lot_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True)
    current_location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)

    state: Mapped[str] = mapped_column(String(32), index=True)

    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    aging_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "state in ('received','aging','released','sold','disposed','quarantined')",
            name="ck_lot_state",
        ),
    )

class InventoryMovement(Base):
    __tablename__ = "inventory_movements"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lot_id: Mapped[int] = mapped_column(ForeignKey("lots.id"), index=True)

    from_location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    to_location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)

    quantity_kg: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)
    moved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    move_type: Mapped[str] = mapped_column(String(32), index=True)

    __table_args__ = (
        CheckConstraint("quantity_kg > 0", name="ck_move_qty_positive"),
    )

class LotEvent(Base):
    __tablename__ = "lot_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lot_id: Mapped[int] = mapped_column(ForeignKey("lots.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    # We treat this as user-entered "notes" in the UI/API. It must be allowed to be null.
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    performed_by: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    performed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # set by database server_default - no Python default!
    txid: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("txid_current()"))

class ProcessProfile(Base):
    __tablename__ = "process_profiles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    allows_lot_mixing: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    default_aging_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    default_aging_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

class ProductionOrder(Base):
    __tablename__ = "production_orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    process_profile_id: Mapped[int] = mapped_column(ForeignKey("process_profiles.id"), index=True)
    process_type: Mapped[str] = mapped_column(String(32), index=True)
    is_rework: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class ProductionInput(Base):
    __tablename__ = "production_inputs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    production_order_id: Mapped[int] = mapped_column(ForeignKey("production_orders.id"), index=True)
    lot_id: Mapped[int] = mapped_column(ForeignKey("lots.id"), index=True)
    quantity_kg: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)

    __table_args__ = (CheckConstraint("quantity_kg > 0", name="ck_prod_input_qty_positive"),)

class ProductionOutput(Base):
    __tablename__ = "production_outputs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    production_order_id: Mapped[int] = mapped_column(ForeignKey("production_orders.id"), index=True)
    output_lot_id: Mapped[int] = mapped_column(ForeignKey("lots.id"), index=True)
    quantity_kg: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)

    __table_args__ = (CheckConstraint("quantity_kg > 0", name="ck_prod_output_qty_positive"),)

class QACheck(Base):
    __tablename__ = "qa_checks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lot_id: Mapped[int] = mapped_column(ForeignKey("lots.id"), index=True)
    check_type: Mapped[str] = mapped_column(String(64), nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    performed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="full")
    pass_qty_kg: Mapped[float | None] = mapped_column(Numeric(12, 3), nullable=True)
    fail_qty_kg: Mapped[float | None] = mapped_column(Numeric(12, 3), nullable=True)
    pass_lot_id: Mapped[int | None] = mapped_column(ForeignKey("lots.id"), nullable=True)
    fail_lot_id: Mapped[int | None] = mapped_column(ForeignKey("lots.id"), nullable=True)

class EnvLog(Base):
    __tablename__ = "env_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), index=True)
    log_type: Mapped[str] = mapped_column(String(64), nullable=False)
    temperature_c: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    humidity_pct: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class Reservation(Base):
    __tablename__ = "reservations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lot_id: Mapped[int] = mapped_column(ForeignKey("lots.id"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    quantity_kg: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)
    reserved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (CheckConstraint("quantity_kg > 0", name="ck_res_qty_positive"),)

class Sale(Base):
    __tablename__ = "sales"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    sold_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class SaleLine(Base):
    __tablename__ = "sale_lines"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id"), index=True)
    lot_id: Mapped[int] = mapped_column(ForeignKey("lots.id"), index=True)
    quantity_kg: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)

    __table_args__ = (CheckConstraint("quantity_kg > 0", name="ck_sale_qty_positive"),)

class OfflineQueue(Base):
    __tablename__ = "offline_queue"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    client_id: Mapped[str] = mapped_column(String, nullable=False)
    client_txn_id: Mapped[str] = mapped_column(String, nullable=False)
    action_type: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    submitted_by: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="queued")
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    conflict_reason: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        UniqueConstraint("client_id", "client_txn_id", name="uq_offline_client_txn"),
    )

class OfflineConflict(Base):
    __tablename__ = "offline_conflicts"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    offline_queue_id: Mapped[int] = mapped_column(ForeignKey("offline_queue.id", ondelete="CASCADE"))
    conflict_type: Mapped[str] = mapped_column(String, nullable=False)
    details: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    resolved_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution: Mapped[str | None] = mapped_column(String, nullable=True)

class BreakdownLoss(Base):
    __tablename__ = "breakdown_losses"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    production_order_id: Mapped[int] = mapped_column(ForeignKey("production_orders.id", ondelete="CASCADE"), index=True)
    loss_type: Mapped[str] = mapped_column(String(64), index=True)
    quantity_kg: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (CheckConstraint("quantity_kg > 0", name="ck_breakdown_loss_qty_positive"),)
