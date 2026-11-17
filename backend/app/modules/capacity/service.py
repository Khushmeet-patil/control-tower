"""Time off (who records it) and capacity queries (find people by skill and free capacity, suggestions
for an assignment, week-by-week load of a team). Everything is limited to the people the viewer may see."""
from sqlalchemy import select

from app.core.command import CommandService
from app.core.errors import Forbidden, ValidationFailed
from app.core.permissions import actor_can
from app.core.tree import descendant_ids
from app.extensions import db
from app.modules.access.scope import is_global, managed_unit_ids, person_visibility_clause
from app.modules.auth.models import User
from app.modules.capacity import engine
from app.modules.capacity.models import PublicHoliday, TimeOff
from app.modules.config.versioning import published_list
from app.modules.organisation.models import OrgUnitClosure
from app.modules.rules.engine import capacity_buffer
from app.modules.work.models import Assignment
from app.modules.work.service import WorkItemService, _int, person_ref


def visible_people(actor, *, unit_id=None, skill_ids=(), q=None):
    stmt = select(User).where(User.tenant_id == actor.tenant_id, User.is_deleted.is_(False), User.is_active.is_(True))
    if (clause := person_visibility_clause(actor)) is not None:
        stmt = stmt.where(clause)
    if unit_id:
        stmt = stmt.where(User.unit_id.in_(descendant_ids(OrgUnitClosure, [_int(unit_id, "unit_id")])))
    if q:
        stmt = stmt.where(User.full_name.ilike(f"%{q}%") | User.job_title.ilike(f"%{q}%"))
    people = db.session.scalars(stmt.order_by(User.full_name)).all()
    wanted = {int(s) for s in skill_ids}
    return [p for p in people if wanted <= set(p.skill_ids or [])]


def describe(actor, people) -> list[dict]:
    """People with their skills and today's capacity figures, most free capacity first."""
    figures = engine.people_now(actor.tenant_id, [p.id for p in people], capacity_buffer(actor.tenant_id))
    rows = [{"person": {**person_ref(p), "unit": p.unit.name if p.unit else None,
                        "function": p.function.name if p.function else None},
             "skill_ids": p.skill_ids or [], "backlog_days": p.backlog_days, **figures[p.id]} for p in people]
    rows.sort(key=lambda r: (r["status"] == "on_leave", -r["free_pct"], r["person"]["full_name"]))
    return rows


def _skill_ids(raw):
    try:
        return [int(s) for s in (raw or "").split(",") if s]
    except ValueError as exc:
        raise ValidationFailed("skill_ids must be numbers", {"field": "skill_ids"}) from exc


def find_people(actor, params) -> dict:
    """The prototype's "find by skill (shows spare capacity)"."""
    people = visible_people(actor, unit_id=params.get("unit_id"), skill_ids=_skill_ids(params.get("skill_ids")),
                            q=params.get("q"))
    return {"items": describe(actor, people), "buffer_pct": capacity_buffer(actor.tenant_id)}


def suggestions(actor, item_id, params) -> dict:
    """Who could take on this item: people in its unit (and below) not already on it, by free capacity."""
    item = WorkItemService(actor).get(item_id)
    assigned = set(db.session.scalars(select(Assignment.person_id).where(
        Assignment.work_item_id == item.id, Assignment.is_deleted.is_(False))))
    people = [p for p in visible_people(actor, unit_id=item.unit_id, skill_ids=_skill_ids(params.get("skill_ids")))
              if p.id not in assigned]
    rows = [r for r in describe(actor, people) if r["status"] != "on_leave"]
    return {"items": rows[:10], "unit_id": item.unit_id}


def timeline(actor, unit_id, weeks=8) -> dict:
    """Week-by-week load of the people in a unit the viewer manages."""
    unit_id = _int(unit_id, "unit_id")
    managed = managed_unit_ids(actor)
    if managed is not None and unit_id not in managed:
        raise Forbidden("You can only see the capacity of units you manage")
    weeks = max(1, min(26, _int(weeks or 8, "weeks")))
    people = visible_people(actor, unit_id=unit_id)
    data = engine.weekly(actor.tenant_id, [p.id for p in people], capacity_buffer(actor.tenant_id), weeks)
    return {"weeks": [w["week_start"] for w in next(iter(data.values()), [])],
            "people": [{"person": person_ref(p), "weeks": data[p.id]} for p in people]}


class TimeOffService(CommandService):
    """People record their own time off; managers (people.manage) record it for the people in their area."""

    model = TimeOff
    entity_type = "time_off"
    permissions = {"create": None, "update": None, "delete": None}

    def base_query(self):
        stmt = super().base_query().join(User, User.id == TimeOff.person_id)
        if self.actor is not None and (clause := person_visibility_clause(self.actor)) is not None:
            stmt = stmt.where(clause)
        return stmt

    def list(self, params):
        stmt = self.base_query()
        if pid := params.get("person_id"):
            stmt = stmt.where(TimeOff.person_id == _int(pid, "person_id"))
        if unit := params.get("unit_id"):
            stmt = stmt.where(User.unit_id.in_(descendant_ids(OrgUnitClosure, [_int(unit, "unit_id")])))
        if params.get("current") in ("1", "true"):
            from app.core.dates import today

            stmt = stmt.where(TimeOff.end_date >= today())
        rows = db.session.scalars(stmt.order_by(TimeOff.start_date)).all()
        return {"items": [self.serialize(r) for r in rows]}

    def serialize(self, r):
        return {"id": r.id, "person": person_ref(r.person), "person_id": r.person_id,
                "start_date": r.start_date.isoformat(), "end_date": r.end_date.isoformat(), "kind_id": r.kind_id,
                "note": r.note, "can_edit": self._may_edit(r.person_id), "version": r.version}

    def _may_edit(self, person_id):
        if self.actor is None or self.actor.id == person_id or is_global(self.actor):
            return True
        if not actor_can(self.actor, "people.manage"):
            return False
        person = db.session.get(User, person_id)
        managed = managed_unit_ids(self.actor) or set()
        return person is not None and person.unit_id in managed

    def _check(self, data, obj=None):
        person_id = data.get("person_id", getattr(obj, "person_id", None))
        person = db.session.get(User, person_id) if person_id else None
        if person is None or person.tenant_id != self.tenant_id or person.is_deleted:
            raise ValidationFailed("Choose a person", {"field": "person_id"})
        if not self._may_edit(person_id):
            raise Forbidden("You can record time off only for yourself or for people in your area")
        start = data.get("start_date", getattr(obj, "start_date", None))
        end = data.get("end_date", getattr(obj, "end_date", None))
        if not start or not end:
            raise ValidationFailed("Give the first and last day", {"field": "end_date"})
        if end < start:
            raise ValidationFailed("The last day is before the first day", {"field": "end_date"})
        if (end - start).days > 366:
            raise ValidationFailed("Record time off of a year or less at a time", {"field": "end_date"})
        if data.get("kind_id") is not None:
            kinds = published_list(self.tenant_id, "time_off_type")
            if data["kind_id"] not in kinds or (not kinds[data["kind_id"]]["is_active"]
                                                and data["kind_id"] != getattr(obj, "kind_id", None)):
                raise ValidationFailed("Choose a kind of time off", {"field": "kind_id"})

    def validate_create(self, data):
        data.setdefault("person_id", getattr(self.actor, "id", None))
        self._check(data)

    def validate_update(self, obj, changes):
        if not self._may_edit(obj.person_id):
            raise Forbidden("You cannot change this time off")
        self._check(changes, obj)

    def validate_delete(self, obj):
        if not self._may_edit(obj.person_id):
            raise Forbidden("You cannot remove this time off")


class HolidayService(CommandService):
    """Public holidays. Organisation-wide ones need settings.manage; a unit's own need settings.manage or
    people.manage over that unit. Everyone can read the holidays that apply to their part of the organisation."""

    model = PublicHoliday
    entity_type = "public_holiday"
    permissions = {"create": None, "update": None, "delete": None}

    def list(self, params):
        stmt = self.base_query()
        if year := params.get("year"):
            from datetime import date

            y = _int(year, "year")
            stmt = stmt.where(PublicHoliday.holiday_date >= date(y, 1, 1), PublicHoliday.holiday_date <= date(y, 12, 31))
        if unit := params.get("unit_id"):
            from app.core.tree import ancestor_ids

            chain = ancestor_ids(OrgUnitClosure, _int(unit, "unit_id"), include_self=True)
            stmt = stmt.where(PublicHoliday.unit_id.is_(None) | PublicHoliday.unit_id.in_(chain))
        rows = db.session.scalars(stmt.order_by(PublicHoliday.holiday_date)).all()
        return {"items": [self.serialize(r) for r in rows]}

    def serialize(self, r):
        return {"id": r.id, "holiday_date": r.holiday_date.isoformat(), "name": r.name, "unit_id": r.unit_id,
                "unit": {"id": r.unit.id, "name": r.unit.name} if r.unit else None,
                "can_edit": self._may_edit(r.unit_id), "version": r.version}

    def _may_edit(self, unit_id):
        if self.actor is None or actor_can(self.actor, "settings.manage"):
            return True
        if unit_id is None or not actor_can(self.actor, "people.manage"):
            return False
        managed = managed_unit_ids(self.actor)
        return managed is None or unit_id in managed

    def _check(self, data, obj=None):
        unit_id = data.get("unit_id", getattr(obj, "unit_id", None))
        if unit_id is not None:
            from app.modules.organisation.models import OrgUnit

            unit = db.session.get(OrgUnit, unit_id)
            if unit is None or unit.tenant_id != self.tenant_id or unit.is_deleted:
                raise ValidationFailed("Unit not found", {"field": "unit_id"})
        if not self._may_edit(unit_id):
            raise Forbidden("You can set holidays only for units you manage")
        if "name" in data and not (data["name"] or "").strip():
            raise ValidationFailed("Name the holiday", {"field": "name"})

    def validate_create(self, data):
        if not data.get("holiday_date"):
            raise ValidationFailed("Choose the date", {"field": "holiday_date"})
        self._check(data)

    def validate_update(self, obj, changes):
        if not self._may_edit(obj.unit_id):
            raise Forbidden("You cannot change this holiday")
        self._check(changes, obj)

    def validate_delete(self, obj):
        if not self._may_edit(obj.unit_id):
            raise Forbidden("You cannot remove this holiday")
