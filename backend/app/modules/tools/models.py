"""Tools registry (the Tool Centre): links to tools deployed elsewhere, and built-in tools that save to
the work item they are used on.

Tool kinds (behaviour is code, so the kinds are fixed; everything else is data):
- link       an external tool at `url`, opened in a new tab. Opening checks access and is audited.
- form       a set of work item fields (core or custom) filled in together, e.g. a risk review.
             Saving goes through WorkItemService, so item permissions and the audit log apply.
- checklist  a readiness assessment: items to tick and a pass mark. Answers are kept per work item
             in ToolResponse.

Who may use a tool (an empty list means "no limit" on that dimension):
- `role_ids`      people holding one of these roles
- `work_item_ids` these items and everything below them
- `unit_ids`      these units and everything below them (work assigned there, and people in them)
- `item_type_ids` only shown on items of these types
A tool with neither items nor units applies organisation-wide.

`context_params` passes project data to an external link tool: name → value pairs added to the address
when it is opened, with placeholders filled in from the item and the person (e.g. {"project": "{code}"};
see tools.service.context_values for the placeholders).
"""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import BaseModel

KINDS = ("link", "form", "checklist")


class Tool(BaseModel):
    __tablename__ = "tools"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    icon: Mapped[str | None] = mapped_column(String(16), nullable=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="link")
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    work_item_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    unit_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    role_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    item_type_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # form: {"fields": ["risks", "custom_fields.go_live"]}
    # checklist: {"items": [{"code": "tested", "label": "Tested end to end"}], "pass_pct": 80}
    definition: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    context_params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ToolResponse(BaseModel):
    """The current answers of a checklist tool on one work item. Every change is audited."""

    __tablename__ = "tool_responses"
    __table_args__ = (UniqueConstraint("tenant_id", "tool_id", "work_item_id", name="uq_tool_responses_tool_item"),)

    tool_id: Mapped[int] = mapped_column(ForeignKey("tools.id"), nullable=False, index=True)
    work_item_id: Mapped[int] = mapped_column(ForeignKey("work_items.id"), nullable=False, index=True)
    answers: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # {item code: true/false}
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    score_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    submitted_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
