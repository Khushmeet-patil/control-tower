"""Approval chains (settings draft) and approval requests (inbox, decisions)."""
import re

from sqlalchemy import func, or_, select

from app.core.command import CommandService
from app.core.dates import today
from app.core.errors import Forbidden, ValidationFailed
from app.core.pagination import paginate
from app.extensions import db
from app.modules.access.models import Role, UserRole
from app.modules.auth.models import User
from app.modules.lookups.models import LookupType, LookupValue
from app.modules.lookups.service import _keep_order_if_empty, _no_code_change
from app.modules.organisation.models import OrgUnit
from app.modules.work.models import WorkItem
from app.modules.work.service import MANAGE as MANAGE_LEVEL, WorkItemService, person_ref
from app.modules.workflows import engine
from app.modules.workflows.models import (
    APPROVER_KINDS, WHEN_MISSING, ApprovalChain, ApprovalDecision, ApprovalRequest, ApprovalStep, StatusTransition)

SETTINGS = {"create": "settings.manage", "update": "settings.manage", "delete": "settings.manage"}
CODE = re.compile(r"^[a-z][a-z0-9_]{1,49}$")
MAX_CHECKS, MAX_CHECK_LENGTH = 12, 300


# ---------------------------------------------------------------------- settings: chains and steps
class ChainService(CommandService):
    model = ApprovalChain
    entity_type = "approval_chain"
    permissions = SETTINGS

    def _check(self, data):
        if "item_type_ids" in data:
            ids = sorted(set(data["item_type_ids"] or []))
            found = set(db.session.scalars(
                select(LookupValue.id).join(LookupType, LookupType.id == LookupValue.lookup_type_id)
                .where(LookupType.tenant_id == self.tenant_id, LookupType.code == "item_type", LookupValue.id.in_(ids))))
            if found != set(ids):
                raise ValidationFailed("Unknown item type", {"field": "item_type_ids"})
            data["item_type_ids"] = ids or None
        if data.get("unit_id") is not None:
            unit = db.session.get(OrgUnit, data["unit_id"])
            if unit is None or unit.tenant_id != self.tenant_id or unit.is_deleted:
                raise ValidationFailed("Unit not found", {"field": "unit_id"})

    def validate_create(self, data):
        if not CODE.match(data.get("code") or ""):
            raise ValidationFailed("Use lowercase letters, numbers and _ (start with a letter)", {"field": "code"})
        if db.session.scalar(select(ApprovalChain.id).where(ApprovalChain.tenant_id == self.tenant_id,
                                                            ApprovalChain.code == data["code"])):
            raise ValidationFailed("This code is already used", {"field": "code"})
        if data.get("sort_order") is None:
            last = db.session.scalar(select(func.max(ApprovalChain.sort_order)).where(
                ApprovalChain.tenant_id == self.tenant_id))
            data["sort_order"] = (last or 0) + 10
        self._check(data)

    def validate_update(self, obj, changes):
        _no_code_change(obj, changes, "code")
        _keep_order_if_empty(changes)
        self._check(changes)

    def delete(self, record_id, *, reason=None):
        raise ValidationFailed("Chains are never deleted, so past approvals keep their history; retire them instead")

    def list_all(self):
        chains = db.session.scalars(self.base_query().order_by(ApprovalChain.sort_order, ApprovalChain.name)).all()
        steps = db.session.scalars(select(ApprovalStep).where(
            ApprovalStep.tenant_id == self.tenant_id, ApprovalStep.is_deleted.is_(False))
            .order_by(ApprovalStep.sort_order, ApprovalStep.id)).all()
        by_chain = {}
        for st in steps:
            by_chain.setdefault(st.chain_id, []).append(serialize_step(st))
        return [serialize_chain(c, by_chain.get(c.id, [])) for c in chains]


class StepService(CommandService):
    model = ApprovalStep
    entity_type = "approval_step"
    permissions = SETTINGS

    def _check(self, data, obj=None):
        merged = lambda f: data.get(f, getattr(obj, f, None))  # noqa: E731
        kind = merged("approver_kind")
        if kind not in APPROVER_KINDS:
            raise ValidationFailed("Choose who approves", {"field": "approver_kind"})
        if merged("when_missing") not in WHEN_MISSING:
            raise ValidationFailed("Choose what happens when nobody can approve", {"field": "when_missing"})
        # Only the reference that matches the approver type is kept.
        if kind == "role":
            role = db.session.get(Role, merged("approver_role_id")) if merged("approver_role_id") else None
            if role is None or role.tenant_id != self.tenant_id or role.is_deleted:
                raise ValidationFailed("Choose the approving role", {"field": "approver_role_id"})
        elif "approver_role_id" in data or (obj and obj.approver_role_id):
            data["approver_role_id"] = None
        if kind == "person":
            person = merged("approver_person_id")
            if not db.session.scalar(select(User.id).where(User.id == person, User.tenant_id == self.tenant_id,
                                                           User.is_deleted.is_(False))):
                raise ValidationFailed("Choose the approver", {"field": "approver_person_id"})
        elif "approver_person_id" in data or (obj and obj.approver_person_id):
            data["approver_person_id"] = None
        if "checklist" in data:
            checks = [c.strip() for c in (data["checklist"] or []) if c and c.strip()]
            if len(checks) > MAX_CHECKS or any(len(c) > MAX_CHECK_LENGTH for c in checks):
                raise ValidationFailed(f"Use at most {MAX_CHECKS} checks of {MAX_CHECK_LENGTH} characters",
                                       {"field": "checklist"})
            if len(set(checks)) != len(checks):
                raise ValidationFailed("Each check must be different", {"field": "checklist"})
            data["checklist"] = checks or None

    def validate_create(self, data):
        chain = db.session.get(ApprovalChain, data.get("chain_id")) if data.get("chain_id") else None
        if chain is None or chain.tenant_id != self.tenant_id or chain.is_deleted:
            raise ValidationFailed("Choose a chain", {"field": "chain_id"})
        data.setdefault("when_missing", "skip")
        if data.get("sort_order") is None:
            last = db.session.scalar(select(func.max(ApprovalStep.sort_order)).where(ApprovalStep.chain_id == chain.id))
            data["sort_order"] = (last or 0) + 10
        self._check(data)

    def validate_update(self, obj, changes):
        _no_code_change(obj, changes, "chain_id")
        _keep_order_if_empty(changes)
        self._check(changes, obj)

    def delete(self, record_id, *, reason=None):
        raise ValidationFailed("Steps are never deleted; retire them instead")


def serialize_chain(c, steps=None):
    unit = db.session.get(OrgUnit, c.unit_id) if c.unit_id else None
    return {
        "id": c.id, "code": c.code, "name": c.name, "description": c.description,
        "item_type_ids": c.item_type_ids or [], "unit_id": c.unit_id, "unit": {"id": unit.id, "name": unit.name} if unit else None,
        "sort_order": c.sort_order, "is_active": c.is_active, "version": c.version,
        **({"steps": steps} if steps is not None else {}),
    }


def serialize_step(st):
    person = db.session.get(User, st.approver_person_id) if st.approver_person_id else None
    return {
        "id": st.id, "chain_id": st.chain_id, "name": st.name, "sort_order": st.sort_order,
        "approver_kind": st.approver_kind, "approver_kind_label": engine.kind_label(st.approver_kind),
        "approver_role_id": st.approver_role_id, "approver_role": engine.role_name(st.approver_role_id),
        "approver_person_id": st.approver_person_id, "approver_person": person_ref(person),
        "when_missing": st.when_missing, "checklist": st.checklist or [],
        "require_evidence": st.require_evidence, "require_comment": st.require_comment,
        "is_active": st.is_active, "version": st.version,
    }


# ---------------------------------------------------------------------- approval requests
class ApprovalService(CommandService):
    """Reads and decisions on approval requests. Requests are created by the engine, never directly."""

    model = ApprovalRequest
    entity_type = "approval_request"
    permissions = {"create": "work.view", "update": "work.view", "delete": "work.view"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.items = WorkItemService(self.actor, tenant_id=self.tenant_id, source=self.source,
                                     correlation_id=self.correlation_id)

    def create(self, data, reason=None):
        raise ValidationFailed("Approvals start when an item is marked complete")

    def base_query(self):
        visible = self.items.base_query().with_only_columns(WorkItem.id)
        return super().base_query().where(ApprovalRequest.work_item_id.in_(visible))

    # ---- inbox
    def _waiting_for_me(self):
        my_roles = select(UserRole.role_id).where(UserRole.user_id == self.actor.id)
        return or_(ApprovalRequest.current_approver_id == self.actor.id,
                   ApprovalRequest.current_role_id.in_(my_roles))

    def _blocked(self):
        return ApprovalRequest.current_approver_id.is_(None) & ApprovalRequest.current_role_id.is_(None)

    def inbox(self, params):
        params = dict(params)
        box = params.pop("box", "mine")
        stmt = self.base_query()
        pending = ApprovalRequest.status == "pending"
        if box == "mine":
            stmt = stmt.where(pending, self._waiting_for_me()).order_by(ApprovalRequest.submitted_at)
        elif box == "submitted":
            stmt = stmt.where(ApprovalRequest.submitted_by_id == self.actor.id).order_by(ApprovalRequest.submitted_at.desc())
        elif box == "decided":
            mine = select(ApprovalDecision.request_id).where(ApprovalDecision.approver_id == self.actor.id,
                                                             ApprovalDecision.decision.in_(["approved", "rejected"]))
            stmt = stmt.where(ApprovalRequest.id.in_(mine)).order_by(ApprovalRequest.updated_at.desc())
        elif box == "blocked":
            stmt = stmt.where(pending, self._blocked()).order_by(ApprovalRequest.submitted_at)
        elif box == "item":
            stmt = stmt.where(ApprovalRequest.work_item_id == int(params.pop("work_item_id"))) \
                .order_by(ApprovalRequest.id.desc())
        elif box == "all":
            if status := params.pop("status", None):
                stmt = stmt.where(ApprovalRequest.status == status)
            stmt = stmt.order_by(ApprovalRequest.submitted_at.desc())
        else:
            raise ValidationFailed(f"Unknown box '{box}'")
        stmt = stmt.order_by(ApprovalRequest.id.desc())
        return paginate(stmt, params, self.serialize)

    def counts(self):
        pending = self.base_query().where(ApprovalRequest.status == "pending")
        count = lambda stmt: db.session.scalar(select(func.count()).select_from(stmt.subquery()))  # noqa: E731
        return {
            "waiting_for_me": count(pending.where(self._waiting_for_me())),
            "submitted_pending": count(pending.where(ApprovalRequest.submitted_by_id == self.actor.id)),
            "blocked": count(pending.where(self._blocked())),
        }

    # ---- one request
    def serialize(self, r, detail=False):
        decisions = db.session.scalars(select(ApprovalDecision).where(ApprovalDecision.request_id == r.id)
                                       .order_by(ApprovalDecision.id)).all()
        by_step = {}
        for d in decisions:
            by_step[d.step_index] = d
        steps = []
        for index, st in enumerate(r.steps):
            d = by_step.get(index)
            if d is not None:
                state = d.decision
            elif r.status == "pending" and index == r.current_step:
                state = "waiting" if (r.current_approver_id or r.current_role_id) else "blocked"
            elif r.status == "pending" and index > r.current_step:
                state = "upcoming"
            else:
                state = "not_reached"
            steps.append({
                "index": index, "name": st["name"], "approver_kind": st["approver_kind"],
                "approver_kind_label": engine.kind_label(st["approver_kind"]), "checklist": st.get("checklist") or [],
                "require_evidence": bool(st.get("require_evidence")), "require_comment": bool(st.get("require_comment")),
                "state": state, "decision": serialize_decision(d) if d else None,
            })
        item = r.work_item
        is_current = r.status == "pending" and r.current_step < len(r.steps)
        out = {
            "id": r.id, "status": r.status, "chain_name": r.chain_name,
            "work_item": {"id": item.id, "code": item.code, "title": item.title, "item_type_id": item.item_type_id,
                          "status_id": item.status_id, "evidence_url": item.evidence_url,
                          "accountable": person_ref(item.accountable), "unit": {"id": item.unit.id, "name": item.unit.name} if item.unit else None},
            "step_count": len(r.steps), "current_step": r.current_step if is_current else None,
            "current_step_name": r.steps[r.current_step]["name"] if is_current else None,
            "current_approver": person_ref(r.current_approver) if is_current else None,
            "current_role": engine.role_name(r.current_role_id) if is_current else None,
            "is_blocked": is_current and not (r.current_approver_id or r.current_role_id),
            "waiting_note": r.waiting_note,
            "submitted_by": person_ref(r.submitted_by), "submitted_at": r.submitted_at.isoformat(),
            "waiting_days": (today() - r.submitted_at.date()).days if r.status == "pending" else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "steps": steps,
            "can_decide": engine.can_decide(self.actor, r),
            "can_withdraw": self._can_withdraw(r),
            "can_retry": r.status == "pending" and is_current and not (r.current_approver_id or r.current_role_id)
            and self._manages(r),
            "version": r.version,
        }
        if detail:
            out["decisions"] = [serialize_decision(d) for d in decisions]
        return out

    def detail(self, request_id):
        return self.serialize(self.get(request_id), detail=True)

    def _manages(self, r):
        return self.actor is None or self.actor.is_admin or \
            self.items.access(self.items.get(r.work_item_id)) == MANAGE_LEVEL

    def _can_withdraw(self, r):
        if r.status != "pending" or self.actor is None:
            return False
        return r.submitted_by_id == self.actor.id or self._manages(r)

    # ---- actions
    def decide(self, request_id, *, approve, comment=None, checklist=None, expected_version=None):
        r = self.get(request_id)
        self._check_version(r, expected_version)
        with self._transaction():
            engine.decide(self, r, approve=approve, comment=comment, checklist=checklist)
        return r

    def withdraw(self, request_id, reason=None):
        """Take back a completion claim: the request is cancelled and the item returns to In progress."""
        r = self.get(request_id)
        if not self._can_withdraw(r):
            raise Forbidden("Only the person who submitted it or the item's managers can withdraw it")
        with self._transaction():
            engine.cancel(self, r, reason or "Withdrawn")
            item = db.session.get(WorkItem, r.work_item_id)
            note = reason or "Approval withdrawn"
            engine._set_item(self, item, "approval_status", None, note)
            back = engine.published_value_id(self.tenant_id, "status", "in_progress")
            if back:
                engine._set_item(self, item, "status_id", back, note)
            engine._set_item(self, item, "actual_end", None, note)
        return r

    def retry(self, request_id):
        r = self.get(request_id)
        if not self._manages(r):
            raise Forbidden("Only the item's managers can look for an approver again")
        with self._transaction():
            engine.retry(self, r)
        return r

    @staticmethod
    def _check_version(r, expected):
        from app.core.errors import Conflict

        if expected is not None and r.version != expected:
            raise Conflict("This approval changed while you were looking at it. Reload and try again.")


def serialize_decision(d):
    return {
        "id": d.id, "step_index": d.step_index, "step_name": d.step_name, "decision": d.decision,
        "approver": person_ref(d.approver), "comment": d.comment, "checklist": d.checklist or [],
        "decided_at": d.decided_at.isoformat(),
    }


# ---------------------------------------------------------------------- settings: status transitions
class TransitionService(CommandService):
    """Allowed status changes per item type (draft settings; enforced once published)."""

    model = StatusTransition
    entity_type = "status_transition"
    permissions = SETTINGS

    def _values(self, list_code):
        return set(db.session.scalars(
            select(LookupValue.id).join(LookupType, LookupType.id == LookupValue.lookup_type_id)
            .where(LookupType.tenant_id == self.tenant_id, LookupType.code == list_code)))

    def _check(self, data, obj=None):
        statuses = self._values("status")
        if "item_type_id" in data and data["item_type_id"] is not None and data["item_type_id"] not in self._values("item_type"):
            raise ValidationFailed("Unknown item type", {"field": "item_type_id"})
        if "from_status_id" in data and data["from_status_id"] not in statuses:
            raise ValidationFailed("Choose the status it moves from", {"field": "from_status_id"})
        if "to_status_ids" in data:
            ids = sorted(set(data["to_status_ids"] or []))
            if set(ids) - statuses:
                raise ValidationFailed("Unknown status", {"field": "to_status_ids"})
            data["to_status_ids"] = ids
        item_type = data.get("item_type_id", getattr(obj, "item_type_id", None))
        from_status = data.get("from_status_id", getattr(obj, "from_status_id", None))
        stmt = select(StatusTransition.id).where(
            StatusTransition.tenant_id == self.tenant_id, StatusTransition.is_deleted.is_(False),
            StatusTransition.from_status_id == from_status,
            StatusTransition.item_type_id.is_(None) if item_type is None else StatusTransition.item_type_id == item_type)
        if obj is not None:
            stmt = stmt.where(StatusTransition.id != obj.id)
        if db.session.scalar(stmt):
            raise ValidationFailed("There is already a rule for this status and item type; edit that one",
                                   {"field": "from_status_id"})

    def validate_create(self, data):
        if data.get("from_status_id") is None:
            raise ValidationFailed("Choose the status it moves from", {"field": "from_status_id"})
        data.setdefault("to_status_ids", [])
        self._check(data)

    def validate_update(self, obj, changes):
        self._check(changes, obj)

    def delete(self, record_id, *, reason=None):
        raise ValidationFailed("Rules are kept for the settings history; switch them off instead")

    def list_all(self):
        return [serialize_transition(t) for t in db.session.scalars(
            self.base_query().order_by(StatusTransition.item_type_id, StatusTransition.from_status_id))]


def serialize_transition(t: StatusTransition) -> dict:
    return {"id": t.id, "item_type_id": t.item_type_id, "from_status_id": t.from_status_id,
            "to_status_ids": t.to_status_ids or [], "is_active": t.is_active, "version": t.version}
