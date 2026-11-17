"""Approvals engine: runs an item through its approval chain.

Every function here works inside the caller's open transaction (it never commits), so a status
change, the approval request it starts and their audit rows are saved together or not at all.
`svc` is the calling CommandService; it supplies the tenant, the actor, the source and the
correlation id used for audit rows.

Flow:
1. An item's status changes to Done → `on_status_change` → `submit`: the most specific published
   chain is found, its steps are copied into a new request, and the first approver is worked out.
   With no chain the item needs no approval and counts as finished at once.
2. Each step's approver is resolved when the step starts (`resolve`):
   - the person who submitted never approves their own work: their line manager does instead;
   - someone who already approved an earlier step is not asked again (the step is skipped, with a note);
   - nobody to ask → the step is skipped or the request waits, as the step says (`when_missing`).
3. `decide`: approving needs every checklist item ticked (and a comment/evidence when the step asks);
   rejecting needs a note and sends the item back to In progress. After the last step the item is
   approved, and only then does it count towards progress.
"""
from sqlalchemy import select

from app.core.audit import record_event
from app.core.errors import Conflict, Forbidden, ValidationFailed
from app.core.models import utcnow
from app.core.tree import descendant_ids
from app.extensions import db
from app.modules.access.models import Role, UserRole
from app.modules.auth.models import User
from app.modules.config.versioning import published_chains, published_value_id
from app.modules.organisation.models import Function, OrgUnit, OrgUnitClosure
from app.modules.work.models import WorkItem, WorkItemResponsible
from app.modules.workflows.models import APPROVER_KINDS, ApprovalDecision, ApprovalRequest

STEP_FIELDS = ("id", "name", "approver_kind", "approver_role_id", "approver_person_id", "when_missing",
               "checklist", "require_evidence", "require_comment")


# ---------------------------------------------------------------------- audit helpers
def _event(svc, entity_type, entity_id, operation, *, field=None, old=None, new=None, reason=None):
    record_event(tenant_id=svc.tenant_id, actor=svc.actor, entity_type=entity_type, entity_id=entity_id,
                 operation=operation, field=field, old=old, new=new, reason=reason, source=svc.source,
                 correlation_id=svc.correlation_id)


def _set_item(svc, item, field, value, reason):
    """Change a work item field from the engine, with its own audit row."""
    old = getattr(item, field)
    if old == value:
        return
    setattr(item, field, value)
    item.updated_by_id = getattr(svc.actor, "id", None)
    _event(svc, "work_item", item.id, "update", field=field, old=old, new=value, reason=reason)


def _person_name(person_id):
    return db.session.scalar(select(User.full_name).where(User.id == person_id)) or "Someone"


# ---------------------------------------------------------------------- chain selection
def find_chain(tenant_id: int, item) -> dict | None:
    """The most specific active published chain for this item, or None (no approval needed)."""
    best = None
    for chain in published_chains(tenant_id):
        if not chain["steps"]:
            continue
        types = chain.get("item_type_ids") or []
        if types and item.item_type_id not in types:
            continue
        distance = 10_000  # organisation-wide chains are the least specific
        if chain.get("unit_id"):
            if item.unit_id is None:
                continue
            depth = db.session.scalar(select(OrgUnitClosure.depth).where(
                OrgUnitClosure.ancestor_id == chain["unit_id"], OrgUnitClosure.descendant_id == item.unit_id))
            if depth is None:
                continue
            distance = depth
        key = (distance, 0 if types else 1, chain["sort_order"], chain["id"])
        if best is None or key < best[0]:
            best = (key, chain)
    return best[1] if best else None


# ---------------------------------------------------------------------- approver resolution
def _active(person_id):
    if person_id is None:
        return None
    return db.session.scalar(select(User.id).where(User.id == person_id, User.is_active.is_(True),
                                                   User.is_deleted.is_(False)))


def _function_lead(item):
    function_id = item.function_id
    if function_id is None:  # fall back to the discipline of the people delivering it
        function_id = db.session.scalar(
            select(User.function_id).join(WorkItemResponsible, WorkItemResponsible.user_id == User.id)
            .where(WorkItemResponsible.work_item_id == item.id, User.function_id.is_not(None)).order_by(User.id))
    seen = set()
    while function_id and function_id not in seen:
        seen.add(function_id)
        fn = db.session.get(Function, function_id)
        if fn is None or fn.is_deleted:
            return None
        if _active(fn.lead_id):
            return fn.lead_id
        function_id = fn.parent_id
    return None


def _unit_head(item):
    unit_id, seen = item.unit_id, set()
    while unit_id and unit_id not in seen:
        seen.add(unit_id)
        unit = db.session.get(OrgUnit, unit_id)
        if unit is None or unit.is_deleted:
            return None
        if _active(unit.head_id):
            return unit.head_id
        unit_id = unit.parent_id
    return None


def _role_has_people(role_id):
    return bool(db.session.scalar(select(UserRole.user_id).join(User, User.id == UserRole.user_id).where(
        UserRole.role_id == role_id, User.is_active.is_(True), User.is_deleted.is_(False))))


def resolve(step: dict, item, submitter_id) -> tuple[int | None, int | None, str | None]:
    """(person id, role id, note) for a step. Both ids None means nobody can approve it."""
    kind = step["approver_kind"]
    person = role = None
    if kind == "functional_lead":
        person = _function_lead(item)
        missing = "No functional lead is set for this work's function"
    elif kind == "accountable":
        person = _active(item.accountable_id)
        missing = "The accountable owner is not an active user"
    elif kind == "unit_head":
        person = _unit_head(item)
        missing = "No head is set for this unit or the units above it"
    elif kind == "person":
        person = _active(step.get("approver_person_id"))
        missing = "The named approver is not an active user"
    elif kind == "role":
        role_id = step.get("approver_role_id")
        if role_id and _role_has_people(role_id):
            return None, role_id, None
        return None, None, "Nobody holds the approving role"
    else:
        return None, None, f"Unknown approver type “{kind}”"
    if person is None:
        return None, None, missing
    if submitter_id is not None and person == submitter_id:
        manager = _active(db.session.scalar(select(User.manager_id).where(User.id == submitter_id)))
        if manager is None:
            return None, None, f"{_person_name(submitter_id)} submitted it and cannot approve their own work; they have no manager"
        return manager, None, f"{_person_name(submitter_id)} submitted it, so their manager approves instead"
    return person, None, None


# ---------------------------------------------------------------------- lifecycle
def _record(svc, request, index, decision, *, approver_id=None, comment=None, checklist=None):
    step = request.steps[index]
    row = ApprovalDecision(tenant_id=svc.tenant_id, request_id=request.id, step_index=index, step_name=step["name"],
                           decision=decision, approver_id=approver_id, comment=comment, checklist=checklist,
                           decided_at=utcnow(), created_by_id=getattr(svc.actor, "id", None),
                           updated_by_id=getattr(svc.actor, "id", None))
    db.session.add(row)
    op = {"approved": "approve", "rejected": "reject", "skipped": "skip"}[decision]
    _event(svc, "approval_request", request.id, op, field="step", new=step["name"], reason=comment)
    return row


def _approved_by(request) -> set[int]:
    return set(db.session.scalars(select(ApprovalDecision.approver_id).where(
        ApprovalDecision.request_id == request.id, ApprovalDecision.decision == "approved",
        ApprovalDecision.approver_id.is_not(None))))


def advance(svc, request, item, start: int) -> None:
    """Start the next step that needs someone, skipping as configured; finish when none are left."""
    db.session.flush()
    approved_by = _approved_by(request)
    index = start
    while index < len(request.steps):
        step = request.steps[index]
        person, role, note = resolve(step, item, request.submitted_by_id)
        if person is not None and person in approved_by:
            _record(svc, request, index, "skipped",
                    comment=f"{_person_name(person)} already approved at an earlier step")
            index += 1
            continue
        if person is not None or role is not None:
            request.current_step, request.current_approver_id, request.current_role_id = index, person, role
            request.waiting_note = note
            _tell_approvers(svc, request, item, step, person, role)
            return
        if step.get("when_missing", "skip") == "skip":
            _record(svc, request, index, "skipped", comment=note or "Nobody to ask for this step")
            index += 1
            continue
        request.current_step, request.current_approver_id, request.current_role_id = index, None, None
        request.waiting_note = f"Waiting: {note}" if note else "Waiting for someone to fill this role"
        return
    request.status = "approved"
    request.current_step = len(request.steps)
    request.current_approver_id = request.current_role_id = request.waiting_note = None
    request.completed_at = utcnow()
    _event(svc, "approval_request", request.id, "complete", field="status", old="pending", new="approved")
    _set_item(svc, item, "approval_status", "approved", "All approvals given")
    _set_item(svc, item, "approved_at", request.completed_at, "All approvals given")
    _tell_submitter(svc, request, item, f"{item.code} {item.title} was approved",
                    "Every approval step is done; it now counts towards progress.")


def _tell_approvers(svc, request, item, step, person, role):
    from app.modules.notifications.service import item_link, notify

    people = [person] if person is not None else list(db.session.scalars(
        select(UserRole.user_id).join(User, User.id == UserRole.user_id).where(
            UserRole.role_id == role, User.is_active.is_(True), User.is_deleted.is_(False))))
    notify(svc.tenant_id, people, "approval_needed", f"Approve {item.code} {item.title}",
           body=f"Step “{step['name']}” of {request.chain_name} is waiting for you.",
           link=f"{item_link(item)}#approvals", entity=("work_item", item.id), actor=svc.actor,
           source=svc.source)


def _tell_submitter(svc, request, item, title, body):
    from app.modules.notifications.service import item_link, notify

    notify(svc.tenant_id, [request.submitted_by_id], "approval_decided", title, body=body, link=item_link(item),
           entity=("work_item", item.id), actor=svc.actor, source=svc.source)


def pending_request(item_id: int):
    return db.session.scalar(select(ApprovalRequest).where(
        ApprovalRequest.work_item_id == item_id, ApprovalRequest.status == "pending",
        ApprovalRequest.is_deleted.is_(False)))


def submit(svc, item):
    """Start approval for a completed item. Returns the request, or None when no approval is needed."""
    chain = find_chain(svc.tenant_id, item)
    if chain is None:
        _set_item(svc, item, "approval_status", None, "No approval needed")
        _set_item(svc, item, "approved_at", None, "No approval needed")
        return None
    if any(s["require_evidence"] for s in chain["steps"]) and not item.evidence_url:
        raise ValidationFailed("Add an evidence or deliverable link before marking this complete; the approvers need it",
                               {"field": "evidence_url"})
    if existing := pending_request(item.id):
        cancel(svc, existing, "Submitted again")
    actor_id = getattr(svc.actor, "id", None)
    request = ApprovalRequest(
        tenant_id=svc.tenant_id, work_item_id=item.id, chain_id=chain["id"], chain_name=chain["name"],
        steps=[{k: s.get(k) for k in STEP_FIELDS} for s in chain["steps"]], status="pending", current_step=0,
        submitted_by_id=actor_id, submitted_at=utcnow(), created_by_id=actor_id, updated_by_id=actor_id)
    db.session.add(request)
    db.session.flush()
    _event(svc, "approval_request", request.id, "create", field="work_item_id", new=item.id,
           reason=f"{item.code} marked complete; chain “{chain['name']}”")
    _set_item(svc, item, "approval_status", "pending", "Marked complete; waiting for approval")
    _set_item(svc, item, "approved_at", None, "Marked complete; waiting for approval")
    advance(svc, request, item, 0)
    return request


def cancel(svc, request, reason):
    request.status = "cancelled"
    request.completed_at = utcnow()
    request.current_approver_id = request.current_role_id = None
    _event(svc, "approval_request", request.id, "cancel", field="status", old="pending", new="cancelled", reason=reason)


def on_status_change(svc, item, old_status_id, new_status_id):
    """Called by WorkItemService whenever an item's status changes (and when one is created as Done)."""
    done = published_value_id(svc.tenant_id, "status", "done")
    if done is None or old_status_id == new_status_id:
        return
    if new_status_id == done:
        submit(svc, item)
    elif old_status_id == done:
        if request := pending_request(item.id):
            cancel(svc, request, "The item is no longer marked complete")
        _set_item(svc, item, "approval_status", None, "No longer complete")
        _set_item(svc, item, "approved_at", None, "No longer complete")


def can_decide(actor, request) -> bool:
    if actor is None or request.status != "pending":
        return False
    if request.current_approver_id is not None:
        return actor.id == request.current_approver_id
    if request.current_role_id is not None:
        return bool(db.session.scalar(select(UserRole.user_id).where(
            UserRole.user_id == actor.id, UserRole.role_id == request.current_role_id)))
    return bool(actor.is_admin)  # waiting with nobody to ask: an administrator may decide


def decide(svc, request, *, approve: bool, comment: str | None, checklist: list[str] | None):
    if request.status != "pending":
        raise Conflict("This approval is no longer waiting for a decision")
    if not can_decide(svc.actor, request):
        raise Forbidden("This step is waiting for someone else")
    item = db.session.get(WorkItem, request.work_item_id)
    index = request.current_step
    step = request.steps[index]
    comment = (comment or "").strip() or None
    if approve:
        required = step.get("checklist") or []
        ticked = [c for c in (checklist or []) if c in required]
        missing = [c for c in required if c not in ticked]
        if missing:
            raise ValidationFailed("Tick every check before approving", {"field": "checklist", "missing": missing})
        if step.get("require_comment") and not comment:
            raise ValidationFailed("Add a comment to approve this step", {"field": "comment"})
        if step.get("require_evidence") and not item.evidence_url:
            raise ValidationFailed("The item has no evidence link yet", {"field": "evidence_url"})
        _record(svc, request, index, "approved", approver_id=svc.actor.id, comment=comment, checklist=ticked)
        advance(svc, request, item, index + 1)
        return request
    if not comment:
        raise ValidationFailed("Say what must be fixed before rejecting", {"field": "comment"})
    _record(svc, request, index, "rejected", approver_id=svc.actor.id, comment=comment)
    request.status = "rejected"
    request.completed_at = utcnow()
    request.current_approver_id = request.current_role_id = request.waiting_note = None
    reason = f"Rejected at “{step['name']}”: {comment}"
    _set_item(svc, item, "approval_status", "rejected", reason)
    back = published_value_id(svc.tenant_id, "status", "in_progress")
    if back:
        _set_item(svc, item, "status_id", back, reason)
    _set_item(svc, item, "actual_end", None, reason)
    _tell_submitter(svc, request, item, f"{item.code} {item.title} was sent back", reason)
    return request


def retry(svc, request):
    """Look again for an approver of a waiting step (e.g. after a functional lead was appointed)."""
    if request.status != "pending" or request.current_approver_id or request.current_role_id:
        return request
    advance(svc, request, db.session.get(WorkItem, request.work_item_id), request.current_step)
    return request


def kind_label(kind):
    return APPROVER_KINDS.get(kind, kind)


def role_name(role_id):
    return db.session.scalar(select(Role.name).where(Role.id == role_id)) if role_id else None


def unit_items(unit_id):
    return descendant_ids(OrgUnitClosure, [unit_id])
