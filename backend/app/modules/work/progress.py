"""Progress engine: validated, weighted progress that rolls up the work tree and to units.

Rules (derived values, never typed in; recalculated on every read):
- A finished item with no children counts 100% only when it needed no approval or its approval is
  complete. Declared-done work still waiting for (or refused) approval counts its manual % (or 0).
- An unfinished item with no children counts its manual % (0 when empty).
- An item with children counts the weighted average of its children's progress (weight = `weight`,
  default 1). Cancelled children are left out. This repeats all the way up the tree.
- A unit's progress is the weighted average of the top-most items assigned to it or to units below it.
"""
from sqlalchemy import select

from app.extensions import db
from app.modules.config.versioning import published_value_id
from app.modules.work.models import WorkItem, WorkItemClosure

COUNTS_AS_APPROVED = (None, "approved")


def _status_ids(tenant_id):
    return published_value_id(tenant_id, "status", "done"), published_value_id(tenant_id, "status", "cancelled")


def leaf_progress(row, done_id) -> int:
    if row.status_id == done_id and done_id is not None and row.approval_status in COUNTS_AS_APPROVED:
        return 100
    return max(0, min(100, row.progress_manual or 0))


def progress_map(tenant_id: int, root_ids) -> dict[int, int]:
    """{item id: progress %} for the given items (and, as a by-product, everything below them)."""
    roots = [int(r) for r in root_ids]
    if not roots:
        return {}
    done_id, cancelled_id = _status_ids(tenant_id)
    ids = select(WorkItemClosure.descendant_id).where(WorkItemClosure.ancestor_id.in_(roots))
    rows = db.session.execute(select(
        WorkItem.id, WorkItem.parent_id, WorkItem.status_id, WorkItem.approval_status, WorkItem.progress_manual,
        WorkItem.weight).where(WorkItem.id.in_(ids), WorkItem.is_deleted.is_(False))).all()
    by_id = {r.id: r for r in rows}
    children = {}
    for r in rows:
        if r.parent_id in by_id and r.status_id != cancelled_id:
            children.setdefault(r.parent_id, []).append(r)

    result = {}

    def compute(item_id):  # iterative post-order, so deep trees cannot hit the recursion limit
        stack = [(item_id, False)]
        while stack:
            node, expanded = stack.pop()
            if node in result:
                continue
            kids = children.get(node, [])
            if kids and not expanded:
                stack.append((node, True))
                stack.extend((k.id, False) for k in kids if k.id not in result)
                continue
            if kids:
                total = sum(max(k.weight or 0, 0) for k in kids)
                result[node] = (round(sum(result[k.id] * max(k.weight or 0, 0) for k in kids) / total)
                                if total else round(sum(result[k.id] for k in kids) / len(kids)))
            else:
                result[node] = leaf_progress(by_id[node], done_id)

    for root in roots:
        if root in by_id:
            compute(root)
    return result


def weighted_average(rows, progress: dict) -> int:
    rows = list(rows)
    if not rows:
        return 0
    total = sum(max(r.weight or 0, 0) for r in rows)
    if not total:
        return round(sum(progress[r.id] for r in rows) / len(rows))
    return round(sum(progress[r.id] * max(r.weight or 0, 0) for r in rows) / total)
