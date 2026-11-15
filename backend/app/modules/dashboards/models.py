"""Dashboards: a named page of widgets, personal or shared.

Each widget reads governed data through the normal, scoped work list (see service.py), so a shared
dashboard shows every viewer only the work they may see, and every number opens the list behind it.

`widgets` is a list of small dicts, validated by DashboardService:
    {"id": "w1", "type": "kpi" | "table" | "chart" | "progress" | "timeline" | "actions",
     "title": "Red work", "view_id": 12 | None, "filters": {...Portfolio filters...},
     "group_by": "status_id" (charts), "chart": "bar" | "doughnut", "limit": 10, "width": 1 | 2}
A widget built on a saved view follows that view's current filters; `filters` keeps a copy, used if
the view is later deleted.
"""
from sqlalchemy import JSON, Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.models import BaseModel

WIDGET_TYPES = {
    "kpi": "Number (KPI)",
    "table": "Table",
    "chart": "Status chart",
    "progress": "Progress",
    "timeline": "Timeline",
    "actions": "My top actions",
}
# Charts group the matching items by one of these. Every group drills into the list with that filter added.
GROUP_BY = {
    "status_id": "Status", "priority_id": "Priority", "health": "Health", "item_type_id": "Item type",
    "category_id": "Category", "accountable_id": "Accountable owner",
}
CHARTS = {"bar": "Bars", "doughnut": "Doughnut"}


class Dashboard(BaseModel):
    __tablename__ = "dashboards"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    widgets: Mapped[list] = mapped_column(JSON, nullable=False)

    owner = relationship("User", lazy="joined")
