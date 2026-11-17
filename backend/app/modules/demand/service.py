"""Demand intake: raise, assess and decide requests for new work (the prototype's Demand Intake).

Who sees a request: the person who raised it, managers of the unit asked to deliver it (and the units
above), and organisation-wide roles. Who decides: people with `demand.decide` over that unit.
The requester may edit it while it is New or waiting for clarification; deciders may always edit it.

Assess (the prototype's "Assess & decide"):
    free capacity = Σ max(0, usable − load) over the unit's people (see app.modules.capacity.engine)
    effort not estimated → cannot assess; effort > free → shortfall, and the lower-priority top-level
    work in delivery in that unit that could be deferred, with the capacity points allocated to it.
Accept creates a draft initiative in the same transaction (one audit trail, all or nothing).
"""
import re

from sqlalchemy import or_, select

from app.core.command import CommandService
from app.core.dates import today
from app.core.errors import Forbidden, ValidationFailed
from app.core.filters import apply_filters
from app.core.models import utcnow
from app.core.pagination import paginate
from app.core.permissions import actor_can
from app.core.tree import descendant_ids
from app.extensions import db
from app.modules.access.scope import is_global, managed_unit_ids
from app.modules.auth.models import User
from app.modules.config.versioning import published_list, published_value_id
from app.modules.demand.models import DemandRequest
from app.modules.organisation.models import OrgUnit, OrgUnitClosure
from app.modules.work.models import Assignment, WorkItem, WorkItemClosure
from app.modules.work.service import WorkItemService, person_ref

OPEN_DECISIONS = ("new", "clarification")
NEEDS_NOTE = ("rejected", "deferred", "clarification")
FILTERABLE = {
    "code": DemandRequest.code, "title": DemandRequest.title, "decision_id": DemandRequest.decision_id,
    "priority_id": DemandRequest.priority_id, "urgency_id": DemandRequest.urgency_id, "unit_id": DemandRequest.unit_id,
    "requester_id": DemandRequest.requester_id, "requested_on": DemandRequest.requested_on,
    "needed_by": DemandRequest.needed_by, "effort_pct": DemandRequest.effort_pct,
}
SEARCH = [DemandRequest.code, DemandRequest.title, DemandRequest.description]
LOOKUPS = {"urgency_id": "urgency", "priority_id": "priority"}
DECISION_FIELDS = frozenset({"decision_id", "decision_note", "decided_by_id", "decided_at", "work_item_id"})


def _iso(d):
    return d.isoformat() if d else None


class DemandService(CommandService):
    model = DemandRequest
    entity_type = "demand_request"
    permissions = {"create": "work.view", "update": "work.view", "delete": "work.view"}
    protected_fields = frozenset({"code"}) | DECISION_FIELDS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._deciding = False

    # ------------------------------------------------------------------ reads
    def base_query(self):
        stmt = super().base_query()
        if self.actor is None or is_global(self.actor):
            return stmt
        conditions = [DemandRequest.requester_id == self.actor.id]
        if managed := managed_unit_ids(self.actor):
            conditions.append(DemandRequest.unit_id.in_(managed))
        return stmt.where(or_(*conditions))

    def decision(self, code):
        return published_value_id(self.tenant_id, "demand_decision", code)

    def awaiting_ids(self):
        return [i for i in (self.decision(c) for c in OPEN_DECISIONS) if i]

    def list(self, params):
        params = dict(params)
        stmt = self.base_query()
        if params.pop("awaiting", "") in ("1", "true"):
            stmt = stmt.where(or_(DemandRequest.decision_id.in_(self.awaiting_ids()), DemandRequest.decision_id.is_(None)))
        if params.pop("mine", "") in ("1", "true"):
            stmt = stmt.where(DemandRequest.requester_id == self.actor.id)
        stmt = apply_filters(stmt, params, FILTERABLE, SEARCH, default_sort="-requested_on")
        return paginate(stmt, params, self.serialize)

    def can_decide(self, r) -> bool:
        if self.actor is None:
            return True
        if not actor_can(self.actor, "demand.decide"):
            return False
        managed = managed_unit_ids(self.actor)
        return managed is None or r.unit_id in managed

    def can_edit(self, r) -> bool:
        if self.can_decide(r):
            return True
        return r.requester_id == getattr(self.actor, "id", None) and (r.decision_id in self.awaiting_ids() or r.decision_id is None)

    def serialize(self, r: DemandRequest) -> dict:
        item = db.session.get(WorkItem, r.work_item_id) if r.work_item_id else None
        return {
            "id": r.id, "code": r.code, "title": r.title, "description": r.description,
            "requester": person_ref(r.requester), "requester_id": r.requester_id, "sponsor": r.sponsor,
            "business_value": r.business_value, "urgency_id": r.urgency_id, "priority_id": r.priority_id,
            "effort_pct": r.effort_pct, "requested_on": _iso(r.requested_on), "needed_by": _iso(r.needed_by),
            "dependencies": r.dependencies, "remarks": r.remarks,
            "unit": {"id": r.unit.id, "name": r.unit.name} if r.unit else None, "unit_id": r.unit_id,
            "decision_id": r.decision_id, "decision_note": r.decision_note,
            "decided_by": person_ref(r.decided_by), "decided_at": r.decided_at.isoformat() if r.decided_at else None,
            "work_item": {"id": item.id, "code": item.code, "title": item.title} if item else None,
            "awaiting": r.decision_id in self.awaiting_ids() or r.decision_id is None,
            "permissions": {"can_edit": self.can_edit(r), "can_decide": self.can_decide(r),
                            "can_delete": self._can_delete(r)},
            "version": r.version,
        }

    # ------------------------------------------------------------------ validation
    def _check(self, data, obj=None):
        for field, list_code in LOOKUPS.items():
            if data.get(field) is not None:
                values = published_list(self.tenant_id, list_code)
                v = values.get(data[field])
                if v is None or (not v["is_active"] and data[field] != getattr(obj, field, None)):
                    raise ValidationFailed("Choose one of the listed options", {"field": field})
        if "unit_id" in data:
            unit = db.session.get(OrgUnit, data["unit_id"]) if data["unit_id"] else None
            if unit is None or unit.tenant_id != self.tenant_id or unit.is_deleted:
                raise ValidationFailed("Choose the unit that would deliver it", {"field": "unit_id"})
        if data.get("requester_id") is not None:
            found = db.session.scalar(select(User.id).where(User.id == data["requester_id"], User.tenant_id == self.tenant_id,
                                                            User.is_deleted.is_(False)))
            if not found:
                raise ValidationFailed("Choose a person", {"field": "requester_id"})
        if data.get("effort_pct") is not None and not 0 <= data["effort_pct"] <= 100000:
            raise ValidationFailed("Effort is in capacity points (1 = 1% of a person's week)", {"field": "effort_pct"})
        start = data.get("requested_on", getattr(obj, "requested_on", None))
        end = data.get("needed_by", getattr(obj, "needed_by", None))
        if start and end and end < start:
            raise ValidationFailed("Needed by is before the request date", {"field": "needed_by"})

    def _next_code(self):
        used = db.session.scalars(select(DemandRequest.code).where(DemandRequest.tenant_id == self.tenant_id))
        numbers = [int(m.group(1)) for c in used if (m := re.match(r"REQ-(\d+)$", c))]
        return f"REQ-{max(numbers, default=0) + 1:03d}"

    def validate_create(self, data):
        data.setdefault("requester_id", getattr(self.actor, "id", None))
        if data.get("requester_id") is None:
            raise ValidationFailed("Choose who is asking", {"field": "requester_id"})
        if data.get("unit_id") is None:
            requester = db.session.get(User, data["requester_id"])
            data["unit_id"] = requester.unit_id if requester else None
        data.setdefault("unit_id", None)
        data["requested_on"] = data.get("requested_on") or today()
        self._check(data)
        data["decision_id"] = self.decision("new")
        data["code"] = self._next_code()

    def _clean(self, data):
        if self._deciding:  # decide() writes only the decision fields, which are otherwise protected
            return dict(data)
        return super()._clean(data)

    def validate_update(self, obj, changes):
        if self._deciding:
            return
        if not self.can_edit(obj):
            raise Forbidden("Only the requester (while it is open) or a decider can change this request")
        self._check(changes, obj)

    def _can_delete(self, r):
        return self.can_decide(r) or (r.requester_id == getattr(self.actor, "id", None) and r.decision_id == self.decision("new"))

    def validate_delete(self, obj):
        if not self._can_delete(obj):
            raise Forbidden("Only the requester (while it is new) or a decider can delete this request")
        if obj.work_item_id:
            raise ValidationFailed("This request became an initiative; it is kept for the record")

    # ------------------------------------------------------------------ assess and decide
    def assessment(self, request_id) -> dict:
        from app.modules.capacity.engine import people_now
        from app.modules.capacity.service import visible_people
        from app.modules.rules import engine
        from app.modules.rules.engine import capacity_buffer

        r = self.get(request_id)
        buffer = capacity_buffer(self.tenant_id)
        people = visible_people(self.actor, unit_id=r.unit_id) if self.actor else []
        figures = people_now(self.tenant_id, [p.id for p in people], buffer)
        free = sum(f["free_pct"] for f in figures.values())
        need = r.effort_pct or 0
        verdict = "not_estimated" if not need else "shortfall" if need > free else "fits"

        candidates = []
        if verdict == "shortfall" and r.priority_id:
            rank = engine.priority_bonus(self.tenant_id)
            mine = rank.get(r.priority_id, 0)
            work = WorkItemService(self.actor, tenant_id=self.tenant_id)
            units = descendant_ids(OrgUnitClosure, [r.unit_id])
            tops = db.session.scalars(work.base_query().where(WorkItem.parent_id.is_(None), WorkItem.unit_id.in_(units))).all()
            results = engine.evaluate(self.tenant_id, [t.id for t in tops])
            for t in tops:
                if not (results.get(t.id) and results[t.id].health) or rank.get(t.priority_id, 0) >= mine:
                    continue  # only work in delivery with a lower priority
                below = select(WorkItemClosure.descendant_id).where(WorkItemClosure.ancestor_id == t.id)
                points = sum(db.session.scalars(select(Assignment.allocation_pct).where(
                    Assignment.work_item_id.in_(below), Assignment.is_deleted.is_(False),
                    or_(Assignment.start_date.is_(None), Assignment.start_date <= today()),
                    or_(Assignment.end_date.is_(None), Assignment.end_date >= today())))) or 0
                candidates.append({"id": t.id, "code": t.code, "title": t.title, "priority_id": t.priority_id,
                                   "health": results[t.id].health, "allocated_pts": int(points)})
            candidates.sort(key=lambda c: (rank.get(c["priority_id"], 0), -c["allocated_pts"], c["code"]))
        return {
            "request": self.serialize(r), "buffer_pct": buffer, "people": len(people), "free_pts": free,
            "need_pts": need, "verdict": verdict, "shortfall_pts": max(0, need - free),
            "candidates": candidates,
            "decisions": [{"id": v["id"], "code": v["code"], "label": v["label"]}
                          for v in sorted(published_list(self.tenant_id, "demand_decision").values(),
                                          key=lambda v: (v["sort_order"], v["id"]))
                          if v["is_active"] and v["code"] != "new"],
        }

    def decide(self, request_id, decision_id, *, note=None, initiative=None):
        """Record the decision. Accepting with `initiative` ({"item_type_id", "accountable_id", "unit_id", …})
        creates a draft initiative from the request in the same transaction."""
        r = self.get(request_id)
        if not self.can_decide(r):
            raise Forbidden("You cannot decide requests for this unit")
        decisions = published_list(self.tenant_id, "demand_decision")
        chosen = decisions.get(decision_id)
        if chosen is None or not chosen["is_active"] or chosen["code"] == "new":
            raise ValidationFailed("Choose a decision", {"field": "decision_id"})
        if chosen["code"] in NEEDS_NOTE and not (note or "").strip():
            raise ValidationFailed("Add a note explaining the decision", {"field": "decision_note"})
        if r.work_item_id and chosen["code"] != "accepted":
            raise ValidationFailed("This request already became an initiative", {"field": "decision_id"})
        with self.transaction():
            item_id = r.work_item_id
            if chosen["code"] == "accepted" and initiative is not None and not item_id:
                item = WorkItemService(self.actor, tenant_id=self.tenant_id, source=self.source,
                                       correlation_id=self.correlation_id).create({
                    "title": initiative.get("title") or r.title,
                    "item_type_id": initiative.get("item_type_id"),
                    "description": r.description, "objective": r.business_value, "priority_id": r.priority_id,
                    "planned_end": r.needed_by, "unit_id": initiative.get("unit_id") or r.unit_id,
                    "accountable_id": initiative.get("accountable_id") or getattr(self.actor, "id", None),
                    "remarks": f"From request {r.code}" + (f" (sponsor: {r.sponsor})" if r.sponsor else ""),
                }, reason=f"Created from request {r.code}")
                item_id = item.id
            self._deciding = True
            try:
                self.update(r.id, {"decision_id": decision_id, "decision_note": (note or "").strip() or None,
                                   "decided_by_id": getattr(self.actor, "id", None), "decided_at": utcnow(),
                                   "work_item_id": item_id}, reason=note or chosen["label"])
            finally:
                self._deciding = False
            from app.modules.notifications.service import notify

            notify(self.tenant_id, [r.requester_id], "demand_decided", f"Your request {r.code} {r.title}: {chosen['label']}",
                   body=(note or "").strip() or None, link=f"/pages/demand.html?assess={r.id}",
                   entity=("demand_request", r.id), actor=self.actor, source=self.source)
        return self.get(r.id)
