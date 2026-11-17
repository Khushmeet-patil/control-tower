"""What-if scenarios (Phase 10): plan changes, see their effect, then apply them all at once, or not at all.

- Scenario: a named set of proposed changes, private to its owner (organisation-wide roles can read
  every scenario). Status: draft → applied, or discarded. Nothing in a draft changes live data.
- ScenarioChange: one proposed change. Only the change is stored, never a copy of the data:
    kind "item"               change fields of a work item (`target_id`): dates, status, priority, owner, unit, weight
    kind "assignment"         change an assignment (`target_id`): person, allocation %, dates, role
    kind "new_assignment"     add someone to a work item (`work_item_id`)
    kind "remove_assignment"  take an assignment (`target_id`) away
  `base_version` is the record's version when the change was proposed. Applying checks it again, so a
  scenario never overwrites something that was changed in the meantime.

Applying runs every change through the normal services (WorkItemService, AssignmentService), as the
person applying, with their current rights, in one transaction and under one correlation id: the audit
log shows the whole scenario as one action. If any change fails, nothing is applied.
"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.models import BaseModel

STATUSES = ("draft", "applied", "discarded")
CHANGE_KINDS = ("item", "assignment", "new_assignment", "remove_assignment")
ITEM_FIELDS = ("planned_start", "planned_end", "status_id", "priority_id", "accountable_id", "unit_id", "weight")
ASSIGNMENT_FIELDS = ("person_id", "allocation_pct", "start_date", "end_date", "role_id")


class Scenario(BaseModel):
    __tablename__ = "scenarios"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", index=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    applied_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    applied_correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    owner = relationship("User", foreign_keys=[owner_id], lazy="joined")


class ScenarioChange(BaseModel):
    __tablename__ = "scenario_changes"

    scenario_id: Mapped[int] = mapped_column(ForeignKey("scenarios.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    work_item_id: Mapped[int | None] = mapped_column(ForeignKey("work_items.id"), nullable=True, index=True)
    changes: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    base_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
