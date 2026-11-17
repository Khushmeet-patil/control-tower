"""Capacity and availability (Phase 6A).

Skills, working capacity (% of a full week) and backlog live on the person (auth.models.User).
TimeOff records days a person is not available (leave, holiday, training…); the kind is a lookup value
from the "time_off_type" list, so admins choose the kinds and colours.
"""
from datetime import date

from sqlalchemy import Date, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.models import BaseModel


class TimeOff(BaseModel):
    __tablename__ = "time_off"

    person_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    end_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    kind_id: Mapped[int | None] = mapped_column(ForeignKey("lookup_values.id"), nullable=True)
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)

    person = relationship("User", foreign_keys=[person_id], lazy="joined")


class PublicHoliday(BaseModel):
    """A day nobody in a unit (and the units below it) works; no unit = the whole organisation.
    Capacity treats it like time off for everyone it applies to (Phase 10 working calendars)."""

    __tablename__ = "public_holidays"

    holiday_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("org_units.id"), nullable=True, index=True)

    unit = relationship("OrgUnit", foreign_keys=[unit_id], lazy="joined")
