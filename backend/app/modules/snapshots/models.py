"""Snapshots: the figures of every work item as they were at a moment, stored, never linked to live data.

- Snapshot: one capture (weekly or on demand). Its figures never change. Only its label and notes,
  its approval and whether it is the baseline can change, each through an audited command. An approved
  snapshot can be used by a published review pack (see app.modules.presentations), and is kept.
- SnapshotItem: one work item's figures in a snapshot, with everything the Portfolio filters need
  (lookups, owners, unit path at the time, health, progress, open/overdue as of the snapshot date), so
  dashboards can be recalculated from a snapshot exactly as they were (see frozen.py).

SnapshotItem rows are append-only: written once, in the same transaction as the audited Snapshot.
"""
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import BaseModel
from app.extensions import db

KINDS = ("weekly", "on_demand")
STATUSES = ("draft", "approved")


class Snapshot(BaseModel):
    __tablename__ = "snapshots"
    # One weekly snapshot per ISO week ("2026-W46"); on-demand snapshots have no period.
    __table_args__ = (UniqueConstraint("tenant_id", "period", name="uq_snapshots_tenant_period"),)

    label: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="on_demand")
    period: Mapped[str | None] = mapped_column(String(10), nullable=True)
    as_of: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    taken_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    taken_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_baseline: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class SnapshotItem(db.Model):
    __tablename__ = "snapshot_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("snapshots.id"), nullable=False, index=True)
    work_item_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    parent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    item_type_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    priority_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    category_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action_type_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    severity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unit_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unit_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    unit_path: Mapped[list | None] = mapped_column(JSON, nullable=True)  # the unit and the units above it, then
    function_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    accountable_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    accountable_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    responsible_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    assignee_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    planned_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    weight: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    health: Mapped[str | None] = mapped_column(String(20), nullable=True)
    health_value_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    health_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_overdue: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approval_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    custom_fields: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class SnapshotPerson(db.Model):
    """One person's capacity figures in a snapshot (Phase 10), so the Team capacity widget can show
    a snapshot too. Append-only, written with the snapshot. Who a viewer sees follows their access now."""

    __tablename__ = "snapshot_people"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("snapshots.id"), nullable=False, index=True)
    person_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    job_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    unit_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unit_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    unit_path: Mapped[list | None] = mapped_column(JSON, nullable=True)
    function_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    skill_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    capacity_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    available_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    usable_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    load_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    free_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    allocated_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    buffer_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
