"""Work items: everything the platform tracks (programmes, projects, milestones, tasks, actions…).

- WorkItem: one tree for all work. `item_type_id`, `status_id`, `priority_id`, `category_id`,
  `action_type_id` and `severity_id` are lookup value ids, so labels and colours are settings.
  `unit_id` is the team or unit the work is assigned to; it decides who can see and manage it.
  `accountable_id` is the ONE accountable owner. Responsible owners (one or more) are in
  WorkItemResponsible. Children inherit owners unless deliberately overridden (with a reason).
- WorkItemDependency: "this item cannot finish before that one".
- Assignment: a person working on an item, with a functional role, allocation % and dates.
  This replaces the prototype's "EMP-001:40" allocation text.
"""
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.models import BaseModel
from app.core.tree import make_closure_model
from app.extensions import db


class WorkItem(BaseModel):
    __tablename__ = "work_items"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_work_items_tenant_code"),)

    code: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    item_type_id: Mapped[int] = mapped_column(ForeignKey("lookup_values.id"), nullable=False, index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("work_items.id"), nullable=True, index=True)
    status_id: Mapped[int | None] = mapped_column(ForeignKey("lookup_values.id"), nullable=True, index=True)
    priority_id: Mapped[int | None] = mapped_column(ForeignKey("lookup_values.id"), nullable=True, index=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("lookup_values.id"), nullable=True, index=True)
    # Actions only (decision, approval, blocker…): what kind of action and how severe.
    action_type_id: Mapped[int | None] = mapped_column(ForeignKey("lookup_values.id"), nullable=True)
    severity_id: Mapped[int | None] = mapped_column(ForeignKey("lookup_values.id"), nullable=True)
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("org_units.id"), nullable=True, index=True)
    function_id: Mapped[int | None] = mapped_column(ForeignKey("functions.id"), nullable=True, index=True)
    accountable_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    # True when the accountable owner was set deliberately instead of inherited from the parent.
    owner_overridden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    planned_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_end: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    actual_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Used only while an item has no children; otherwise progress is calculated.
    progress_manual: Mapped[int | None] = mapped_column(Integer, nullable=True)
    objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    risks: Mapped[str | None] = mapped_column(Text, nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Share of the parent's progress this item carries, relative to its siblings.
    weight: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    # Approval of the completed item: None (no approval needed), pending, approved or rejected.
    # Set only by the approvals engine (app.modules.workflows.engine).
    approval_status: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    custom_fields: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Adoption pipeline (the prototype's Dev → Test → Accepted → Trained → Rollout → Adopted): the
    # "adoption_stage" lookup value ids this work has reached, plus evidence that users adopted it.
    adoption_stage_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    adoption_evidence: Mapped[str | None] = mapped_column(String(500), nullable=True)

    accountable = relationship("User", foreign_keys=[accountable_id], lazy="joined")
    unit = relationship("OrgUnit", foreign_keys=[unit_id], lazy="joined")
    function = relationship("Function", foreign_keys=[function_id], lazy="joined")


WorkItemClosure = make_closure_model("WorkItemClosure", "work_item_closure", "work_items")


class WorkItemResponsible(db.Model):
    __tablename__ = "work_item_responsibles"

    work_item_id: Mapped[int] = mapped_column(ForeignKey("work_items.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True, index=True)


class WorkItemDependency(db.Model):
    __tablename__ = "work_item_dependencies"

    work_item_id: Mapped[int] = mapped_column(ForeignKey("work_items.id"), primary_key=True)
    depends_on_id: Mapped[int] = mapped_column(ForeignKey("work_items.id"), primary_key=True, index=True)


class Assignment(BaseModel):
    __tablename__ = "assignments"

    work_item_id: Mapped[int] = mapped_column(ForeignKey("work_items.id"), nullable=False, index=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    role_id: Mapped[int | None] = mapped_column(ForeignKey("lookup_values.id"), nullable=True)
    allocation_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    duties: Mapped[str | None] = mapped_column(Text, nullable=True)

    person = relationship("User", foreign_keys=[person_id], lazy="joined")
