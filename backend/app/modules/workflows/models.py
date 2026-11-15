"""Approvals: configurable chains (settings) and the requests that run through them.

Settings (edited as a draft, used once published, like lookups):
- ApprovalChain: which work it applies to (item types and/or a unit and everything below it).
  The most specific active chain wins: unit-specific before organisation-wide, typed before untyped,
  then the lowest order. Work with no chain needs no approval.
- ApprovalStep: one approval in a chain, in order. Who approves (`approver_kind`), what happens
  when nobody fills that role (`when_missing`: skip or block), and what the approver must provide
  (checklist, evidence on the item, a comment).

Runtime:
- ApprovalRequest: one run of a chain for one item, started when the item is marked Done. The chain's
  steps are copied into `steps`, so editing a chain never changes requests already in flight.
- ApprovalDecision: each approval, rejection or automatic skip, with the comment and ticked checks.
"""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.models import BaseModel

APPROVER_KINDS = {
    "functional_lead": "Functional lead",
    "accountable": "Accountable owner",
    "unit_head": "Head of the item's unit",
    "role": "Anyone with a role",
    "person": "A named person",
}
WHEN_MISSING = {"skip": "Skip the step", "block": "Wait until someone fills the role"}
REQUEST_STATUSES = ("pending", "approved", "rejected", "cancelled")


class ApprovalChain(BaseModel):
    __tablename__ = "approval_chains"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_approval_chains_tenant_code"),)

    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Item type lookup value ids; empty = every type.
    item_type_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Applies to work in this unit and the units below it; empty = the whole organisation.
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("org_units.id"), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ApprovalStep(BaseModel):
    __tablename__ = "approval_steps"

    chain_id: Mapped[int] = mapped_column(ForeignKey("approval_chains.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    approver_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    approver_role_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id"), nullable=True)
    approver_person_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    when_missing: Mapped[str] = mapped_column(String(10), nullable=False, default="skip")
    checklist: Mapped[list | None] = mapped_column(JSON, nullable=True)
    require_evidence: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    require_comment: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ApprovalRequest(BaseModel):
    __tablename__ = "approval_requests"

    work_item_id: Mapped[int] = mapped_column(ForeignKey("work_items.id"), nullable=False, index=True)
    chain_id: Mapped[int | None] = mapped_column(ForeignKey("approval_chains.id"), nullable=True)
    chain_name: Mapped[str] = mapped_column(String(100), nullable=False)
    steps: Mapped[list] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    current_step: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Who must act now: a person, or anyone holding a role. Both empty while blocked.
    current_approver_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    current_role_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id"), nullable=True, index=True)
    waiting_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    work_item = relationship("WorkItem", lazy="joined")
    submitted_by = relationship("User", foreign_keys=[submitted_by_id], lazy="joined")
    current_approver = relationship("User", foreign_keys=[current_approver_id], lazy="joined")


class ApprovalDecision(BaseModel):
    __tablename__ = "approval_decisions"

    request_id: Mapped[int] = mapped_column(ForeignKey("approval_requests.id"), nullable=False, index=True)
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    step_name: Mapped[str] = mapped_column(String(100), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)  # approved, rejected, skipped
    approver_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    checklist: Mapped[list | None] = mapped_column(JSON, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    approver = relationship("User", foreign_keys=[approver_id], lazy="joined")
