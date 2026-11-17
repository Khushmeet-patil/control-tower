"""Templates (Phase 10): reusable work breakdowns, e.g. "Product launch" → milestones → tasks.

A template stores a tree of nodes, never links to live items:
    {"title", "item_type_id", "description", "objective", "weight",
     "start_offset": days after the start date (or null), "duration": days (or null), "children": [...]}
Made by saving an existing item's breakdown ("Save as template") or edited on the Templates screen.
Using a template creates real work items through WorkItemService, as the person using it (their rights,
inheritance of owners and units, audit), in one transaction: the whole tree is created or nothing is.

Private to the owner unless shared (needs `templates.share`); shared templates can be used by everyone.
"""
from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.models import BaseModel


class WorkTemplate(BaseModel):
    __tablename__ = "work_templates"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    is_shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    structure: Mapped[list] = mapped_column(JSON, nullable=False)
    node_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_item_id: Mapped[int | None] = mapped_column(ForeignKey("work_items.id"), nullable=True)

    owner = relationship("User", foreign_keys=[owner_id], lazy="joined")
