"""Notifications (Phase 10): telling people when something needs them.

- Notification: one message for one person, shown in the bell in the top bar (in-app). Created in the
  same transaction as the change that caused it, so a failed change never leaves a stray message.
  `dedupe_key` stops the daily checks (item turned Red, deadline due, overdue) repeating themselves.
- Delivery: the outbox. Email to a person and calls to webhooks (including Microsoft Teams channels)
  are written here in the same transaction, then sent by `flask --app run notify --deliver`, with
  retries. Nothing is sent for a change that was rolled back.
- HealthWatch: the last health each work item was seen with by the daily check, so "turned Red" is
  noticed once, when it happens, not every day it stays Red.

What kinds exist (`kind`) is code, because each is raised by a piece of code; who gets them and by
which channel is each person's preference (User.notification_prefs).
"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import BaseModel
from app.extensions import db

# kind → (label, description, sent by email by default)
KINDS = {
    "assignment": ("Assigned to work", "Someone assigned you to a work item.", True),
    "handover": ("Ownership handed to you", "You became the accountable owner of a work item.", True),
    "approval_needed": ("Approval needed", "A completed item is waiting for your approval.", True),
    "approval_decided": ("Approval decided", "Work you submitted was approved or sent back.", True),
    "item_red": ("Item turned Red", "Work you own or are responsible for turned Red.", True),
    "due_soon": ("Deadline coming up", "Work you own or are responsible for is due soon.", False),
    "overdue": ("Overdue", "Work you own or are responsible for passed its planned finish.", True),
    "demand_decided": ("Request decided", "A request you raised was accepted, rejected, deferred or needs clarifying.", True),
    "scenario_applied": ("Scenario applied", "A what-if scenario that changed your work was applied.", False),
}
CHANNELS = ("email",)  # in-app is always on; Teams goes through webhooks (see integrations)
DELIVERY_STATUSES = ("pending", "sent", "failed")


class Notification(BaseModel):
    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", "dedupe_key", name="uq_notifications_user_dedupe"),)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    link: Mapped[str | None] = mapped_column(String(300), nullable=True)
    entity_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(120), nullable=True)


class Delivery(db.Model):
    """One message to send outside Control Tower. Append-only apart from its sending state."""

    __tablename__ = "deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)  # email | webhook
    target: Mapped[str] = mapped_column(String(500), nullable=False)  # email address or webhook URL
    webhook_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    notification_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    event: Mapped[str] = mapped_column(String(80), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(300), nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class HealthWatch(db.Model):
    __tablename__ = "health_watch"

    work_item_id: Mapped[int] = mapped_column(ForeignKey("work_items.id"), primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    health: Mapped[str | None] = mapped_column(String(20), nullable=True)
    seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
