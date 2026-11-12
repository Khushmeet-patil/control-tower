"""Reusable hierarchy support, shared by the administrative tree (org units) and the
functional tree (functions) — and any future tree.

Each tree has a node table with `parent_id` plus a closure table holding one row per
(ancestor, descendant) pair, including each node with itself at depth 0. Closure rows make
"everything under X" a single indexed query, however deep the tree.

Closure rows are derived data: `rebuild_closure()` regenerates them from `parent_id`.
"""
from sqlalchemy import ForeignKey, Integer, delete, insert, select
from sqlalchemy.orm import Mapped, mapped_column

from app.core.command import CommandService
from app.core.errors import Conflict, ValidationFailed
from app.extensions import db


def make_closure_model(class_name: str, table_name: str, node_table: str):
    """Build a closure-table model for the node table `node_table`."""
    return type(class_name, (db.Model,), {
        "__tablename__": table_name,
        "__annotations__": {"ancestor_id": Mapped[int], "descendant_id": Mapped[int], "depth": Mapped[int]},
        "ancestor_id": mapped_column(ForeignKey(f"{node_table}.id"), primary_key=True),
        "descendant_id": mapped_column(ForeignKey(f"{node_table}.id"), primary_key=True, index=True),
        "depth": mapped_column(Integer, nullable=False),
    })


# ---------------------------------------------------------------------- closure operations
def add_node(closure, node_id: int, parent_id: int | None) -> None:
    db.session.add(closure(ancestor_id=node_id, descendant_id=node_id, depth=0))
    if parent_id is not None:
        db.session.execute(insert(closure).from_select(
            ["ancestor_id", "descendant_id", "depth"],
            select(closure.ancestor_id, db.literal(node_id), closure.depth + 1)
            .where(closure.descendant_id == parent_id),
        ))


def move_node(closure, node_id: int, new_parent_id: int | None) -> None:
    subtree = select(closure.descendant_id).where(closure.ancestor_id == node_id).scalar_subquery()
    db.session.execute(delete(closure).where(
        closure.descendant_id.in_(subtree),
        closure.ancestor_id.not_in(
            select(closure.descendant_id).where(closure.ancestor_id == node_id).scalar_subquery()),
    ).execution_options(synchronize_session=False))
    if new_parent_id is None:
        return
    above = db.session.execute(select(closure.ancestor_id, closure.depth)
                               .where(closure.descendant_id == new_parent_id)).all()
    below = db.session.execute(select(closure.descendant_id, closure.depth)
                               .where(closure.ancestor_id == node_id)).all()
    db.session.execute(insert(closure), [
        {"ancestor_id": a, "descendant_id": d, "depth": da + dd + 1}
        for a, da in above for d, dd in below
    ])


def descendant_ids(closure, node_ids, include_self: bool = True) -> set[int]:
    ids = list(node_ids)
    if not ids:
        return set()
    stmt = select(closure.descendant_id).where(closure.ancestor_id.in_(ids))
    if not include_self:
        stmt = stmt.where(closure.depth > 0)
    return set(db.session.scalars(stmt))


def ancestor_ids(closure, node_id: int, include_self: bool = False) -> list[int]:
    """Ancestors ordered from the root down."""
    stmt = select(closure.ancestor_id).where(closure.descendant_id == node_id)
    if not include_self:
        stmt = stmt.where(closure.depth > 0)
    return list(db.session.scalars(stmt.order_by(closure.depth.desc())))


def is_descendant(closure, node_id: int, possible_ancestor_id: int) -> bool:
    return db.session.scalar(select(closure.depth).where(
        closure.ancestor_id == possible_ancestor_id, closure.descendant_id == node_id)) is not None


def rebuild_closure(closure, node_model, tenant_id: int) -> None:
    """Regenerate all closure rows of a tenant's tree from parent_id."""
    nodes = db.session.execute(select(node_model.id, node_model.parent_id)
                               .where(node_model.tenant_id == tenant_id)).all()
    ids = [n for n, _ in nodes]
    db.session.execute(delete(closure).where(closure.descendant_id.in_(ids)))
    parent = dict(nodes)
    rows = []
    for node_id in ids:
        depth, current, seen = 0, node_id, set()
        while current is not None and current not in seen:
            seen.add(current)
            rows.append({"ancestor_id": current, "descendant_id": node_id, "depth": depth})
            current, depth = parent.get(current), depth + 1
    if rows:
        db.session.execute(insert(closure), rows)


# ---------------------------------------------------------------------- service base
class TreeService(CommandService):
    """CommandService for a tree node: keeps closure rows in step and blocks cycles."""

    closure = None  # set by subclasses

    def _check_parent(self, parent_id, node_id=None):
        if parent_id is None:
            return
        parent = db.session.get(self.model, parent_id)
        if parent is None or parent.tenant_id != self.tenant_id or parent.is_deleted:
            raise ValidationFailed("Parent not found", {"field": "parent_id"})
        if node_id is not None and (parent_id == node_id or is_descendant(self.closure, parent_id, node_id)):
            raise ValidationFailed("An item cannot be moved under itself or one of its children",
                                   {"field": "parent_id"})

    def validate_create(self, data):
        self._check_parent(data.get("parent_id"))

    def validate_update(self, obj, changes):
        if "parent_id" in changes:
            self._check_parent(changes["parent_id"], obj.id)

    def after_create(self, obj, data):
        add_node(self.closure, obj.id, obj.parent_id)

    def apply_update(self, obj, changes):
        moved = "parent_id" in changes and changes["parent_id"] != obj.parent_id
        super().apply_update(obj, changes)
        if moved:
            db.session.flush()
            move_node(self.closure, obj.id, obj.parent_id)

    def child_count(self, obj) -> int:
        return db.session.scalar(select(db.func.count()).select_from(self.model).where(
            self.model.parent_id == obj.id, self.model.is_deleted.is_(False)))

    def validate_delete(self, obj):
        if self.child_count(obj):
            raise Conflict("Move or delete the items under this one first")
