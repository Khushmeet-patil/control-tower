"""Read API for Power BI and other reporting tools: flat tables, one row per record, labels written out.

    GET /api/v1/reporting                     the list of datasets
    GET /api/v1/reporting/<dataset>           JSON {"dataset", "generated_at", "rows": [...]}
    GET /api/v1/reporting/<dataset>?format=csv

Datasets: work-items (every level, with parent and health), assignments, people, units.
Authenticate with an API token (header "Authorization: Bearer ct_…", scope "read"); in Power BI use
Get data → Web → Advanced, and add that header. Every dataset is limited to what the token's owner may
see, exactly like the screens, so a report never shows more than its owner could open.
"""
import csv
import io
from datetime import date, datetime

from sqlalchemy import select

from app.core.errors import NotFound
from app.core.models import utcnow
from app.extensions import db
from app.modules.config.versioning import published_fields
from app.modules.snapshots.exports import Labels

DATASETS = {
    "work-items": "Work items at every level, with owners, dates, progress and health",
    "assignments": "Who works on what: role, allocation % and dates",
    "people": "People you can see, with unit, function, manager and capacity",
    "units": "Organisation units, with their parent and head",
}


def catalog() -> dict:
    return {"datasets": [{"code": k, "description": v, "url": f"/api/v1/reporting/{k}"} for k, v in DATASETS.items()]}


def _iso(v):
    return v.isoformat() if isinstance(v, (date, datetime)) else v


def work_items(actor) -> list[dict]:
    from app.modules.rules import engine
    from app.modules.work.models import WorkItem, WorkItemResponsible
    from app.modules.work.progress import progress_map
    from app.modules.work.service import WorkItemService, closed_status_ids

    labels = Labels(actor.tenant_id)
    svc = WorkItemService(actor)
    items = db.session.scalars(svc.base_query().order_by(WorkItem.code)).all()
    ids = [w.id for w in items]
    progress = progress_map(actor.tenant_id, ids)
    health = engine.evaluate(actor.tenant_id, ids) if ids else {}
    codes = {w.id: w.code for w in items}
    responsible = {}
    from app.modules.auth.models import User

    for item_id, name in db.session.execute(
            select(WorkItemResponsible.work_item_id, User.full_name)
            .join(User, User.id == WorkItemResponsible.user_id)
            .where(WorkItemResponsible.work_item_id.in_(ids or [0]))):
        responsible.setdefault(item_id, []).append(name)
    fields = [f for f in published_fields(actor.tenant_id, "work_item") if f.get("is_active", True)]
    closed = set(closed_status_ids(actor.tenant_id))
    rows = []
    for w in items:
        h = health.get(w.id)
        row = {
            "id": w.id, "code": w.code, "title": w.title, "type": labels.label(w.item_type_id),
            "parent_id": w.parent_id, "parent_code": codes.get(w.parent_id), "status": labels.label(w.status_id),
            "priority": labels.label(w.priority_id), "category": labels.label(w.category_id),
            "unit": w.unit.name if w.unit else None, "unit_id": w.unit_id,
            "function": w.function.name if w.function else None,
            "accountable": w.accountable.full_name if w.accountable else None, "accountable_id": w.accountable_id,
            "responsible": "; ".join(sorted(responsible.get(w.id, []))),
            "planned_start": _iso(w.planned_start), "planned_end": _iso(w.planned_end),
            "actual_start": _iso(w.actual_start), "actual_end": _iso(w.actual_end),
            "progress": progress.get(w.id, 0), "weight": w.weight,
            "health": labels.health_label(h.health if h else None),
            "health_reason": h.top.reason if h and h.top else None,
            "approval_status": w.approval_status, "is_open": w.status_id not in closed,
            "is_overdue": svc.is_overdue(w), "updated_at": _iso(w.updated_at),
        }
        for f in fields:
            value = (w.custom_fields or {}).get(f["code"])
            if f["field_type"] in ("select",) and isinstance(value, int):
                value = labels.label(value)
            elif f["field_type"] == "multi_select" and isinstance(value, list):
                value = "; ".join(str(labels.label(v) or v) for v in value)
            row[f"cf_{f['code']}"] = value
        rows.append(row)
    return rows


def assignments(actor) -> list[dict]:
    from app.modules.work.models import Assignment, WorkItem
    from app.modules.work.service import AssignmentService

    labels = Labels(actor.tenant_id)
    svc = AssignmentService(actor)
    rows = []
    for a in db.session.scalars(svc.base_query().order_by(Assignment.id)):
        item = db.session.get(WorkItem, a.work_item_id)
        rows.append({"id": a.id, "work_item_id": a.work_item_id, "work_item_code": item.code if item else None,
                     "person_id": a.person_id, "person": a.person.full_name if a.person else None,
                     "role": labels.label(a.role_id), "allocation_pct": a.allocation_pct,
                     "start_date": _iso(a.start_date), "end_date": _iso(a.end_date), "duties": a.duties})
    return rows


def people(actor) -> list[dict]:
    from app.modules.auth.models import User
    from app.modules.people.service import PersonService

    svc = PersonService(actor)
    return [{"id": u.id, "full_name": u.full_name, "email": u.email, "job_title": u.job_title,
             "unit": u.unit.name if u.unit else None, "unit_id": u.unit_id,
             "function": u.function.name if u.function else None, "manager_id": u.manager_id,
             "capacity_pct": u.capacity_pct, "is_active": u.is_active}
            for u in db.session.scalars(svc.base_query().order_by(User.full_name))]


def units(actor) -> list[dict]:
    from app.modules.organisation.models import OrgUnit
    from app.modules.organisation.service import UnitService

    svc = UnitService(actor)
    return [{"id": u.id, "code": u.code, "name": u.name, "parent_id": u.parent_id, "head_id": u.head_id}
            for u in db.session.scalars(svc.base_query().order_by(OrgUnit.name))]


BUILDERS = {"work-items": work_items, "assignments": assignments, "people": people, "units": units}


def dataset(actor, code: str) -> dict:
    if code not in BUILDERS:
        raise NotFound("No such dataset")
    return {"dataset": code, "generated_at": utcnow().isoformat(), "rows": BUILDERS[code](actor)}


def to_csv(rows: list[dict]) -> bytes:
    from app.modules.snapshots.exports import _safe_csv

    buf = io.StringIO()
    if rows:
        writer = csv.DictWriter(buf, fieldnames=list(rows[0]))
        writer.writeheader()
        for r in rows:
            writer.writerow({k: "" if v is None else _safe_csv(v) for k, v in r.items()})
    return ("﻿" + buf.getvalue()).encode("utf-8")
