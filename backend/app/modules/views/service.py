"""Saved views: personal ones for everyone, shared ones for people with `views.share`."""
from sqlalchemy import or_, select

from app.core.command import CommandService
from app.core.errors import Forbidden, ValidationFailed
from app.core.permissions import actor_can
from app.extensions import db
from app.modules.views.models import LAYOUTS, PAGES, SavedView

MAX_FILTERS = 30


class SavedViewService(CommandService):
    model = SavedView
    entity_type = "saved_view"
    permissions = {"create": "work.view", "update": "work.view", "delete": "work.view"}
    protected_fields = frozenset({"owner_id"})

    def base_query(self):
        """Your own views and everyone's shared views."""
        stmt = super().base_query()
        if self.actor is None:
            return stmt
        return stmt.where(or_(SavedView.owner_id == self.actor.id, SavedView.is_shared.is_(True)))

    def list_for(self, page):
        rows = db.session.scalars(self.base_query().where(SavedView.page == page)
                                  .order_by(SavedView.is_shared.desc(), SavedView.name)).all()
        return [self.serialize(v) for v in rows]

    def serialize(self, v):
        return {
            "id": v.id, "name": v.name, "page": v.page, "filters": v.filters, "layout": v.layout,
            "is_shared": v.is_shared, "owner": {"id": v.owner.id, "full_name": v.owner.full_name} if v.owner else None,
            "can_edit": self._can_edit(v), "version": v.version,
        }

    def _can_edit(self, v):
        return self.actor is None or self.actor.is_admin or v.owner_id == self.actor.id

    def _check(self, data):
        if "page" in data and data["page"] not in PAGES:
            raise ValidationFailed("Unknown screen", {"field": "page"})
        if "layout" in data and data["layout"] not in LAYOUTS:
            raise ValidationFailed("Choose list or board", {"field": "layout"})
        if "filters" in data:
            filters = data["filters"] or {}
            if not isinstance(filters, dict) or len(filters) > MAX_FILTERS or not all(
                    isinstance(k, str) and isinstance(v, (str, int)) for k, v in filters.items()):
                raise ValidationFailed("Filters must be simple name/value pairs", {"field": "filters"})
            data["filters"] = {k: str(v) for k, v in filters.items() if str(v) != ""}
        if data.get("is_shared") and not actor_can(self.actor, "views.share"):
            raise Forbidden("You do not have permission to share views")

    def validate_create(self, data):
        # Request bodies only carry the fields sent, so fill the defaults here.
        data.setdefault("page", "work")
        data.setdefault("filters", {})
        data.setdefault("layout", "list")
        data.setdefault("is_shared", False)
        self._check(data)
        data["owner_id"] = getattr(self.actor, "id", None) or data.get("owner_id")
        if data["owner_id"] is None:
            raise ValidationFailed("A view needs an owner")

    def apply_create(self, data):
        return SavedView(**data)

    def _clean(self, data):
        owner = data.pop("owner_id", None)
        clean = super()._clean(data)
        if owner is not None and self.actor is None:  # system seeding only
            clean["owner_id"] = owner
        return clean

    def validate_update(self, obj, changes):
        if not self._can_edit(obj):
            raise Forbidden("Only the person who saved this view can change it")
        changes.pop("page", None)
        self._check(changes)

    def validate_delete(self, obj):
        if not self._can_edit(obj):
            raise Forbidden("Only the person who saved this view can delete it")
