"""Integrations (Phase 10): API tokens, webhooks, and the links Microsoft Entra ID sign-in needs.

- ApiToken: a personal access token for scripts, Power BI and other tools. The token acts as its owner,
  with the owner's current roles and scope, never more. Only a SHA-256 hash is stored; the token is
  shown once, when it is created. `scopes`:
    read      GET requests (the API, the reporting feeds for Power BI)
    write     also POST/PATCH/DELETE (tools that write back, through the same services and audit)
    calendar  only the personal calendar feed (.ics) for Outlook
  A token can expire and can be revoked by its owner or an administrator (integrations.manage).
- Webhook: Control Tower calls an address when something happens. `events` lists what to send:
    "<entity>.<operation>"  an audited change, e.g. "work_item.update", "assignment.create",
                            "approval_request.approve"; "<entity>.*" for every operation
    "alert.<kind>"          a notification kind, e.g. "alert.item_red", "alert.approval_needed"
  `unit_id` limits work item, assignment and alert events to work in that unit and the units below.
  `format` "teams" sends a Microsoft Teams message card (for a channel's incoming webhook); "json" sends
  a signed JSON body (see notifications.delivery).
"""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.models import BaseModel

TOKEN_SCOPES = {"read": "Read the API and reporting feeds", "write": "Read and change records through the API",
                "calendar": "Only the calendar feed (Outlook)"}
WEBHOOK_FORMATS = {"json": "Signed JSON", "teams": "Microsoft Teams channel"}


class ApiToken(BaseModel):
    __tablename__ = "api_tokens"
    __table_args__ = (UniqueConstraint("token_hash", name="uq_api_tokens_hash"),)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    token_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    scopes: Mapped[list] = mapped_column(JSON, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user = relationship("User", foreign_keys=[user_id], lazy="joined")


class Webhook(BaseModel):
    __tablename__ = "webhooks"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    format: Mapped[str] = mapped_column(String(20), nullable=False, default="json")
    events: Mapped[list] = mapped_column(JSON, nullable=False)
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("org_units.id"), nullable=True)
    secret: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
