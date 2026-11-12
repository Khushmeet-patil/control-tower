import pytest

from app.core.errors import Conflict, ValidationFailed
from app.modules.access.models import Role
from app.modules.access.service import RoleService
from app.extensions import db
from tests.conftest import person


def role(code):
    return db.session.scalar(db.select(Role).where(Role.code == code))


def test_editing_role_permissions_changes_access(demo, as_user, admin):
    c = as_user("arjun")
    assert c.get("/api/v1/audit-events").status_code == 403
    perms = role("contributor").permission_codes + ["audit.view"]
    RoleService(admin).update(role("contributor").id, {"permission_codes": perms}, reason="Transparency")
    assert c.get("/api/v1/audit-events").status_code == 200  # no code change needed


def test_widening_scope_widens_visibility(demo, as_user, admin):
    c = as_user("arjun")
    assert c.get("/api/v1/people").get_json()["total"] == 1
    RoleService(admin).update(role("contributor").id, {"scope": "unit"})
    assert c.get("/api/v1/people").get_json()["total"] > 1


def test_unknown_permission_rejected(admin):
    with pytest.raises(ValidationFailed):
        RoleService(admin).create({"code": "x", "name": "X", "permission_codes": ["launch.rockets"]})


def test_built_in_and_assigned_roles_cannot_be_deleted(demo, admin):
    with pytest.raises(Conflict):
        RoleService(admin).delete(role("manager").id)
    custom = RoleService(admin).create({"code": "auditor", "name": "Auditor", "permission_codes": ["audit.view"]})
    RoleService(admin).delete(custom.id)


def test_only_one_default_role(demo, admin):
    RoleService(admin).update(role("viewer").id, {"is_default": True})
    assert role("viewer").is_default and not role("contributor").is_default


def test_roles_api_lists_catalog(admin_client):
    data = admin_client.get("/api/v1/permissions").get_json()
    assert "org.manage" in {p["code"] for p in data["items"]} and data["scopes"] == ["own", "unit", "all"]
