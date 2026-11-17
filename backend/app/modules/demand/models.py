"""Demand intake (the prototype's "Demand Intake" screen): requests for new work, assessed against
free team capacity and then accepted (which creates a draft initiative), rejected, deferred or sent
back for clarification.

`urgency_id`, `priority_id` and `decision_id` are lookup value ids ("urgency", "priority",
"demand_decision" lists). `effort_pct` is the effort in capacity points: 1 point = 1% of one person's
working week, the same unit as allocation %, so it can be compared with free capacity directly.
"""
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.models import BaseModel


class DemandRequest(BaseModel):
    __tablename__ = "demand_requests"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_demand_requests_tenant_code"),)

    code: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    sponsor: Mapped[str | None] = mapped_column(String(200), nullable=True)
    business_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    urgency_id: Mapped[int | None] = mapped_column(ForeignKey("lookup_values.id"), nullable=True)
    priority_id: Mapped[int | None] = mapped_column(ForeignKey("lookup_values.id"), nullable=True)
    effort_pct: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requested_on: Mapped[date] = mapped_column(Date, nullable=False)
    needed_by: Mapped[date | None] = mapped_column(Date, nullable=True)
    dependencies: Mapped[str | None] = mapped_column(Text, nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The unit asked to deliver it: its managers decide, and its people's free capacity is assessed.
    unit_id: Mapped[int] = mapped_column(ForeignKey("org_units.id"), nullable=False, index=True)
    decision_id: Mapped[int | None] = mapped_column(ForeignKey("lookup_values.id"), nullable=True, index=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # The draft initiative created on acceptance.
    work_item_id: Mapped[int | None] = mapped_column(ForeignKey("work_items.id"), nullable=True)

    requester = relationship("User", foreign_keys=[requester_id], lazy="joined")
    decided_by = relationship("User", foreign_keys=[decided_by_id], lazy="joined")
    unit = relationship("OrgUnit", foreign_keys=[unit_id], lazy="joined")
