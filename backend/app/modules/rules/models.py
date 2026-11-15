"""Health and data-quality rules, stored as settings (drafted in admin, used once published).

A rule = a condition type from app.modules.rules.catalog (code) + its parameters and outcome (data).
Admins choose the thresholds, the colour it gives (Red, Amber or Grey), which item types it checks,
how many points it adds to the Action Centre score, the recommended action and who to escalate to.

kind:
- "health": the finding colours the item (and, through roll-up, everything above it);
- "data_quality": the finding is listed as a data-quality flag but does not change the colour;
- "signal": the finding is an opportunity or a watch point (e.g. ready for rollout, built but not
  adopted). It ranks in the Action Centre and its watchlist but does not change the colour.
"""
from sqlalchemy import JSON, Boolean, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import BaseModel

RULE_KINDS = {"health": "Health", "data_quality": "Data quality", "signal": "Signal (Action Centre only)"}
OUTCOMES = {"red": "Red", "amber": "Amber", "grey": "Grey"}
ESCALATE_TO = {
    "accountable": "Accountable owner",
    "accountable_manager": "Accountable owner's manager",
    "parent_accountable": "Accountable owner of the parent item",
    "unit_head": "Head of the item's unit",
    "approver": "The person whose approval is awaited",
}


class HealthRule(BaseModel):
    __tablename__ = "health_rules"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_health_rules_tenant_code"),)

    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="health")
    rule_type: Mapped[str] = mapped_column(String(40), nullable=False)
    params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    outcome: Mapped[str] = mapped_column(String(10), nullable=False, default="amber")
    # Item type lookup value ids this rule checks; empty = every type.
    item_type_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Base points in the Action Centre ranking (priority and lateness add to it).
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    # Shown with the finding; may use {accountable}, {responsible}, {escalation}, {days}, {item}.
    recommended_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    escalate_to: Mapped[str] = mapped_column(String(30), nullable=False, default="accountable")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
