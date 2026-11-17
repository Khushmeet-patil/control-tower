"""Presentations: dashboard pages arranged into a full-screen management review, with speaker notes.

`pages` is an ordered list:
    {"id": "p1", "dashboard_id": 4, "title": "Portfolio", "notes": "Speaker notes…"}
A published page also carries `widgets` (a copy of the dashboard's widgets, with each widget's
filters written out, so later edits to the dashboard or its saved views do not change it).

Modes:
- live      every page shows the live figures, for each viewer.
- snapshot  every page is calculated from `snapshot_id`'s stored figures.

Publishing (status "published") needs snapshot mode and an approved snapshot. It freezes the pages,
and afterwards the review pack cannot be changed or deleted, so it reopens exactly as it was presented.
"""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.models import BaseModel

MODES = ("live", "snapshot")


class Presentation(BaseModel):
    __tablename__ = "presentations"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    is_shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="live")
    snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("snapshots.id"), nullable=True, index=True)
    pages: Mapped[list] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    owner = relationship("User", foreign_keys=[owner_id], lazy="joined")
