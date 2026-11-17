"""Tool Centre: the tools registry, who may use each tool, and the built-in tools that save to work items.

Using a tool (see models.py for the scope fields):
    active  AND  role allowed  AND  (on an item:   the item is visible to you and the tool applies to it
                                     in the Centre: the tool is organisation-wide, or reaches your unit,
                                                    a unit you manage, or an item you can see)
A tool you may not use is reported as "not found", so its existence and address do not leak.

External links: lists never include the address, only its host. The address comes back from
`open()`, which checks access and writes an audit event first.

Built-in tools write through the same services as the screens:
- a form updates the work item through WorkItemService (its permissions and per-field audit apply),
- a checklist saves a ToolResponse through ToolResponseService.
Both record source = "tool" and share the request's correlation ID with the tool's own "use" event.
"""
import re
from urllib.parse import urlparse

from sqlalchemy import select

from app.core.command import CUSTOM_PREFIX, CommandService
from app.core.errors import Forbidden, NotFound, ValidationFailed
from app.core.filters import apply_filters
from app.core.models import utcnow
from app.core.pagination import paginate
from app.core.permissions import actor_can, ensure_can
from app.core.tree import ancestor_ids, descendant_ids
from app.extensions import db
from app.modules.access.models import Role, UserRole
from app.modules.access.scope import is_global, managed_unit_ids
from app.modules.config.versioning import published_fields, published_list
from app.modules.organisation.models import OrgUnit, OrgUnitClosure
from app.modules.tools.models import KINDS, Tool, ToolResponse
from app.modules.work.models import WorkItem, WorkItemClosure
from app.modules.work.service import VIEW, WorkItemService, person_ref, work_visibility_clause

# Work item fields a form tool may contain (custom fields are added from the published settings).
FORM_FIELDS = {
    "description": "Description", "objective": "Business objective", "risks": "Key risks", "remarks": "Remarks",
    "evidence_url": "Evidence / deliverable link", "status_id": "Status", "priority_id": "Priority",
    "category_id": "Category", "planned_start": "Planned start", "planned_end": "Planned finish",
    "actual_start": "Actual start", "actual_end": "Actual finish", "progress_manual": "Progress %",
}
LIST_FIELDS = ("work_item_ids", "unit_ids", "role_ids", "item_type_ids")
MAX_CHECKLIST_ITEMS = 50
PARAM_KEY = re.compile(r"^[A-Za-z0-9_.-]{1,40}$")
FILTERABLE = {"name": Tool.name, "kind": Tool.kind, "is_active": Tool.is_active, "sort_order": Tool.sort_order,
              "updated_at": Tool.updated_at}
SEARCH = [Tool.name, Tool.description]


PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")
PLACEHOLDERS = {"code", "id", "title", "type", "status", "unit", "unit_code", "user_email", "user_id"}


def context_values(item, actor) -> dict:
    """What a link tool's parameters may contain: {code}, {id}, {title}, {type}, {status}, {unit},
    {unit_code}, {user_email}, {user_id}. Values about the item are empty when the tool is opened
    from the Tool Centre instead of from an item."""
    values = {"user_email": getattr(actor, "email", "") or "", "user_id": str(getattr(actor, "id", "") or "")}
    if item is not None:
        labels = {**published_list(item.tenant_id, "item_type"), **published_list(item.tenant_id, "status")}
        values.update({"code": item.code, "id": str(item.id), "title": item.title,
                       "type": (labels.get(item.item_type_id) or {}).get("label", ""),
                       "status": (labels.get(item.status_id) or {}).get("label", ""),
                       "unit": item.unit.name if item.unit else "", "unit_code": (item.unit.code or "") if item.unit else ""})
    return values


def build_url(tool, item, actor) -> str:
    """The tool's address with its context parameters added to the query string, e.g. {"project": "{code}"}
    opens https://tool.example/board?project=PRJ-004. Parameters that resolve to nothing are left out."""
    from urllib.parse import parse_qsl, urlencode, urlunparse

    params = tool.context_params or {}
    if not params:
        return tool.url
    values = context_values(item, actor)
    extra = []
    for name, template in params.items():
        value = PLACEHOLDER.sub(lambda m: values.get(m.group(1), ""), template)
        if value.strip():
            extra.append((name, value))
    if not extra:
        return tool.url
    parts = urlparse(tool.url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in dict(extra)] + extra
    return urlunparse(parts._replace(query=urlencode(query)))


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:40] or "item"


def _host(url):
    return urlparse(url).netloc if url else None


class ToolResponseService(CommandService):
    """Checklist answers on a work item. Only ToolService calls it, after checking access."""

    model = ToolResponse
    entity_type = "tool_response"


class ToolService(CommandService):
    model = Tool
    entity_type = "tool"
    permissions = {"create": "tools.manage", "update": "tools.manage", "delete": "tools.manage"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._my_roles = None
        self._below = {}

    def _accepted_inputs(self):
        return {"work_item_codes"}  # a convenience for the admin form: resolved to work_item_ids

    def _work(self, source=None):
        return WorkItemService(self.actor, tenant_id=self.tenant_id, source=source or self.source,
                               correlation_id=self.correlation_id)

    # ------------------------------------------------------------------ who may use a tool
    def role_ok(self, tool) -> bool:
        if not tool.role_ids or self.actor is None or self.actor.is_admin:
            return True
        if self._my_roles is None:
            self._my_roles = set(db.session.scalars(select(UserRole.role_id).where(UserRole.user_id == self.actor.id)))
        return bool(self._my_roles & set(tool.role_ids))

    def _units_below(self, tool) -> set[int]:
        if tool.id not in self._below:
            self._below[tool.id] = descendant_ids(OrgUnitClosure, tool.unit_ids or [])
        return self._below[tool.id]

    @staticmethod
    def is_org_wide(tool) -> bool:
        return not tool.work_item_ids and not tool.unit_ids

    def applies_to_item(self, tool, item) -> bool:
        if tool.item_type_ids and item.item_type_id not in tool.item_type_ids:
            return False
        if self.is_org_wide(tool):
            return True
        if tool.work_item_ids and set(tool.work_item_ids) & set(ancestor_ids(WorkItemClosure, item.id, include_self=True)):
            return True
        return bool(tool.unit_ids) and item.unit_id in self._units_below(tool)

    def _visible_items(self, ids):
        stmt = select(WorkItem).where(WorkItem.tenant_id == self.tenant_id, WorkItem.is_deleted.is_(False),
                                      WorkItem.id.in_(ids or []))
        clause = work_visibility_clause(self.actor) if self.actor is not None else None
        return db.session.scalars(stmt if clause is None else stmt.where(clause)).all()

    def reaches_actor(self, tool) -> bool:
        """Tool Centre (no item): may the actor use this tool at all?"""
        if self.is_org_wide(tool) or self.actor is None or is_global(self.actor):
            return True
        if tool.unit_ids:
            units = self._units_below(tool)
            if self.actor.unit_id in units or (managed_unit_ids(self.actor) or set()) & units:
                return True
        if not tool.work_item_ids:
            return False
        # Linked to a project: anyone who can see it, or any item below it, may use the tool.
        stmt = select(WorkItem.id).where(
            WorkItem.tenant_id == self.tenant_id, WorkItem.is_deleted.is_(False),
            WorkItem.id.in_(select(WorkItemClosure.descendant_id).where(WorkItemClosure.ancestor_id.in_(tool.work_item_ids))))
        clause = work_visibility_clause(self.actor)
        return db.session.scalar((stmt if clause is None else stmt.where(clause)).limit(1)) is not None

    def usable(self, tool_id, work_item_id=None):
        """(tool, item) if the actor may use the tool (on that item); otherwise NotFound."""
        tool = self.get(tool_id)
        item = self._work().get(work_item_id) if work_item_id else None
        ok = tool.is_active and self.role_ok(tool) and (
            self.applies_to_item(tool, item) if item is not None else self.reaches_actor(tool))
        if not ok:
            raise NotFound("Tool not found, or it is not available to you")
        return tool, item

    # ------------------------------------------------------------------ reads
    def list(self, params):
        """Tools the actor may use (on `work_item_id`, if given). `manage=1` lists the whole registry."""
        params = dict(params)
        if params.pop("manage", "") in ("1", "true"):
            ensure_can(self.actor, "tools.manage")
            stmt = apply_filters(self.base_query(), params, FILTERABLE, SEARCH, default_sort="sort_order,name")
            return paginate(stmt, params, lambda t: self.serialize(t, manage=True))
        item = self._work().get(int(params["work_item_id"])) if params.get("work_item_id") else None
        q = (params.get("q") or "").strip().lower()
        kind = params.get("kind")
        tools = db.session.scalars(self.base_query().where(Tool.is_active.is_(True))
                                   .order_by(Tool.sort_order, Tool.name)).all()
        out = []
        for t in tools:
            if kind and t.kind != kind:
                continue
            if q and q not in f"{t.name} {t.description or ''}".lower():
                continue
            if not self.role_ok(t):
                continue
            if not (self.applies_to_item(t, item) if item is not None else self.reaches_actor(t)):
                continue
            out.append(self.serialize(t, item=item))
        return {"items": out, "page": 1, "per_page": max(len(out), 1), "total": len(out), "pages": 1}

    def detail(self, tool_id):
        if actor_can(self.actor, "tools.manage"):
            return self.serialize(self.get(tool_id), manage=True)
        tool, _ = self.usable(tool_id)
        return self.serialize(tool)

    def form_field_options(self) -> list[dict]:
        core = [{"code": c, "label": label} for c, label in FORM_FIELDS.items()]
        custom = [{"code": f"{CUSTOM_PREFIX}{f['code']}", "label": f["label"], "custom": True}
                  for f in published_fields(self.tenant_id, "work_item")]
        return core + custom

    def _definition_out(self, t):
        d = t.definition or {}
        if t.kind == "form":
            labels = {o["code"]: o["label"] for o in self.form_field_options()}
            return {"fields": [{"code": c, "label": labels.get(c, c)} for c in d.get("fields", [])]}
        if t.kind == "checklist":
            return {"items": d.get("items", []), "pass_pct": d.get("pass_pct", 100)}
        return None

    def serialize(self, t: Tool, *, manage=False, item=None) -> dict:
        units = db.session.scalars(select(OrgUnit).where(OrgUnit.id.in_(t.unit_ids or []))).all()
        roles = db.session.scalars(select(Role).where(Role.id.in_(t.role_ids or []))).all()
        # Linked items: managers see them all; others only the ones they may open.
        items = (db.session.scalars(select(WorkItem).where(WorkItem.id.in_(t.work_item_ids or []))).all()
                 if manage else self._visible_items(t.work_item_ids))
        out = {
            "id": t.id, "name": t.name, "description": t.description, "icon": t.icon, "kind": t.kind,
            "host": _host(t.url), "definition": self._definition_out(t),
            "applies_to": {
                "org_wide": self.is_org_wide(t),
                "work_items": [{"id": w.id, "code": w.code, "title": w.title} for w in items],
                "units": [{"id": u.id, "name": u.name} for u in units],
                "roles": [{"id": r.id, "name": r.name} for r in roles],
                "item_type_ids": t.item_type_ids or [],
            },
            "is_active": t.is_active, "sort_order": t.sort_order, "version": t.version,
        }
        if manage:
            out.update({"url": t.url, "context_params": t.context_params or {}, "raw_definition": t.definition,
                        **{f: getattr(t, f) or [] for f in LIST_FIELDS},
                        "work_item_codes": [w.code for w in items]})
        if item is not None and t.kind == "checklist":
            r = self._response(t.id, item.id)
            out["response"] = self.serialize_response(r) if r else None
        if item is not None:
            out["can_use"] = t.kind == "link" or self._work().access(item) != VIEW
        return out

    # ------------------------------------------------------------------ validation (registry)
    def _resolve_codes(self, data):
        if "work_item_codes" not in data:
            return
        codes = [c.strip().upper() for c in data.pop("work_item_codes") or [] if c and c.strip()]
        found = dict(db.session.execute(select(WorkItem.code, WorkItem.id).where(
            WorkItem.tenant_id == self.tenant_id, WorkItem.is_deleted.is_(False), WorkItem.code.in_(codes))).all())
        if missing := [c for c in codes if c not in found]:
            raise ValidationFailed(f"No work item with code {', '.join(missing)}", {"field": "work_item_codes"})
        data["work_item_ids"] = [found[c] for c in codes]

    def _check_ids(self, field, ids):
        if ids is None:
            return None
        ids = sorted({int(i) for i in ids})
        if not ids:
            return None
        if field == "item_type_ids":
            known = set(published_list(self.tenant_id, "item_type"))
        else:
            model = {"work_item_ids": WorkItem, "unit_ids": OrgUnit, "role_ids": Role}[field]
            known = set(db.session.scalars(select(model.id).where(model.tenant_id == self.tenant_id,
                                                                  model.is_deleted.is_(False), model.id.in_(ids))))
        if set(ids) - known:
            raise ValidationFailed("Some of the chosen records do not exist", {"field": field})
        return ids

    def _check_definition(self, kind, definition):
        if kind == "link":
            return None
        definition = definition or {}
        if kind == "form":
            allowed = {o["code"] for o in self.form_field_options()}
            fields = list(dict.fromkeys(definition.get("fields") or []))
            if not fields:
                raise ValidationFailed("Choose the fields the form fills in", {"field": "definition"})
            if bad := [f for f in fields if f not in allowed]:
                raise ValidationFailed(f"Unknown work item field: {', '.join(bad)}", {"field": "definition"})
            return {"fields": fields}
        items, seen = [], set()
        for raw in definition.get("items") or []:
            label = str(raw.get("label") if isinstance(raw, dict) else raw).strip()
            if not label:
                continue
            code = _slug(raw.get("code") or label) if isinstance(raw, dict) else _slug(label)
            base, n = code, 2
            while code in seen:
                code, n = f"{base}_{n}", n + 1
            seen.add(code)
            items.append({"code": code, "label": label[:200]})
        if not items or len(items) > MAX_CHECKLIST_ITEMS:
            raise ValidationFailed(f"A checklist needs 1 to {MAX_CHECKLIST_ITEMS} items", {"field": "definition"})
        pass_pct = definition.get("pass_pct", 100)
        if not isinstance(pass_pct, int) or not 0 <= pass_pct <= 100:
            raise ValidationFailed("The pass mark is a percentage from 0 to 100", {"field": "pass_pct"})
        return {"items": items, "pass_pct": pass_pct}

    @staticmethod
    def _check_params(params):
        if not params:
            return None
        if not isinstance(params, dict) or len(params) > 20:
            raise ValidationFailed("Up to 20 name = value pairs", {"field": "context_params"})
        for k, v in params.items():
            if not PARAM_KEY.match(str(k)) or not isinstance(v, str) or len(v) > 200:
                raise ValidationFailed(f"Invalid pair: {k}", {"field": "context_params"})
            unknown = set(PLACEHOLDER.findall(v)) - PLACEHOLDERS
            if unknown:
                raise ValidationFailed(f"Unknown placeholder {{{sorted(unknown)[0]}}}. Use: "
                                       + ", ".join(f"{{{p}}}" for p in sorted(PLACEHOLDERS)), {"field": "context_params"})
        return dict(params)

    def _check(self, data, obj=None):
        self._resolve_codes(data)
        kind = data.get("kind", getattr(obj, "kind", None) or "link")
        if kind not in KINDS:
            raise ValidationFailed("Choose a kind of tool", {"field": "kind"})
        if obj is None:
            data["kind"] = kind
        url = data.get("url", getattr(obj, "url", None))
        if url:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                raise ValidationFailed("Enter a web address starting with https://", {"field": "url"})
        elif kind == "link":
            raise ValidationFailed("A link tool needs a web address", {"field": "url"})
        for field in LIST_FIELDS:
            if field in data:
                data[field] = self._check_ids(field, data[field])
        if obj is None or "definition" in data or "kind" in data:
            data["definition"] = self._check_definition(kind, data.get("definition", getattr(obj, "definition", None)))
        if "context_params" in data:
            data["context_params"] = self._check_params(data["context_params"])

    def validate_create(self, data):
        self._check(data)

    def validate_update(self, obj, changes):
        self._check(changes, obj)

    # ------------------------------------------------------------------ using tools
    def _use_event(self, tool, item, operation, extra=None, reason=None):
        new = {"work_item_id": item.id, "work_item": item.code} if item is not None else None
        if extra:
            new = {**(new or {}), **extra}
        self._audit(tool.id, operation, new=new, reason=reason)

    def open(self, tool_id, work_item_id=None) -> dict:
        """Check access, log the opening, and return the address to open."""
        tool, item = self.usable(tool_id, work_item_id)
        if tool.kind != "link":
            raise ValidationFailed("This tool is used inside Control Tower, on a work item")
        url = build_url(tool, item, self.actor)
        with self.transaction():
            self._use_event(tool, item, "open", {"parameters": sorted((tool.context_params or {}))} if tool.context_params else None)
        return {"url": url}

    def submit_form(self, tool_id, work_item_id, values, *, expected_version=None, reason=None) -> dict:
        """Save a form tool's fields to the work item, as the screen would (same permissions and audit)."""
        if not work_item_id:
            raise ValidationFailed("Choose the work item to fill the form in for", {"field": "work_item_id"})
        tool, item = self.usable(tool_id, work_item_id)
        if tool.kind != "form":
            raise ValidationFailed("This tool is not a form")
        allowed = set((tool.definition or {}).get("fields", []))
        changes, blocked = {}, []
        for key, value in (values or {}).items():
            if key == "custom_fields":
                value = value or {}
                blocked += [f"{CUSTOM_PREFIX}{c}" for c in value if f"{CUSTOM_PREFIX}{c}" not in allowed]
                changes["custom_fields"] = value
            elif key in allowed:
                changes[key] = value
            else:
                blocked.append(key)
        if blocked:
            raise ValidationFailed("These fields are not part of this tool", {"fields": sorted(blocked)})
        fields = sorted(k for k in changes if k != "custom_fields") \
            + sorted(f"{CUSTOM_PREFIX}{c}" for c in changes.get("custom_fields", {}))
        work = self._work(source="tool")
        with self.transaction():
            work.update(item.id, changes, expected_version=expected_version,
                        reason=f"{tool.name}: {reason}" if reason else tool.name)
            self._use_event(tool, item, "use", {"fields": fields}, reason=reason)
        return work.detail(item.id)

    # ------------------------------------------------------------------ checklists
    def _response(self, tool_id, item_id):
        return db.session.scalar(select(ToolResponse).where(
            ToolResponse.tenant_id == self.tenant_id, ToolResponse.tool_id == tool_id,
            ToolResponse.work_item_id == item_id, ToolResponse.is_deleted.is_(False)))

    @staticmethod
    def serialize_response(r: ToolResponse) -> dict:
        from app.modules.auth.models import User

        by = db.session.get(User, r.submitted_by_id) if r.submitted_by_id else None
        return {"id": r.id, "tool_id": r.tool_id, "work_item_id": r.work_item_id, "answers": r.answers or {},
                "notes": r.notes, "score_pct": r.score_pct, "passed": r.passed, "submitted_by": person_ref(by),
                "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None, "version": r.version}

    def get_response(self, tool_id, work_item_id):
        tool, item = self.usable(tool_id, work_item_id)
        r = self._response(tool.id, item.id)
        return self.serialize_response(r) if r else None

    def save_checklist(self, tool_id, work_item_id, answers, notes=None, *, expected_version=None, reason=None):
        if not work_item_id:
            raise ValidationFailed("Choose the work item to assess", {"field": "work_item_id"})
        tool, item = self.usable(tool_id, work_item_id)
        if tool.kind != "checklist":
            raise ValidationFailed("This tool is not a checklist")
        if self._work().access(item) == VIEW:
            raise Forbidden("Only people working on this item can fill in its checklists")
        definition = tool.definition or {}
        codes = [i["code"] for i in definition.get("items", [])]
        answers = answers or {}
        if unknown := sorted(set(answers) - set(codes)):
            raise ValidationFailed("Unknown checklist items", {"fields": unknown})
        clean = {c: bool(answers.get(c)) for c in codes}
        score = round(100 * sum(clean.values()) / len(codes)) if codes else 0
        notes = (notes or "").strip() or None
        data = {"answers": clean, "notes": notes, "score_pct": score, "passed": score >= definition.get("pass_pct", 100)}
        existing = self._response(tool.id, item.id)
        if existing and existing.answers == clean and existing.notes == notes:
            return self.serialize_response(existing)  # nothing changed: no new audit rows
        stamp = {"submitted_by_id": getattr(self.actor, "id", None), "submitted_at": utcnow()}
        svc = ToolResponseService(self.actor, tenant_id=self.tenant_id, source="tool", correlation_id=self.correlation_id)
        with self.transaction():
            if existing:
                r = svc.update(existing.id, {**data, **stamp}, expected_version=expected_version, reason=reason)
            else:
                r = svc.create({"tool_id": tool.id, "work_item_id": item.id, **data, **stamp}, reason=reason)
            self._use_event(tool, item, "use", {"score_pct": score, "passed": data["passed"]}, reason=reason)
        return self.serialize_response(r)

    def responses(self, tool_id, params):
        """A checklist's results across the work items the actor can see (readiness at a glance)."""
        tool, _ = self.usable(tool_id)
        stmt = select(ToolResponse, WorkItem).join(WorkItem, WorkItem.id == ToolResponse.work_item_id).where(
            ToolResponse.tenant_id == self.tenant_id, ToolResponse.tool_id == tool.id,
            ToolResponse.is_deleted.is_(False), WorkItem.is_deleted.is_(False))
        if self.actor is not None and (clause := work_visibility_clause(self.actor)) is not None:
            stmt = stmt.where(clause)
        if params.get("passed") in ("0", "1"):
            stmt = stmt.where(ToolResponse.passed.is_(params["passed"] == "1"))
        rows = db.session.execute(stmt.order_by(ToolResponse.score_pct, WorkItem.code)).all()
        items = [{**self.serialize_response(r), "work_item": {"id": w.id, "code": w.code, "title": w.title}}
                 for r, w in rows]
        return {"items": items, "page": 1, "per_page": max(len(items), 1), "total": len(items), "pages": 1}


def response_ids_for_item(item_id):
    """Subquery of checklist responses on an item, so its History tab includes them."""
    return select(ToolResponse.id).where(ToolResponse.work_item_id == item_id)

