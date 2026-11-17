"""What can be imported, the columns of each template, and how a row becomes a service call.

Each row goes through the same service as the screen (PersonService, WorkItemService,
AssignmentService, DemandService), so permissions, validation, scope and the audit log apply exactly
as for a person typing it in. Rows are identified like this:

    people        Email
    work items    Code (e.g. PRJ-004, to update an existing item) or External ID (the spreadsheet's own ID)
    assignments   Item + Person
    requests      Code (REQ-001) or External ID

References accept what people write in spreadsheets: people by email (or a unique full name), units
and functions by code or name, lookups (status, priority…) by label or code, parents by code or by
another row's External ID. Custom fields have a column each, named by their label.
"""
import re
import secrets
from dataclasses import dataclass, field

from sqlalchemy import func, select

from app.extensions import db
from app.modules.access.models import Role
from app.modules.auth.models import User
from app.modules.config.versioning import published_fields, published_list
from app.modules.imports.models import ExternalKey
from app.modules.imports.parsing import CellError, normalise, parse_bool, parse_date, parse_int, split_list, text
from app.modules.organisation.models import Function, OrgUnit

EXAMPLE_PREFIX = "EXAMPLE"


class RowInvalid(Exception):
    def __init__(self, errors):
        super().__init__("invalid row")
        self.errors = errors  # [{"column": label | None, "message": str}]


@dataclass
class Col:
    key: str
    label: str
    kind: str                 # text · email · int · bool · date · person · people · unit · function · roles ·
    field: str | None = None  # lookup · lookups · item · ext
    required: bool = False
    lookup: str | None = None
    max_len: int | None = None
    low: int | None = None
    high: int | None = None
    help: str = ""


@dataclass
class Entity:
    code: str
    label: str
    columns: list
    custom_entity: str | None = None
    identity: str = ""
    order_note: str = ""
    examples: list = field(default_factory=list)

    def col(self, key):
        return next(c for c in self.columns if c.key == key)


# ---------------------------------------------------------------------- definitions
PEOPLE = Entity("people", "People", [
    Col("email", "Email", "email", "email", required=True, help="Identifies the person; used to sign in."),
    Col("full_name", "Full name", "text", "full_name", required=True, max_len=200),
    Col("job_title", "Job title", "text", "job_title", max_len=200),
    Col("employee_code", "Employee code", "text", "employee_code", max_len=50),
    Col("unit", "Unit", "unit", "unit_id", help="Unit code or name."),
    Col("function", "Function", "function", "function_id", help="Function code or name."),
    Col("manager", "Reports to", "person", "manager_id", help="Their manager's email. Managers may be earlier in the file."),
    Col("roles", "Roles", "roles", "role_ids", help="Role names, separated by commas. Empty = the default role."),
    Col("skills", "Skills", "lookups", "skill_ids", lookup="skill"),
    Col("capacity", "Capacity %", "int", "capacity_pct", low=0, high=100, help="100 = full time."),
    Col("backlog", "Backlog days", "int", "backlog_days", low=0, high=10000),
    Col("active", "Active", "bool", "is_active", help="Yes or No. Empty = Yes."),
    Col("password", "Initial password", "text", "password", max_len=200,
        help="Optional, at least 8 characters. Empty = a random one; reset it from People before they sign in."),
], custom_entity="person", identity="Email",
    examples=[{"email": "EXAMPLE.priya@company.com", "full_name": "Priya Sharma", "job_title": "Business Analyst",
               "unit": "Platform Team", "manager": "karan@company.com", "roles": "Contributor", "capacity": 100}])

WORK = Entity("work_items", "Work items", [
    Col("external_id", "External ID", "ext", help="Your spreadsheet's ID (e.g. INI-001). Import again to update the same item."),
    Col("code", "Code", "text", help="Control Tower's code (e.g. PRJ-004), to update an existing item."),
    Col("type", "Type", "lookup", "item_type_id", required=True, lookup="item_type"),
    Col("title", "Title", "text", "title", required=True, max_len=300),
    Col("parent", "Parent", "item", "parent_id", help="Code or External ID of the parent; parents may be earlier or later in the file."),
    Col("unit", "Unit", "unit", "unit_id", help="Unit code or name. Empty = the parent's."),
    Col("function", "Function", "function", "function_id"),
    Col("accountable", "Accountable", "person", "accountable_id", help="Email. Empty = the parent's owner, or you."),
    Col("responsible", "Responsible", "people", "responsible_ids", help="Emails, separated by commas."),
    Col("status", "Status", "lookup", "status_id", lookup="status"),
    Col("priority", "Priority", "lookup", "priority_id", lookup="priority"),
    Col("category", "Category", "lookup", "category_id", lookup="category"),
    Col("action_type", "Action type", "lookup", "action_type_id", lookup="action_type", help="Actions only."),
    Col("severity", "Severity", "lookup", "severity_id", lookup="severity", help="Actions only."),
    Col("planned_start", "Planned start", "date", "planned_start"),
    Col("planned_end", "Planned finish", "date", "planned_end"),
    Col("actual_start", "Actual start", "date", "actual_start"),
    Col("actual_end", "Actual finish", "date", "actual_end"),
    Col("progress", "Progress %", "int", "progress_manual", low=0, high=100, help="Only used while it has no child items."),
    Col("weight", "Weight", "int", "weight", low=0, high=1000),
    Col("description", "Description", "text", "description"),
    Col("objective", "Business objective", "text", "objective"),
    Col("risks", "Key risks", "text", "risks"),
    Col("remarks", "Remarks", "text", "remarks"),
    Col("evidence_url", "Evidence link", "text", "evidence_url", max_len=500),
], custom_entity="work_item", identity="Code or External ID",
    order_note="Parents are created before their children, wherever they are in the file.",
    examples=[{"external_id": "EXAMPLE-INI-1", "type": "Project", "title": "Customer self-service portal",
               "unit": "Engineering", "accountable": "meera@company.com", "priority": "High",
               "planned_start": "2026-01-05", "planned_end": "30/06/2026"},
              {"external_id": "EXAMPLE-MS-1", "type": "Milestone", "title": "Design signed off", "parent": "EXAMPLE-INI-1",
               "responsible": "karan@company.com", "planned_end": "15-Feb-2026"}])

ASSIGNMENTS = Entity("assignments", "Assignments", [
    Col("item", "Item", "item", "work_item_id", required=True, help="Code or External ID of the work item."),
    Col("person", "Person", "person", "person_id", required=True, help="Email."),
    Col("role", "Role", "lookup", "role_id", lookup="functional_role"),
    Col("allocation", "Allocation %", "int", "allocation_pct", required=True, low=0, high=100),
    Col("start", "Start", "date", "start_date"),
    Col("end", "End", "date", "end_date"),
    Col("duties", "Duties", "text", "duties"),
], identity="Item + Person",
    examples=[{"item": "EXAMPLE-INI-1", "person": "arjun@company.com", "role": "Contributor", "allocation": 40}])

DEMAND = Entity("demand", "Requests", [
    Col("external_id", "External ID", "ext"),
    Col("code", "Code", "text", help="REQ-… to update an existing request."),
    Col("title", "Request", "text", "title", required=True, max_len=300),
    Col("description", "Description", "text", "description"),
    Col("requester", "Requester", "person", "requester_id", help="Email. Empty = you."),
    Col("sponsor", "Sponsor", "text", "sponsor", max_len=200),
    Col("business_value", "Business value", "text", "business_value"),
    Col("urgency", "Urgency", "lookup", "urgency_id", lookup="urgency"),
    Col("priority", "Priority", "lookup", "priority_id", lookup="priority"),
    Col("effort", "Effort (points)", "int", "effort_pct", low=0, high=100000, help="1 point = 1% of one person's week."),
    Col("requested_on", "Requested on", "date", "requested_on"),
    Col("needed_by", "Needed by", "date", "needed_by"),
    Col("unit", "Delivering unit", "unit", "unit_id"),
    Col("dependencies", "Dependencies", "text", "dependencies"),
    Col("remarks", "Remarks", "text", "remarks"),
], identity="Code or External ID",
    examples=[{"external_id": "EXAMPLE-REQ-1", "title": "Invoice export", "requester": "ravi@company.com",
               "priority": "Medium", "effort": 60, "needed_by": "2026-09-30"}])

ENTITIES = {e.code: e for e in (PEOPLE, WORK, ASSIGNMENTS, DEMAND)}


# ---------------------------------------------------------------------- resolving references
class Context:
    """Looks things up for one import run. Only settings are cached; records are always read fresh,
    because rows earlier in the file may have created them (or been rolled back)."""

    def __init__(self, actor, tenant_id, *, correlation_id, mode, filename):
        self.actor, self.tenant_id, self.mode, self.filename = actor, tenant_id, mode, filename
        self.correlation_id = correlation_id
        self._lists = {}

    def service(self, cls):
        return cls(self.actor, tenant_id=self.tenant_id, source="import", correlation_id=self.correlation_id)

    @property
    def reason(self):
        return f"Imported from {self.filename}"

    def person(self, value):
        v = str(value).strip()
        base = select(User.id).where(User.tenant_id == self.tenant_id, User.is_deleted.is_(False))
        found = db.session.scalar(base.where(func.lower(User.email) == v.lower()))
        if found:
            return found
        named = db.session.scalars(base.where(func.lower(User.full_name) == v.lower())).all()
        if len(named) == 1:
            return named[0]
        raise CellError(f"No person with email “{v}”" if len(named) == 0 else f"Several people are called “{v}”; use their email")

    def _named(self, model, value, what):
        v = str(value).strip()
        rows = db.session.execute(select(model.id, model.code, model.name).where(
            model.tenant_id == self.tenant_id, model.is_deleted.is_(False))).all()
        by_code = [r.id for r in rows if (r.code or "").lower() == v.lower()]
        by_name = [r.id for r in rows if normalise(r.name) == normalise(v)]
        found = by_code or by_name
        if len(found) == 1:
            return found[0]
        raise CellError(f"No {what} with code or name “{v}”" if not found else f"Several {what}s are called “{v}”; use the code")

    def unit(self, value):
        return self._named(OrgUnit, value, "unit")

    def function(self, value):
        return self._named(Function, value, "function")

    def role(self, value):
        v = str(value).strip()
        rows = db.session.execute(select(Role.id, Role.code, Role.name).where(
            Role.tenant_id == self.tenant_id, Role.is_deleted.is_(False))).all()
        found = [r.id for r in rows if (r.code or "").lower() == v.lower() or normalise(r.name) == normalise(v)]
        if len(found) != 1:
            raise CellError(f"No role called “{v}”")
        return found[0]

    def lookup(self, list_code, value, *, current=None):
        if list_code not in self._lists:
            self._lists[list_code] = published_list(self.tenant_id, list_code)
        values = self._lists[list_code]
        v = normalise(value)
        match = [x for x in values.values() if normalise(x["label"]) == v or normalise(x["code"]) == v]
        active = [x for x in match if x["is_active"] or x["id"] == current]
        if active:
            return active[0]["id"]
        allowed = ", ".join(x["label"] for x in values.values() if x["is_active"])
        raise CellError(f"“{value}” is not one of: {allowed}" if allowed else f"There is no “{list_code}” list")

    def external(self, entity_type, external_id):
        return db.session.scalar(select(ExternalKey.record_id).where(
            ExternalKey.tenant_id == self.tenant_id, ExternalKey.entity_type == entity_type,
            ExternalKey.external_id == external_id))

    def remember(self, entity_type, external_id, record_id):
        if external_id and not self.external(entity_type, external_id):
            db.session.add(ExternalKey(tenant_id=self.tenant_id, entity_type=entity_type, external_id=external_id,
                                       record_id=record_id))
            from app.core.audit import record_event

            record_event(tenant_id=self.tenant_id, actor=self.actor, entity_type=entity_type, entity_id=record_id,
                         operation="update", field="external_id", new=external_id, reason=self.reason, source="import",
                         correlation_id=self.correlation_id)

    def work_item(self, value):
        from app.modules.work.models import WorkItem

        v = str(value).strip()
        found = db.session.scalar(select(WorkItem.id).where(
            WorkItem.tenant_id == self.tenant_id, WorkItem.is_deleted.is_(False), func.upper(WorkItem.code) == v.upper()))
        found = found or self.external("work_item", v)
        if not found:
            raise CellError(f"No work item with code or External ID “{v}”")
        return found


# ---------------------------------------------------------------------- converting a row
def custom_columns(entity: Entity, tenant_id) -> dict[str, dict]:
    """{normalised header: custom field} for the entity's published custom fields (by label or code)."""
    if not entity.custom_entity:
        return {}
    out = {}
    for f in published_fields(tenant_id, entity.custom_entity):
        out[normalise(f["label"])] = f
        out.setdefault(normalise(f["code"]), f)
    return out


def _convert(ctx: Context, col: Col, raw, current=None):
    k = col.kind
    if k in ("text", "ext"):
        return text(raw, col.max_len)
    if k == "email":
        v = text(raw, 254)
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v or ""):
            raise CellError(f"“{raw}” is not an email address")
        return v.lower()
    if k == "int":
        return parse_int(raw, low=col.low, high=col.high)
    if k == "bool":
        return parse_bool(raw)
    if k == "date":
        return parse_date(raw)
    if k == "person":
        return ctx.person(raw)
    if k == "people":
        return sorted({ctx.person(p) for p in split_list(raw)})
    if k == "unit":
        return ctx.unit(raw)
    if k == "function":
        return ctx.function(raw)
    if k == "roles":
        return sorted({ctx.role(p) for p in split_list(raw)})
    if k == "lookup":
        return ctx.lookup(col.lookup, raw, current=current)
    if k == "lookups":
        return sorted({ctx.lookup(col.lookup, p) for p in split_list(raw)})
    if k == "item":
        return ctx.work_item(raw)
    raise CellError(f"Unknown column kind {k}")


def _custom_value(ctx, f, raw):
    kind = f["field_type"]
    if kind == "number":
        number = float(str(raw).replace(",", "")) if not isinstance(raw, (int, float)) else raw
        return int(number) if float(number).is_integer() else number
    if kind == "date":
        return parse_date(raw).isoformat()
    if kind in ("select", "multi_select"):
        values = published_list_by_type(ctx.tenant_id, f["lookup_type_id"])
        ids = []
        for part in (split_list(raw) if kind == "multi_select" else [raw]):
            match = [v["id"] for v in values if normalise(v["label"]) == normalise(part) or normalise(v["code"]) == normalise(part)]
            if not match:
                raise CellError(f"“{part}” is not one of: {', '.join(v['label'] for v in values if v['is_active'])}")
            ids.append(match[0])
        return ids if kind == "multi_select" else ids[0]
    if kind == "person":
        return ctx.person(raw)
    return text(raw)


def published_list_by_type(tenant_id, lookup_type_id):
    from app.modules.config.versioning import published_values

    return list(published_values(tenant_id, lookup_type_id).values())


def convert_row(ctx: Context, entity: Entity, values: dict, custom: dict) -> tuple[dict, dict]:
    """Cells → ({column key: value}, {custom field code: value}). Empty cells are left out.
    Raises RowInvalid listing every bad cell, not just the first."""
    errors, out, extra = [], {}, {}
    for col in entity.columns:
        raw = values.get(col.key)
        if raw is None:
            continue
        try:
            out[col.key] = _convert(ctx, col, raw)
        except CellError as exc:
            errors.append({"column": col.label, "message": str(exc)})
    for header, raw in values.items():
        if header.startswith("cf:") and raw is not None:
            f = custom[header[3:]]
            try:
                extra[f["code"]] = _custom_value(ctx, f, raw)
            except (CellError, ValueError) as exc:
                errors.append({"column": f["label"], "message": str(exc) if isinstance(exc, CellError) else "Enter a number"})
    if errors:
        raise RowInvalid(errors)
    return out, extra


def _missing(entity, out, creating):
    if not creating:
        return []
    return [{"column": c.label, "message": "Required"} for c in entity.columns if c.required and out.get(c.key) is None]


# ---------------------------------------------------------------------- applying a row
def identity_of(entity: Entity, values: dict) -> str:
    keys = {"people": ["email"], "work_items": ["code", "external_id"], "assignments": ["item", "person"],
            "demand": ["code", "external_id"]}[entity.code]
    parts = [str(values[k]) for k in keys if values.get(k) is not None]
    return " / ".join(parts) or "(no ID)"


def is_example(entity: Entity, values: dict) -> bool:
    keys = {"people": "email", "work_items": "external_id", "assignments": "item", "demand": "external_id"}[entity.code]
    return str(values.get(keys) or "").upper().startswith(EXAMPLE_PREFIX)


def apply_row(ctx: Context, entity: Entity, values: dict, custom: dict) -> dict:
    """Create or update one record. Returns {"action": "create"|"update"|"unchanged", "record": {...}}."""
    out, extra = convert_row(ctx, entity, values, custom)
    return {"people": _people, "work_items": _work, "assignments": _assignment, "demand": _demand}[entity.code](
        ctx, entity, out, extra)


def _fields(entity, out, skip=()):
    data = {c.field: out[c.key] for c in entity.columns if c.field and c.key in out and c.key not in skip}
    return data


def _existing_check(ctx, existing, label):
    if existing and ctx.mode == "add":
        raise RowInvalid([{"column": label, "message": "Already exists (choose “Add and update” to update it)"}])


def _save(ctx, svc, existing, data, extra, *, entity, out):
    if extra:
        data["custom_fields"] = extra
    if existing is None:
        if missing := _missing(entity, out, True):
            raise RowInvalid(missing)
        return "create", svc.create(data, reason=ctx.reason)
    before = existing.version
    obj = svc.update(existing.id, data, reason=ctx.reason)
    return ("update" if obj.version != before else "unchanged"), obj


def _people(ctx, entity, out, extra):
    from app.modules.people.service import PersonService

    svc = ctx.service(PersonService)
    existing = db.session.scalar(select(User).where(User.tenant_id == ctx.tenant_id, User.is_deleted.is_(False),
                                                    func.lower(User.email) == (out.get("email") or "").lower()))
    _existing_check(ctx, existing, "Email")
    data = _fields(entity, out, skip=("password",) if existing else ())
    if existing is None:
        data["password"] = out.get("password") or secrets.token_urlsafe(18)
        if data.get("role_ids") == []:
            data.pop("role_ids")
    else:
        data.pop("email", None)
    action, obj = _save(ctx, svc, existing, data, extra, entity=entity, out=out)
    return {"action": action, "record": {"id": obj.id, "label": obj.full_name}}


def _work(ctx, entity, out, extra):
    from app.modules.work.models import WorkItem
    from app.modules.work.service import WorkItemService

    svc = ctx.service(WorkItemService)
    existing = None
    if out.get("code"):
        existing = db.session.scalar(select(WorkItem).where(
            WorkItem.tenant_id == ctx.tenant_id, WorkItem.is_deleted.is_(False), func.upper(WorkItem.code) == out["code"].upper()))
        if existing is None:
            raise RowInvalid([{"column": "Code", "message": f"No work item with code {out['code']}; leave Code empty to create one"}])
    elif out.get("external_id") and (rid := ctx.external("work_item", out["external_id"])):
        existing = db.session.get(WorkItem, rid)
        existing = existing if existing is not None and not existing.is_deleted else None
    _existing_check(ctx, existing, "Code" if out.get("code") else "External ID")
    data = _fields(entity, out)
    if existing is not None and data.get("parent_id") == existing.id:
        raise RowInvalid([{"column": "Parent", "message": "An item cannot be its own parent"}])
    action, obj = _save(ctx, svc, existing, data, extra, entity=entity, out=out)
    ctx.remember("work_item", out.get("external_id"), obj.id)
    return {"action": action, "record": {"id": obj.id, "label": f"{obj.code} {obj.title}"}}


def _assignment(ctx, entity, out, extra):
    from app.modules.work.models import Assignment
    from app.modules.work.service import AssignmentService

    svc = ctx.service(AssignmentService)
    existing = None
    if out.get("item") and out.get("person"):
        existing = db.session.scalar(select(Assignment).where(
            Assignment.tenant_id == ctx.tenant_id, Assignment.is_deleted.is_(False),
            Assignment.work_item_id == out["item"], Assignment.person_id == out["person"]))
    _existing_check(ctx, existing, "Person")
    data = _fields(entity, out)
    if existing is not None:
        data.pop("work_item_id", None)
        data.pop("person_id", None)
    action, obj = _save(ctx, svc, existing, data, extra, entity=entity, out=out)
    return {"action": action, "record": {"id": obj.id, "label": f"{obj.person.full_name if obj.person else ''} on item {obj.work_item_id}"}}


def _demand(ctx, entity, out, extra):
    from app.modules.demand.models import DemandRequest
    from app.modules.demand.service import DemandService

    svc = ctx.service(DemandService)
    existing = None
    if out.get("code"):
        existing = db.session.scalar(select(DemandRequest).where(
            DemandRequest.tenant_id == ctx.tenant_id, DemandRequest.is_deleted.is_(False),
            func.upper(DemandRequest.code) == out["code"].upper()))
        if existing is None:
            raise RowInvalid([{"column": "Code", "message": f"No request with code {out['code']}"}])
    elif out.get("external_id") and (rid := ctx.external("demand_request", out["external_id"])):
        existing = db.session.get(DemandRequest, rid)
        existing = existing if existing is not None and not existing.is_deleted else None
    _existing_check(ctx, existing, "Code" if out.get("code") else "External ID")
    data = _fields(entity, out)
    action, obj = _save(ctx, svc, existing, data, extra, entity=entity, out=out)
    ctx.remember("demand_request", out.get("external_id"), obj.id)
    return {"action": action, "record": {"id": obj.id, "label": f"{obj.code} {obj.title}"}}


# ---------------------------------------------------------------------- ordering
def order_rows(entity: Entity, rows):
    """Rows in an order where references inside the file come first: managers before their reports,
    parents before children. Rows that refer to each other in a loop keep their place and fail."""
    if entity.code not in ("people", "work_items"):
        return rows
    own_key, ref_key = ("email", "manager") if entity.code == "people" else ("external_id", "parent")
    keyed = {}
    for n, values in rows:
        k = str(values.get(own_key) or "").strip().lower()
        if k:
            keyed.setdefault(k, (n, values))
    done, out, visiting = set(), [], set()

    def visit(n, values):
        if n in done:
            return
        if n in visiting:
            return  # a loop: leave it to fail on its own
        visiting.add(n)
        ref = str(values.get(ref_key) or "").strip().lower()
        if ref in keyed and keyed[ref][0] != n:
            visit(*keyed[ref])
        visiting.discard(n)
        if n not in done:
            done.add(n)
            out.append((n, values))

    for n, values in rows:
        visit(n, values)
    return out
