"""Templates: save a work breakdown, edit it, and create work from it (see models.py)."""
from datetime import date, timedelta

from sqlalchemy import or_, select

from app.core.command import CommandService
from app.core.errors import Forbidden, ValidationFailed
from app.core.pagination import paginate
from app.core.permissions import actor_can
from app.extensions import db
from app.modules.config.versioning import published_list
from app.modules.templates.models import WorkTemplate
from app.modules.work.models import WorkItem
from app.modules.work.service import WorkItemService, person_ref

MAX_NODES = 300
MAX_DEPTH = 8
NODE_FIELDS = ("title", "item_type_id", "description", "objective", "weight", "start_offset", "duration")


def _count(nodes) -> int:
    return sum(1 + _count(n.get("children") or []) for n in nodes)


class TemplateService(CommandService):
    model = WorkTemplate
    entity_type = "work_template"
    permissions = {"create": "work.view", "update": "work.view", "delete": "work.view"}
    protected_fields = frozenset({"owner_id", "node_count"})

    def base_query(self):
        stmt = super().base_query()
        if self.actor is None:
            return stmt
        return stmt.where(or_(WorkTemplate.owner_id == self.actor.id, WorkTemplate.is_shared.is_(True)))

    def list(self, params):
        stmt = self.base_query()
        if q := params.get("q"):
            stmt = stmt.where(WorkTemplate.name.ilike(f"%{q}%"))
        return paginate(stmt.order_by(WorkTemplate.name), params, self.serialize)

    def can_edit(self, t) -> bool:
        if self.actor is None:
            return True
        return t.owner_id == self.actor.id or (t.is_shared and actor_can(self.actor, "templates.share"))

    def serialize(self, t: WorkTemplate, detail=False) -> dict:
        out = {"id": t.id, "name": t.name, "description": t.description, "is_shared": t.is_shared,
               "owner": person_ref(t.owner), "node_count": t.node_count, "source_item_id": t.source_item_id,
               "root_type_ids": sorted({n.get("item_type_id") for n in t.structure or []}),
               "can_edit": self.can_edit(t), "updated_at": t.updated_at.isoformat(), "version": t.version}
        if detail:
            out["structure"] = t.structure
        return out

    # ------------------------------------------------------------------ validation
    def _clean_nodes(self, nodes, depth=1):
        if not isinstance(nodes, list):
            raise ValidationFailed("The structure is a list of items", {"field": "structure"})
        if depth > MAX_DEPTH:
            raise ValidationFailed(f"A template can be at most {MAX_DEPTH} levels deep", {"field": "structure"})
        types = published_list(self.tenant_id, "item_type")
        out = []
        for n in nodes:
            if not isinstance(n, dict):
                raise ValidationFailed("Each item in the structure is an object", {"field": "structure"})
            title = str(n.get("title") or "").strip()
            if not title:
                raise ValidationFailed("Every item needs a title", {"field": "structure"})
            type_id = n.get("item_type_id")
            if type_id not in types or not types[type_id]["is_active"]:
                raise ValidationFailed(f"Choose an item type for “{title}”", {"field": "structure"})
            node = {"title": title[:300], "item_type_id": type_id}
            for f in ("description", "objective"):
                if n.get(f):
                    node[f] = str(n[f])
            for f in ("weight", "start_offset", "duration"):
                v = n.get(f)
                if v in (None, ""):
                    continue
                if not isinstance(v, int) or v < 0 or v > 3650 or (f == "weight" and v < 1):
                    raise ValidationFailed(f"“{title}”: {f.replace('_', ' ')} must be a whole number of days (0–3650)",
                                           {"field": "structure"})
                node[f] = v
            node["children"] = self._clean_nodes(n.get("children") or [], depth + 1)
            out.append(node)
        return out

    def _check(self, data, obj=None):
        if "structure" in data:
            data["structure"] = self._clean_nodes(data["structure"])
            if not data["structure"]:
                raise ValidationFailed("A template needs at least one item", {"field": "structure"})
            data["node_count"] = _count(data["structure"])
            if data["node_count"] > MAX_NODES:
                raise ValidationFailed(f"A template can hold at most {MAX_NODES} items", {"field": "structure"})
        sharing = data.get("is_shared")
        if sharing and not (obj is not None and obj.is_shared):
            if not actor_can(self.actor, "templates.share"):
                raise Forbidden("You cannot share templates with everyone")

    def _accepted_inputs(self):
        return {"node_count"}

    def validate_create(self, data):
        if not (data.get("name") or "").strip():
            raise ValidationFailed("Name the template", {"field": "name"})
        if "structure" not in data:
            raise ValidationFailed("A template needs at least one item", {"field": "structure"})
        self._check(data)

    def apply_create(self, data):
        return WorkTemplate(**data, owner_id=getattr(self.actor, "id", None))

    def validate_update(self, obj, changes):
        if not self.can_edit(obj):
            raise Forbidden("You cannot change this template")
        self._check(changes, obj)

    def validate_delete(self, obj):
        if not self.can_edit(obj):
            raise Forbidden("You cannot delete this template")

    # ------------------------------------------------------------------ save from an item
    def from_item(self, item_id, name, description=None, is_shared=False) -> WorkTemplate:
        work = WorkItemService(self.actor, tenant_id=self.tenant_id)
        root = work.get(item_id)
        visible = {w.id: w for w in work.rows({"ancestor_id": str(root.id)})}
        visible[root.id] = root
        anchor = root.planned_start or min((w.planned_start for w in visible.values() if w.planned_start), default=None)

        def node(w):
            n = {"title": w.title, "item_type_id": w.item_type_id, "weight": w.weight}
            if w.description:
                n["description"] = w.description
            if w.objective:
                n["objective"] = w.objective
            if anchor and w.planned_start:
                n["start_offset"] = max(0, (w.planned_start - anchor).days)
            if w.planned_start and w.planned_end:
                n["duration"] = max(0, (w.planned_end - w.planned_start).days)
            elif anchor and w.planned_end and not w.planned_start:
                n["start_offset"] = max(0, (w.planned_end - anchor).days)
                n["duration"] = 0
            kids = sorted((c for c in visible.values() if c.parent_id == w.id),
                          key=lambda c: (c.planned_start or date.max, c.code))
            n["children"] = [node(c) for c in kids]
            return n

        return self.create({"name": name or root.title, "description": description, "is_shared": bool(is_shared),
                            "structure": [node(root)], "source_item_id": root.id},
                           reason=f"Saved from {root.code}")

    # ------------------------------------------------------------------ use
    def instantiate(self, template_id, *, start_date: date | None = None, parent_id=None, unit_id=None,
                    accountable_id=None, title=None, reason=None) -> list[WorkItem]:
        """Create the template's items. Returns the top-level items made (usually one)."""
        t = self.get(template_id)
        work = WorkItemService(self.actor, tenant_id=self.tenant_id, source=self.source,
                               correlation_id=self.correlation_id)
        why = reason or f"Created from template “{t.name}”"
        made = []

        def create(node, parent, top):
            data = {"title": (title if top and title and len(t.structure) == 1 else node["title"]),
                    "item_type_id": node["item_type_id"], "description": node.get("description"),
                    "objective": node.get("objective"), "weight": node.get("weight")}
            if parent is not None:
                data["parent_id"] = parent.id
            if top:
                if unit_id:
                    data["unit_id"] = unit_id
                if accountable_id:
                    data["accountable_id"] = accountable_id
            if start_date is not None and node.get("start_offset") is not None:
                start = start_date + timedelta(days=node["start_offset"])
                data["planned_start"] = start
                if node.get("duration") is not None:
                    data["planned_end"] = start + timedelta(days=node["duration"])
            item = work.create({k: v for k, v in data.items() if v is not None}, reason=why)
            for child in node.get("children") or []:
                create(child, item, False)
            return item

        parent = work.get(parent_id) if parent_id else None
        with self.transaction():
            for node in t.structure:
                made.append(create(node, parent, True))
            self._audit(t.id, "use", new={"items": [m.code for m in made]}, reason=why)
        return made
