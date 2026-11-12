"""Who can see what. Every read of units and people goes through these helpers.

A person's visibility is the union of:
1. Role scope: all → everything; unit → own unit + descendants; own → only self
   (with 'own' scope you still see your own unit in the organisation tree, but not its people)
2. Units they head (and everything below them)
3. People in functions they lead (and sub-functions)
4. People in their reporting line (direct and indirect reports)
5. Themselves
"""
from dataclasses import dataclass, field

from flask import g, has_request_context
from sqlalchemy import false, or_, select

from app.core.tree import descendant_ids
from app.extensions import db
from app.modules.access.catalog import PERMISSION_CODES
from app.modules.access.models import SCOPES, Role, RolePermission, UserRole


@dataclass
class Access:
    permissions: set[str] = field(default_factory=set)
    scope: str = "own"

    @property
    def is_global(self) -> bool:
        return self.scope == "all"


def resolve_access(user) -> Access:
    if user.is_admin:
        return Access(set(PERMISSION_CODES), "all")
    roles = db.session.scalars(
        select(Role).join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user.id, Role.is_deleted.is_(False))
    ).all()
    perms = set(db.session.scalars(
        select(RolePermission.permission_code).where(RolePermission.role_id.in_([r.id for r in roles]))
    )) if roles else set()
    scope = max((r.scope for r in roles), key=SCOPES.index, default="own")
    return Access(perms, scope)


def clear_access_cache() -> None:
    if has_request_context():
        g.pop("_access_cache", None)
        g.pop("_scope_cache", None)


def _cached(user, key, compute):
    if not has_request_context():
        return compute()
    cache = g.setdefault("_scope_cache", {})
    if (user.id, key) not in cache:
        cache[(user.id, key)] = compute()
    return cache[(user.id, key)]


def is_global(user) -> bool:
    return user is None or user.is_admin or user.scope == "all"


def managed_unit_ids(user) -> set[int] | None:
    """Units whose PEOPLE (and later, work) the user may see and manage; None means all.

    = units they head + everything below, and — for 'unit' scope — their own unit + everything below.
    """
    if is_global(user):
        return None

    def compute():
        from app.modules.organisation.models import OrgUnit, OrgUnitClosure

        roots = set(db.session.scalars(
            select(OrgUnit.id).where(OrgUnit.head_id == user.id, OrgUnit.is_deleted.is_(False))))
        if user.unit_id and user.scope == "unit":
            roots.add(user.unit_id)
        return descendant_ids(OrgUnitClosure, roots)

    return _cached(user, "units", compute)


def visible_unit_ids(user) -> set[int] | None:
    """Units shown in the organisation tree: the managed area plus the user's own unit."""
    managed = managed_unit_ids(user)
    if managed is None:
        return None
    return managed | ({user.unit_id} if user.unit_id else set())


def led_function_ids(user) -> set[int]:
    def compute():
        from app.modules.organisation.models import Function, FunctionClosure

        roots = set(db.session.scalars(
            select(Function.id).where(Function.lead_id == user.id, Function.is_deleted.is_(False))))
        return descendant_ids(FunctionClosure, roots)

    return _cached(user, "functions", compute)


def report_ids(user) -> set[int]:
    """Everyone in the user's reporting line (direct and indirect reports)."""
    def compute():
        from app.modules.auth.models import User

        found, frontier = set(), {user.id}
        while frontier:
            nxt = set(db.session.scalars(select(User.id).where(User.manager_id.in_(frontier)))) - found - {user.id}
            found |= nxt
            frontier = nxt
        return found

    return _cached(user, "reports", compute)


def person_visibility_clause(user):
    """SQL condition limiting a User query to people this user may see."""
    from app.modules.auth.models import User

    if is_global(user):
        return None
    units = managed_unit_ids(user)
    conditions = [User.id == user.id]
    if units:
        conditions.append(User.unit_id.in_(units))
    if functions := led_function_ids(user):
        conditions.append(User.function_id.in_(functions))
    if reports := report_ids(user):
        conditions.append(User.id.in_(reports))
    return or_(*conditions) if conditions else false()


def unit_visibility_clause(user):
    from app.modules.organisation.models import OrgUnit

    units = visible_unit_ids(user)
    if units is None:
        return None
    return OrgUnit.id.in_(units) if units else false()
