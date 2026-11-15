"""Work items and assignments: create, delegate, hand over and track work within the actor's scope.

Who can see a work item (see work_visibility_clause):
- everyone with an organisation-wide role;
- managers, for work assigned to their units and the units below;
- functional leads, for work in the functions they lead;
- anyone who is accountable, responsible or assigned on an item, for that item and everything under it.

What they can do with it (see WorkItemService.access):
- MANAGE: edit everything, add children, assign people, delete. Unit managers with `work.manage`,
  the accountable owner of the item or of any item above it, and the responsible owner of an item above it.
- CONTRIBUTE: the responsible owners and assignees of the item may update progress fields only
  (CONTRIBUTOR_FIELDS). Responsible owners may also add child items (delegation).
- VIEW: read only.
"""
import re
from datetime import date

from sqlalchemy import delete, false, func, or_, select

from app.core.audit import AuditEvent
from app.core.command import CommandService
from app.core.dates import today
from app.core.errors import Forbidden, ValidationFailed
from app.core.filters import apply_filters
from app.core.pagination import paginate
from app.core.permissions import actor_can, ensure_can
from app.core.tree import TreeService, ancestor_ids, descendant_ids
from app.extensions import db
from app.modules.access.scope import is_global, led_function_ids, managed_unit_ids
from app.modules.audit.service import serialize as serialize_event
from app.modules.auth.models import User
from app.modules.config.custom_fields import apply_custom_filters, person_refs
from app.modules.config.versioning import published_list, published_value_id
from app.modules.organisation.models import Function, OrgUnit, OrgUnitClosure
from app.modules.work.models import (
    Assignment, WorkItem, WorkItemClosure, WorkItemDependency, WorkItemResponsible)
from app.modules.work.progress import progress_map
from app.modules.workflows import engine

MANAGE, CONTRIBUTE, VIEW = "manage", "contribute", "view"

# Fields responsible owners and assignees may change on an item they do not manage.
CONTRIBUTOR_FIELDS = frozenset({"status_id", "actual_start", "actual_end", "progress_manual", "evidence_url", "remarks"})

# Lookup-backed columns → the lookup list that supplies their values.
LOOKUP_FIELDS = {
    "item_type_id": "item_type", "status_id": "status", "priority_id": "priority",
    "category_id": "category", "action_type_id": "action_type", "severity_id": "severity",
}
# Status codes that mean the work is finished (no longer counts as open, overdue or allocated).
CLOSED_STATUS_CODES = ("done", "cancelled")

# Short prefixes for readable codes such as PRJ-004. Other item types use their code's first letters.
ITEM_PREFIX = {"programme": "PGM", "project": "PRJ", "milestone": "MS", "task": "TSK", "action": "ACT"}

FILTERABLE = {
    "code": WorkItem.code, "title": WorkItem.title, "item_type_id": WorkItem.item_type_id,
    "status_id": WorkItem.status_id, "priority_id": WorkItem.priority_id, "category_id": WorkItem.category_id,
    "action_type_id": WorkItem.action_type_id, "severity_id": WorkItem.severity_id,
    "unit_id": WorkItem.unit_id, "function_id": WorkItem.function_id, "accountable_id": WorkItem.accountable_id,
    "parent_id": WorkItem.parent_id, "planned_start": WorkItem.planned_start, "planned_end": WorkItem.planned_end,
    "actual_end": WorkItem.actual_end, "approval_status": WorkItem.approval_status,
    "created_at": WorkItem.created_at, "updated_at": WorkItem.updated_at,
}
SEARCH = [WorkItem.code, WorkItem.title, WorkItem.description]


def person_ref(u):
    return {"id": u.id, "full_name": u.full_name, "initials": u.initials, "job_title": u.job_title} if u else None


def _ref(obj):
    return {"id": obj.id, "name": obj.name} if obj else None


def closed_status_ids(tenant_id: int) -> list[int]:
    return [i for i in (published_value_id(tenant_id, "status", c) for c in CLOSED_STATUS_CODES) if i]


def _live_items(tenant_id):
    return select(WorkItem.id).where(WorkItem.tenant_id == tenant_id, WorkItem.is_deleted.is_(False))


def involved_item_ids(user_id: int):
    """Selects of items a person is accountable, responsible or assigned on (one select per role)."""
    return (
        select(WorkItem.id).where(WorkItem.accountable_id == user_id, WorkItem.is_deleted.is_(False)),
        select(WorkItemResponsible.work_item_id).where(WorkItemResponsible.user_id == user_id),
        select(Assignment.work_item_id).where(Assignment.person_id == user_id, Assignment.is_deleted.is_(False)),
    )


def allocated_item_ids(tenant_id: int, person_id: int, on: date | None = None):
    """Select of the items whose assignment counts in a person's load on a day (see allocation_load)."""
    on = on or today()
    stmt = (select(Assignment.work_item_id).join(WorkItem, WorkItem.id == Assignment.work_item_id)
            .where(Assignment.tenant_id == tenant_id, Assignment.person_id == person_id,
                   Assignment.is_deleted.is_(False), WorkItem.is_deleted.is_(False),
                   or_(Assignment.start_date.is_(None), Assignment.start_date <= on),
                   or_(Assignment.end_date.is_(None), Assignment.end_date >= on)))
    closed = closed_status_ids(tenant_id)
    if closed:
        stmt = stmt.where(or_(WorkItem.status_id.is_(None), WorkItem.status_id.not_in(closed)))
    return stmt


def _int(value, field):
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationFailed(f"{field} must be a number", {"field": field}) from exc


def portfolio_params(filters: dict) -> dict:
    """Portfolio-style filters (as in its URL and in saved views: `level`, `unit_id`…) → work list
    API parameters. Mirrors toQuery() in frontend/js/pages/work.js, so a count taken here equals the
    Portfolio list that the same filters open."""
    params = {k: v for k, v in (filters or {}).items() if v not in (None, "")}
    level = params.pop("level", None)
    params.pop("view", None)
    params.pop("layout", None)
    if level != "all":
        params["top_level"] = "1"
    if params.get("unit_id"):
        params["include_descendants"] = "1"
    return params


def work_visibility_clause(user):
    """SQL condition limiting a WorkItem query to what this user may see (None = everything)."""
    if is_global(user):
        return None
    under = lambda ids: WorkItem.id.in_(  # noqa: E731 — the item itself and everything below it
        select(WorkItemClosure.descendant_id).where(WorkItemClosure.ancestor_id.in_(ids)))
    conditions = [under(ids) for ids in involved_item_ids(user.id)]
    if units := managed_unit_ids(user):
        conditions.append(WorkItem.unit_id.in_(units))
    if functions := led_function_ids(user):
        conditions.append(WorkItem.function_id.in_(functions))
    return or_(*conditions) if conditions else false()


def allocation_load(tenant_id: int, person_ids, on: date | None = None) -> dict[int, dict]:
    """{person id: {"pct": total allocation %, "items": number of items}} on a day (default today).

    Counts assignments whose dates cover the day, on live items that are not closed.
    """
    ids = [int(p) for p in person_ids]
    if not ids:
        return {}
    on = on or today()
    closed = closed_status_ids(tenant_id)
    stmt = (select(Assignment.person_id, func.coalesce(func.sum(Assignment.allocation_pct), 0), func.count(Assignment.id))
            .join(WorkItem, WorkItem.id == Assignment.work_item_id)
            .where(Assignment.tenant_id == tenant_id, Assignment.is_deleted.is_(False), WorkItem.is_deleted.is_(False),
                   Assignment.person_id.in_(ids),
                   or_(Assignment.start_date.is_(None), Assignment.start_date <= on),
                   or_(Assignment.end_date.is_(None), Assignment.end_date >= on))
            .group_by(Assignment.person_id))
    if closed:
        stmt = stmt.where(or_(WorkItem.status_id.is_(None), WorkItem.status_id.not_in(closed)))
    found = {pid: {"pct": int(pct), "items": n} for pid, pct, n in db.session.execute(stmt)}
    return {pid: found.get(pid, {"pct": 0, "items": 0}) for pid in ids}


class _ChecksMixin:
    """Validation helpers shared by work items and assignments."""

    def _check_lookup(self, field, value, previous=None, list_code=None):
        if value is None:
            return
        values = published_list(self.tenant_id, list_code or LOOKUP_FIELDS[field])
        found = values.get(value) if isinstance(value, int) and not isinstance(value, bool) else None
        if found is None:
            raise ValidationFailed("Choose one of the listed options", {"field": field})
        if not found["is_active"] and value != previous:
            raise ValidationFailed(f"“{found['label']}” has been retired; choose another option", {"field": field})

    def _check_person(self, person_id, field):
        if person_id is None:
            return
        found = db.session.scalar(select(User.id).where(
            User.id == person_id, User.tenant_id == self.tenant_id, User.is_deleted.is_(False), User.is_active.is_(True)))
        if not found:
            raise ValidationFailed("Choose an active person", {"field": field})

    @staticmethod
    def _check_dates(start, end, field):
        if start and end and start > end:
            raise ValidationFailed("The end date is before the start date", {"field": field})


class WorkItemService(_ChecksMixin, TreeService):
    model = WorkItem
    entity_type = "work_item"
    closure = WorkItemClosure
    # Access is decided per item (see access()); routes require work.view.
    permissions = {"create": "work.view", "update": "work.view", "delete": "work.view"}
    # Set by the platform: codes are generated, approval fields belong to the approvals engine.
    protected_fields = frozenset({"code", "owner_overridden", "approval_status", "approved_at"})
    extra_fields = frozenset({"responsible_ids", "depends_on_ids"})
    custom_entity = "work_item"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._reason = None
        self._access_cache = {}

    # ------------------------------------------------------------------ reads
    def base_query(self):
        stmt = super().base_query()
        clause = work_visibility_clause(self.actor)
        return stmt if clause is None else stmt.where(clause)

    def query(self, params):
        """The scoped, filtered (unsorted-by-page) select behind the work list. Every count shown on a
        screen is taken from this same select, so a number always matches the list it opens."""
        params = dict(params)
        stmt = self.base_query()
        if params.pop("top_level", "") in ("1", "true"):
            stmt = stmt.where(WorkItem.parent_id.is_(None))
        if ancestor := params.pop("ancestor_id", None):
            stmt = stmt.where(WorkItem.id.in_(select(WorkItemClosure.descendant_id).where(
                WorkItemClosure.ancestor_id == _int(ancestor, "ancestor_id"), WorkItemClosure.depth > 0)))
        if params.pop("include_descendants", "") in ("1", "true") and (unit_id := params.pop("unit_id", None)):
            stmt = stmt.where(WorkItem.unit_id.in_(descendant_ids(OrgUnitClosure, [_int(unit_id, "unit_id")])))
        if mine := params.pop("mine", None):
            stmt = stmt.where(self._mine_clause(mine))
        if involves := params.pop("involves", None):  # accountable, responsible or assigned
            stmt = stmt.where(or_(*(WorkItem.id.in_(s) for s in involved_item_ids(_int(involves, "involves")))))
        if responsible := params.pop("responsible_id", None):
            stmt = stmt.where(WorkItem.id.in_(select(WorkItemResponsible.work_item_id).where(
                WorkItemResponsible.user_id == _int(responsible, "responsible_id"))))
        if params.pop("validated", "") in ("1", "true"):  # finished and approved (or needing no approval)
            done = published_value_id(self.tenant_id, "status", "done")
            stmt = stmt.where(WorkItem.status_id == done, or_(WorkItem.approval_status.is_(None),
                                                              WorkItem.approval_status == "approved"))
        if allocated := params.pop("allocated_to", None):  # assignments counted in today's load
            stmt = stmt.where(WorkItem.id.in_(allocated_item_ids(self.tenant_id, _int(allocated, "allocated_to"))))
        closed = closed_status_ids(self.tenant_id)
        open_only = params.pop("open", "") in ("1", "true")
        if params.pop("overdue", "") in ("1", "true"):
            stmt = stmt.where(WorkItem.planned_end < today())
            open_only = True
        if due := params.pop("due_within", ""):  # open work due from today to N days ahead
            stmt = stmt.where(WorkItem.planned_end >= today(), WorkItem.planned_end <= date.fromordinal(
                today().toordinal() + _int(due, "due_within")))
            open_only = True
        if open_only and closed:
            stmt = stmt.where(or_(WorkItem.status_id.is_(None), WorkItem.status_id.not_in(closed)))
        health = {h for h in (params.pop("health", "") or "").split(",") if h}
        stmt = apply_custom_filters(stmt, WorkItem.custom_fields, params, self.tenant_id, self.custom_entity)
        stmt = apply_filters(stmt, params, FILTERABLE, SEARCH, default_sort="code")
        if health:  # health is calculated, not stored: work it out for the matching items, then filter
            from app.modules.rules.service import filter_by_health

            ids = list(db.session.scalars(stmt.with_only_columns(WorkItem.id).order_by(None)))
            stmt = stmt.where(WorkItem.id.in_(filter_by_health(self.tenant_id, ids, health) or [0]))
        return stmt

    def list(self, params):
        page = paginate(self.query(params), params, self.serialize)
        from app.modules.rules.service import annotate_items

        annotate_items(self.actor, self.tenant_id, page["items"])
        return page

    def count(self, params) -> int:
        """How many items the work list returns for these filters (same select, no paging)."""
        params = {k: v for k, v in dict(params).items() if k not in ("page", "per_page", "sort")}
        stmt = self.query(params).with_only_columns(WorkItem.id).order_by(None)
        return db.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    def rows(self, params, limit=None):
        """The matching WorkItem rows (scoped and filtered like the list)."""
        stmt = self.query({k: v for k, v in dict(params).items() if k not in ("page", "per_page")})
        if limit:
            stmt = stmt.limit(limit)
        return db.session.scalars(stmt).all()

    def _mine_clause(self, mine):
        if self.actor is None:
            raise ValidationFailed("'mine' needs a signed-in user")
        accountable, responsible, assigned = (WorkItem.id.in_(s) for s in involved_item_ids(self.actor.id))
        options = {"accountable": accountable, "responsible": responsible, "assigned": assigned,
                   "any": or_(accountable, responsible, assigned)}
        if mine not in options:
            raise ValidationFailed(f"Unknown value for 'mine': {mine}")
        return options[mine]

    # ------------------------------------------------------------------ access
    def access(self, item) -> str:
        """MANAGE, CONTRIBUTE or VIEW for the current actor on this (visible) item."""
        if self.actor is None:
            return MANAGE
        if item.id in self._access_cache:
            return self._access_cache[item.id]
        uid = self.actor.id
        chain = ancestor_ids(WorkItemClosure, item.id, include_self=True) if item.id else []
        above = [i for i in chain if i != item.id]
        responsible_above = bool(above) and db.session.scalar(select(func.count()).select_from(WorkItemResponsible).where(
            WorkItemResponsible.work_item_id.in_(above), WorkItemResponsible.user_id == uid))
        accountable_in_chain = bool(chain) and db.session.scalar(select(func.count()).select_from(WorkItem).where(
            WorkItem.id.in_(chain), WorkItem.accountable_id == uid))
        managed = managed_unit_ids(self.actor)
        unit_manager = actor_can(self.actor, "work.manage") and (
            managed is None or (item.unit_id is not None and item.unit_id in managed))
        if unit_manager or accountable_in_chain or responsible_above:
            level = MANAGE
        elif uid in self.read_value(item, "responsible_ids") or db.session.scalar(
                select(Assignment.id).where(Assignment.work_item_id == item.id, Assignment.person_id == uid,
                                            Assignment.is_deleted.is_(False))):
            level = CONTRIBUTE
        else:
            level = VIEW
        self._access_cache[item.id] = level
        return level

    def can_add_child(self, item) -> bool:
        level = self.access(item)
        return level == MANAGE or (level == CONTRIBUTE and self.actor.id in self.read_value(item, "responsible_ids"))

    def ensure_manage(self, item, message="You cannot change this item"):
        if self.access(item) != MANAGE:
            raise Forbidden(message)

    def permissions_for(self, item) -> dict:
        level = self.access(item)
        return {
            "level": level,
            "can_edit": level in (MANAGE, CONTRIBUTE),
            "editable_fields": None if level == MANAGE else sorted(CONTRIBUTOR_FIELDS) if level == CONTRIBUTE else [],
            "can_add_child": self.can_add_child(item),
            "can_assign": level == MANAGE,
            "can_delete": level == MANAGE and not self.child_count(item),
            "can_complete": level in (MANAGE, CONTRIBUTE)
            and item.status_id not in closed_status_ids(self.tenant_id),
        }

    # ------------------------------------------------------------------ serialisation
    def _children_stats(self, item):
        closed = closed_status_ids(self.tenant_id)
        done = published_value_id(self.tenant_id, "status", "done")
        cancelled = published_value_id(self.tenant_id, "status", "cancelled")
        rows = db.session.execute(select(WorkItem.status_id, WorkItem.planned_end).where(
            WorkItem.parent_id == item.id, WorkItem.is_deleted.is_(False))).all()
        counted = [s for s, _ in rows if s != cancelled]
        overdue = sum(1 for s, end in rows if end and end < today() and s not in closed)
        return {"total": len(rows), "done": sum(1 for s in counted if s == done), "counted": len(counted),
                "overdue": overdue}

    def progress(self, item) -> int:
        """Validated, weighted progress (see app.modules.work.progress)."""
        return progress_map(self.tenant_id, [item.id]).get(item.id, 0)

    def is_overdue(self, item) -> bool:
        return bool(item.planned_end and item.planned_end < today()
                    and item.status_id not in closed_status_ids(self.tenant_id))

    def serialize(self, w: WorkItem, detail: bool = False) -> dict:
        stats = self._children_stats(w)
        responsibles = db.session.scalars(select(User).join(WorkItemResponsible, WorkItemResponsible.user_id == User.id)
                                          .where(WorkItemResponsible.work_item_id == w.id).order_by(User.full_name)).all()
        parent = db.session.get(WorkItem, w.parent_id) if w.parent_id else None
        out = {
            "id": w.id, "code": w.code, "title": w.title, "description": w.description,
            "item_type_id": w.item_type_id, "status_id": w.status_id, "priority_id": w.priority_id,
            "category_id": w.category_id, "action_type_id": w.action_type_id, "severity_id": w.severity_id,
            "parent_id": w.parent_id,
            "parent": {"id": parent.id, "code": parent.code, "title": parent.title} if parent else None,
            "unit": _ref(w.unit), "unit_id": w.unit_id, "function": _ref(w.function), "function_id": w.function_id,
            "accountable": person_ref(w.accountable), "accountable_id": w.accountable_id,
            "owner_overridden": w.owner_overridden,
            "responsibles": [person_ref(u) for u in responsibles], "responsible_ids": [u.id for u in responsibles],
            "planned_start": _iso(w.planned_start), "planned_end": _iso(w.planned_end),
            "actual_start": _iso(w.actual_start), "actual_end": _iso(w.actual_end),
            "progress_manual": w.progress_manual, "progress": self.progress(w), "weight": w.weight,
            "approval_status": w.approval_status, "approved_at": w.approved_at.isoformat() if w.approved_at else None,
            "child_count": stats["total"], "overdue_children": stats["overdue"], "is_overdue": self.is_overdue(w),
            "objective": w.objective, "risks": w.risks, "remarks": w.remarks, "evidence_url": w.evidence_url,
            "adoption_stage_ids": w.adoption_stage_ids or [], "adoption_evidence": w.adoption_evidence,
            "custom_fields": w.custom_fields or {},
            "custom_people": person_refs(self.tenant_id, self.custom_entity, w.custom_fields),
            "updated_at": w.updated_at.isoformat(), "version": w.version,
        }
        if detail:
            out["ancestors"] = self._visible_ancestors(w)
            out["dependencies"] = [
                {"id": d.id, "code": d.code, "title": d.title, "status_id": d.status_id}
                for d in db.session.scalars(self.base_query().where(WorkItem.id.in_(self.read_value(w, "depends_on_ids"))))]
            out["depends_on_ids"] = self.read_value(w, "depends_on_ids")
            out["permissions"] = self.permissions_for(w)
            out["approval"] = approval_summary(w.id)
            from app.modules.rules.service import health_detail

            out["health"] = health_detail(self.actor, self.tenant_id, w.id)
        return out

    def _visible_ancestors(self, w):
        ids = ancestor_ids(WorkItemClosure, w.id)
        visible = {a.id: a for a in db.session.scalars(self.base_query().where(WorkItem.id.in_(ids)))}
        # Ancestors the user may not open are still named in the trail, but without a link.
        return [{"id": i, "code": visible[i].code, "title": visible[i].title} if i in visible
                else {"id": None, "code": "…", "title": "Item you cannot open"} for i in ids]

    def detail(self, item_id: int) -> dict:
        return self.serialize(self.get(item_id), detail=True)

    def history(self, item_id: int, params) -> dict:
        item = self.get(item_id)
        assignment_ids = select(Assignment.id).where(Assignment.work_item_id == item.id)
        stmt = select(AuditEvent).where(AuditEvent.tenant_id == self.tenant_id, or_(
            (AuditEvent.entity_type == "work_item") & (AuditEvent.entity_id == item.id),
            (AuditEvent.entity_type == "assignment") & AuditEvent.entity_id.in_(assignment_ids),
        )).order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
        return paginate(stmt, params, serialize_event)

    # ------------------------------------------------------------------ linked values
    def read_value(self, obj, field):
        if field == "responsible_ids":
            if obj.id is None:
                return []
            return sorted(db.session.scalars(select(WorkItemResponsible.user_id)
                                             .where(WorkItemResponsible.work_item_id == obj.id)))
        if field == "depends_on_ids":
            if obj.id is None:
                return []
            return sorted(db.session.scalars(select(WorkItemDependency.depends_on_id)
                                             .where(WorkItemDependency.work_item_id == obj.id)))
        return super().read_value(obj, field)

    def apply_update(self, obj, changes):
        changes = dict(changes)
        if "responsible_ids" in changes:
            ids = changes.pop("responsible_ids")
            db.session.execute(delete(WorkItemResponsible).where(WorkItemResponsible.work_item_id == obj.id))
            db.session.add_all(WorkItemResponsible(work_item_id=obj.id, user_id=u) for u in ids)
        if "depends_on_ids" in changes:
            ids = changes.pop("depends_on_ids")
            db.session.execute(delete(WorkItemDependency).where(WorkItemDependency.work_item_id == obj.id))
            db.session.add_all(WorkItemDependency(work_item_id=obj.id, depends_on_id=d) for d in ids)
        self._access_cache.clear()
        old_status = obj.status_id
        if changes:
            super().apply_update(obj, changes)
        if "status_id" in changes and obj.id is not None:
            engine.on_status_change(self, obj, old_status, obj.status_id)

    def after_create(self, obj, data):
        super().after_create(obj, data)
        if obj.status_id is not None:  # created already finished: approval starts straight away
            db.session.flush()
            engine.on_status_change(self, obj, None, obj.status_id)

    def complete(self, item_id, *, evidence_url=None, actual_end=None, remarks=None, reason=None):
        """Mark an item complete ("I have finished this"); starts its approval if it needs one."""
        item = self.get(item_id)
        done = published_value_id(self.tenant_id, "status", "done")
        if done is None:
            raise ValidationFailed("There is no “done” status in the Status list")
        changes = {"status_id": done, "actual_end": actual_end or item.actual_end or today()}
        if evidence_url:
            changes["evidence_url"] = evidence_url
        if remarks:
            changes["remarks"] = remarks
        return self.update(item_id, changes, reason=reason or "Marked complete")

    def custom_field_scope(self, context):
        item_type_id = context.get("item_type_id") if isinstance(context, dict) else getattr(context, "item_type_id", None)
        return {"item_type_id": item_type_id}

    # ------------------------------------------------------------------ writes
    def create(self, data, reason=None):
        self._reason = reason
        return super().create(data, reason=reason)

    def update(self, record_id, changes, *, expected_version=None, reason=None):
        self._reason = reason
        return super().update(record_id, changes, expected_version=expected_version, reason=reason)

    def _next_code(self, item_type_id):
        type_code = published_list(self.tenant_id, "item_type")[item_type_id]["code"]
        prefix = ITEM_PREFIX.get(type_code) or re.sub(r"[^A-Z]", "", type_code.upper())[:3] or "WI"
        used = db.session.scalars(select(WorkItem.code).where(
            WorkItem.tenant_id == self.tenant_id, WorkItem.code.like(f"{prefix}-%")))  # deleted codes are never reused
        numbers = [int(c.split("-", 1)[1]) for c in used if c.split("-", 1)[1].isdigit()]
        return f"{prefix}-{max(numbers, default=0) + 1:03d}"

    def _check_unit(self, unit_id, parent):
        """Work is pushed DOWN the hierarchy: a child goes to its parent's unit or a unit below it;
        top-level work goes to a unit the actor manages (or anywhere, for organisation-wide roles)."""
        if unit_id is None:
            return
        unit = db.session.get(OrgUnit, unit_id)
        if unit is None or unit.tenant_id != self.tenant_id or unit.is_deleted:
            raise ValidationFailed("Unit not found", {"field": "unit_id"})
        if self.actor is None or is_global(self.actor):
            return
        if parent is not None and parent.unit_id is not None:
            if unit_id not in descendant_ids(OrgUnitClosure, [parent.unit_id]):
                raise ValidationFailed("Assign it to the parent's unit or a unit below it", {"field": "unit_id"})
            return
        managed = managed_unit_ids(self.actor) or set()
        if unit_id not in managed:
            raise Forbidden("You can only assign work to units within your own area")

    def _check_function(self, function_id):
        if function_id is None:
            return
        fn = db.session.get(Function, function_id)
        if fn is None or fn.tenant_id != self.tenant_id or fn.is_deleted:
            raise ValidationFailed("Function not found", {"field": "function_id"})

    def _check_adoption(self, ids, previous=()):
        """Adoption stages reached: values of the "adoption_stage" list (retired ones only if already set)."""
        ids = sorted({int(i) for i in ids or []})
        stages = published_list(self.tenant_id, "adoption_stage")
        for i in ids:
            if i not in stages or (not stages[i]["is_active"] and i not in (previous or ())):
                raise ValidationFailed("Choose stages from the Adoption stage list", {"field": "adoption_stage_ids"})
        return ids or None

    def _check_responsibles(self, ids):
        ids = sorted(set(ids or []))
        if not ids:
            raise ValidationFailed("Choose at least one responsible owner", {"field": "responsible_ids"})
        for pid in ids:
            self._check_person(pid, "responsible_ids")
        return ids

    def _check_dependencies(self, item_id, ids):
        ids = sorted(set(ids or []))
        if item_id is not None and item_id in ids:
            raise ValidationFailed("An item cannot depend on itself", {"field": "depends_on_ids"})
        found = set(db.session.scalars(_live_items(self.tenant_id).where(WorkItem.id.in_(ids))))
        if found != set(ids):
            raise ValidationFailed("Dependency not found", {"field": "depends_on_ids"})
        if item_id is not None:  # walk what the new dependencies depend on: no loops
            frontier, seen = set(ids), set()
            while frontier:
                if item_id in frontier:
                    raise ValidationFailed("This would create a circular dependency", {"field": "depends_on_ids"})
                seen |= frontier
                frontier = set(db.session.scalars(select(WorkItemDependency.depends_on_id).where(
                    WorkItemDependency.work_item_id.in_(frontier)))) - seen
        return ids

    def validate_create(self, data):
        parent = None
        if data.get("parent_id") is not None:
            parent = self.get(data["parent_id"])  # must be visible
            if not self.can_add_child(parent):
                raise Forbidden("You cannot add items under this one")
        else:
            ensure_can(self.actor, "work.create", "You do not have permission to create top-level work")
        super().validate_create(data)  # parent exists in this tenant

        if data.get("item_type_id") is None:
            raise ValidationFailed("Choose an item type", {"field": "item_type_id"})
        if data.get("weight") is None:
            data.pop("weight", None)  # empty = the default weight of 1
        for field in LOOKUP_FIELDS:
            self._check_lookup(field, data.get(field))

        # Inherit from the parent unless given.
        if parent is not None:
            for field in ("unit_id", "priority_id", "category_id", "function_id"):
                if data.get(field) is None:
                    data[field] = getattr(parent, field)
        if data.get("status_id") is None:
            data["status_id"] = next((v["id"] for v in published_list(self.tenant_id, "status").values()
                                      if v["is_default"] and v["is_active"]), None)
        self._check_unit(data.get("unit_id"), parent)
        self._check_function(data.get("function_id"))

        # Ownership: exactly one accountable owner, inherited unless deliberately overridden (with a reason).
        inherited = parent.accountable_id if parent else getattr(self.actor, "id", None)
        if data.get("accountable_id") is None:
            data["accountable_id"] = inherited
        if data["accountable_id"] is None:
            raise ValidationFailed("Choose the accountable owner", {"field": "accountable_id"})
        self._check_person(data["accountable_id"], "accountable_id")
        if parent is not None and data["accountable_id"] != parent.accountable_id:
            if not self._reason:
                raise ValidationFailed("Give a reason for choosing a different accountable owner than the parent's",
                                       {"field": "reason"})
            data["owner_overridden"] = True
        if data.get("responsible_ids") is None:
            data["responsible_ids"] = self.read_value(parent, "responsible_ids") if parent else [data["accountable_id"]]
        data["responsible_ids"] = self._check_responsibles(data["responsible_ids"])
        if data.get("depends_on_ids"):
            data["depends_on_ids"] = self._check_dependencies(None, data["depends_on_ids"])
        else:
            data.pop("depends_on_ids", None)

        if "adoption_stage_ids" in data:
            data["adoption_stage_ids"] = self._check_adoption(data["adoption_stage_ids"])
        self._check_dates(data.get("planned_start"), data.get("planned_end"), "planned_end")
        self._check_dates(data.get("actual_start"), data.get("actual_end"), "actual_end")
        data["code"] = self._next_code(data["item_type_id"])

    def validate_update(self, obj, changes):
        for field in self.extra_fields & set(changes):  # linked lists compare as sorted sets
            changes[field] = sorted(set(changes[field] or []))
        if "adoption_stage_ids" in changes:
            changes["adoption_stage_ids"] = self._check_adoption(changes["adoption_stage_ids"], obj.adoption_stage_ids)
            if changes["adoption_stage_ids"] == (sorted(obj.adoption_stage_ids) if obj.adoption_stage_ids else None):
                changes.pop("adoption_stage_ids")
        if "weight" in changes and changes["weight"] is None:
            changes.pop("weight")  # empty box on the form = leave the weight as it is
        level = self.access(obj)
        changed = {f for f, v in changes.items() if self.read_value(obj, f) != v}
        if level == VIEW:
            raise Forbidden("You cannot change this item")
        if level == CONTRIBUTE and changed - CONTRIBUTOR_FIELDS:
            raise Forbidden("You can only update the status, actual dates, progress, evidence and remarks of this item",
                            {"fields": sorted(changed - CONTRIBUTOR_FIELDS)})
        super().validate_update(obj, changes)  # parent exists, no loops

        for field in LOOKUP_FIELDS:
            if field in changed:
                if field == "item_type_id" and changes[field] is None:
                    raise ValidationFailed("Choose an item type", {"field": field})
                self._check_lookup(field, changes[field], previous=getattr(obj, field))

        new_parent_id = changes.get("parent_id", obj.parent_id)
        parent = db.session.get(WorkItem, new_parent_id) if new_parent_id else None
        if "parent_id" in changed:
            if parent is None:
                ensure_can(self.actor, "work.create", "You do not have permission to make this a top-level item")
            elif not self.can_add_child(self.get(parent.id)):
                raise Forbidden("You cannot move items under that one")
        if "unit_id" in changed or "parent_id" in changed:
            self._check_unit(changes.get("unit_id", obj.unit_id), parent)
        if "function_id" in changed:
            self._check_function(changes["function_id"])
        if "accountable_id" in changed:
            if changes["accountable_id"] is None:
                raise ValidationFailed("An item must have an accountable owner", {"field": "accountable_id"})
            self._check_person(changes["accountable_id"], "accountable_id")
            if not self._reason:
                raise ValidationFailed("Give a reason for the handover", {"field": "reason"})
            changes["owner_overridden"] = bool(parent and changes["accountable_id"] != parent.accountable_id)
        if "responsible_ids" in changes:
            changes["responsible_ids"] = self._check_responsibles(changes["responsible_ids"])
        if "depends_on_ids" in changes:
            changes["depends_on_ids"] = self._check_dependencies(obj.id, changes["depends_on_ids"])

        merged = lambda f: changes.get(f, getattr(obj, f))  # noqa: E731
        self._check_dates(merged("planned_start"), merged("planned_end"), "planned_end")
        self._check_dates(merged("actual_start"), merged("actual_end"), "actual_end")

    def validate_delete(self, obj):
        self.ensure_manage(obj, "You cannot delete this item")
        super().validate_delete(obj)


class AssignmentService(_ChecksMixin, CommandService):
    """People working on an item: functional role, allocation % and dates. Only managers of the item may change them."""

    model = Assignment
    entity_type = "assignment"
    permissions = {"create": "work.view", "update": "work.view", "delete": "work.view"}
    protected_fields = frozenset({"work_item_id"})

    def _accepted_inputs(self):
        return {"work_item_id"}  # create only; protected on update

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.items = WorkItemService(self.actor, tenant_id=self.tenant_id, source=self.source,
                                     correlation_id=self.correlation_id)

    def base_query(self):
        visible = self.items.base_query().with_only_columns(WorkItem.id)
        return super().base_query().where(Assignment.work_item_id.in_(visible))

    def list_for(self, item_id):
        item = self.items.get(item_id)
        rows = db.session.scalars(self.base_query().where(Assignment.work_item_id == item.id)
                                  .order_by(Assignment.allocation_pct.desc(), Assignment.id)).all()
        load = allocation_load(self.tenant_id, {a.person_id for a in rows})
        return {"items": [self.serialize(a, load) for a in rows]}

    def serialize(self, a, load=None):
        load = load if load is not None else allocation_load(self.tenant_id, [a.person_id])
        return {
            "id": a.id, "work_item_id": a.work_item_id, "person": person_ref(a.person), "person_id": a.person_id,
            "role_id": a.role_id, "allocation_pct": a.allocation_pct,
            "start_date": _iso(a.start_date), "end_date": _iso(a.end_date), "duties": a.duties,
            "person_load": load.get(a.person_id), "version": a.version,
        }

    def _check(self, data, existing=None):
        if "person_id" in data:
            self._check_person(data["person_id"], "person_id")
        if "role_id" in data:
            self._check_lookup("role_id", data["role_id"], previous=getattr(existing, "role_id", None),
                               list_code="functional_role")
        start = data.get("start_date", getattr(existing, "start_date", None))
        end = data.get("end_date", getattr(existing, "end_date", None))
        self._check_dates(start, end, "end_date")

    def _check_unique(self, item_id, person_id, exclude_id=None):
        stmt = select(Assignment.id).where(Assignment.work_item_id == item_id, Assignment.person_id == person_id,
                                           Assignment.is_deleted.is_(False))
        if exclude_id:
            stmt = stmt.where(Assignment.id != exclude_id)
        if db.session.scalar(stmt):
            raise ValidationFailed("This person is already assigned to this item", {"field": "person_id"})

    def validate_create(self, data):
        item = self.items.get(data["work_item_id"])
        self.items.ensure_manage(item, "Only the item's managers can assign people")
        if data.get("person_id") is None:
            raise ValidationFailed("Choose a person", {"field": "person_id"})
        self._check(data)
        self._check_unique(item.id, data["person_id"])

    def validate_update(self, obj, changes):
        if changes.get("work_item_id", obj.work_item_id) != obj.work_item_id:
            raise ValidationFailed("An assignment cannot move to another item", {"field": "work_item_id"})
        changes.pop("work_item_id", None)
        self.items.ensure_manage(self.items.get(obj.work_item_id), "Only the item's managers can change assignments")
        self._check(changes, obj)
        if changes.get("person_id") not in (None, obj.person_id):
            self._check_unique(obj.work_item_id, changes["person_id"], obj.id)

    def validate_delete(self, obj):
        self.items.ensure_manage(self.items.get(obj.work_item_id), "Only the item's managers can remove assignments")


def _iso(d):
    return d.isoformat() if d else None


def approval_summary(item_id: int) -> dict | None:
    """The latest approval request of an item, in brief, for headers and lists."""
    from app.modules.workflows.models import ApprovalRequest

    r = db.session.scalar(select(ApprovalRequest).where(ApprovalRequest.work_item_id == item_id,
                                                        ApprovalRequest.is_deleted.is_(False))
                          .order_by(ApprovalRequest.id.desc()))
    if r is None:
        return None
    step = r.steps[r.current_step] if r.status == "pending" and r.current_step < len(r.steps) else None
    return {
        "id": r.id, "status": r.status, "chain_name": r.chain_name, "step_count": len(r.steps),
        "current_step": r.current_step + 1 if step else None, "step_name": step["name"] if step else None,
        "current_approver": person_ref(r.current_approver) if step else None,
        "current_role": engine.role_name(r.current_role_id) if step else None,
        "waiting_note": r.waiting_note,
    }


def unit_rollup(actor, unit_id: int) -> dict:
    """Weighted progress of the top-most visible items in a unit and the units below it, plus counts.
    "Top-most" = items whose parent is not itself in that set, so nothing is counted twice."""
    from app.modules.work.progress import weighted_average

    svc = WorkItemService(actor)
    units = descendant_ids(OrgUnitClosure, [unit_id])
    items = db.session.scalars(svc.base_query().where(WorkItem.unit_id.in_(units))).all()
    ids = {i.id for i in items}
    tops = [i for i in items if i.parent_id not in ids]
    progress = progress_map(svc.tenant_id, [i.id for i in tops])
    closed = closed_status_ids(svc.tenant_id)
    return {
        "unit_id": unit_id,
        "progress": weighted_average(tops, progress),
        "items": len(items),
        "top_level_items": len(tops),
        "open_items": sum(1 for i in items if i.status_id not in closed),
        "overdue_items": sum(1 for i in items if svc.is_overdue(i)),
        "awaiting_approval": sum(1 for i in items if i.approval_status == "pending"),
    }
