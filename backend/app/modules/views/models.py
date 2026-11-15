"""Saved views: a named set of filters (and a list or board layout) for a screen.

Personal views belong to one person. Shared views are visible to everyone who can open the screen;
sharing needs the `views.share` permission. The filters are replayed through the normal, scoped list
API, so a shared view never shows anyone more than they may see.
"""
from sqlalchemy import JSON, Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.models import BaseModel

PAGES = {"work": "Portfolio"}
LAYOUTS = {"list": "List", "board": "Board"}


class SavedView(BaseModel):
    __tablename__ = "saved_views"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    page: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    filters: Mapped[dict] = mapped_column(JSON, nullable=False)
    layout: Mapped[str] = mapped_column(String(10), nullable=False, default="list")
    is_shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    owner = relationship("User", lazy="joined")
