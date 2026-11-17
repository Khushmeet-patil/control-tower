"""Phase 9 security review: each fix is pinned by a test (see docs/SECURITY_REVIEW.md)."""
from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app import _check_secret_key, create_app
from app.core.audit import AuditEvent
from app.core.models import utcnow
from app.extensions import db
from app.modules.access.models import Role
from tests.conftest import person


def sign_in(client, who, password="Password123!"):
    return client.post("/api/v1/auth/login", json={"email": f"{who}@demo.local", "password": password})


# ---------------------------------------------------------------------- sign-in protection
def test_account_locks_after_repeated_wrong_passwords(demo, client):
    for _ in range(5):
        assert sign_in(client, "arjun", "wrong-password").status_code == 401
    locked = sign_in(client, "arjun")  # even the right password waits now
    assert locked.status_code == 401 and "Try again in" in locked.get_json()["error"]["message"]
    ops = [e.operation for e in db.session.scalars(select(AuditEvent).where(
        AuditEvent.entity_type == "person", AuditEvent.entity_id == person("arjun").id))]
    assert ops.count("login_failed") == 5 and "locked" in ops

    arjun = person("arjun")
    arjun.locked_until = utcnow() - timedelta(minutes=1)  # the lock has run out
    db.session.commit()
    assert sign_in(client, "arjun").status_code == 200
    assert person("arjun").failed_logins == 0


def test_unknown_emails_get_the_same_answer(demo, client):
    unknown = client.post("/api/v1/auth/login", json={"email": "nobody@demo.local", "password": "whatever-123"})
    wrong = sign_in(client, "arjun", "whatever-123")
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.get_json()["error"]["message"] == wrong.get_json()["error"]["message"]


def test_password_reset_signs_out_other_sessions(demo, app):
    victim, admin_client = app.test_client(), app.test_client()
    assert sign_in(victim, "arjun").status_code == 200
    assert victim.get("/api/v1/auth/me").status_code == 200
    admin_client.post("/api/v1/auth/login", json={"email": app.config["SEED_ADMIN_EMAIL"],
                                                  "password": app.config["SEED_ADMIN_PASSWORD"]})
    resp = admin_client.post(f"/api/v1/people/{person('arjun').id}/reset-password",
                             json={"password": "BrandNew123!", "reason": "Laptop stolen"})
    assert resp.status_code == 200, resp.get_json()
    assert victim.get("/api/v1/auth/me").status_code == 401


def test_changing_your_own_password_keeps_you_signed_in_here(demo, app):
    here, elsewhere = app.test_client(), app.test_client()
    sign_in(here, "arjun")
    sign_in(elsewhere, "arjun")
    resp = here.post("/api/v1/auth/change-password", json={"current_password": "Password123!", "new_password": "Another123!"})
    assert resp.status_code == 200
    assert here.get("/api/v1/auth/me").status_code == 200
    assert elsewhere.get("/api/v1/auth/me").status_code == 401


# ---------------------------------------------------------------------- configuration and headers
def test_production_refuses_a_weak_secret_key():
    for key in ("dev-only-insecure-key", "short"):
        with pytest.raises(RuntimeError):
            _check_secret_key(SimpleNamespace(debug=False, testing=False, config={"SECRET_KEY": key}))
    _check_secret_key(SimpleNamespace(debug=False, testing=False, config={"SECRET_KEY": "x" * 48}))


def test_security_headers(client):
    resp = client.get("/api/v1/health")
    assert "script-src 'self'" in resp.headers["Content-Security-Policy"]
    assert "frame-ancestors 'self'" in resp.headers["Content-Security-Policy"]
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["Cache-Control"] == "no-store"


def test_oversized_requests_are_refused(admin_client):
    resp = admin_client.post("/api/v1/imports", data="x" * (13 * 1024 * 1024), content_type="application/json")
    assert resp.status_code == 413


def test_production_cookies_are_secure():
    from app.config import ProductionConfig

    assert ProductionConfig.SESSION_COOKIE_SECURE and ProductionConfig.REMEMBER_COOKIE_SECURE
    assert ProductionConfig.REMEMBER_COOKIE_DURATION.days <= 14


# ---------------------------------------------------------------------- privilege escalation
@pytest.fixture()
def role_manager(demo, admin):
    """Karan also manages roles, but is no administrator."""
    from app.modules.access.service import RoleService
    from app.modules.people.service import PersonService

    role = RoleService(admin).create({"code": "role_mgr", "name": "Role manager", "scope": "unit",
                                      "permission_codes": ["roles.manage", "people.view", "people.manage", "org.view"]})
    karan = person("karan")
    PersonService(admin).update(karan.id, {"role_ids": sorted(set(PersonService(admin).read_value(karan, "role_ids")) | {role.id})})
    return karan


def test_role_managers_cannot_grant_more_than_they_hold(role_manager, as_user):
    c = as_user("karan")
    admin_role = db.session.scalar(select(Role.id).where(Role.code == "administrator"))
    executive = db.session.scalar(select(Role.id).where(Role.code == "executive"))
    karan = person("karan")
    current = [r for r in c.get(f"/api/v1/people/{karan.id}").get_json()["role_ids"]]
    for role_id in (admin_role, executive):  # all permissions / organisation-wide scope
        resp = c.patch(f"/api/v1/people/{karan.id}", json={"role_ids": current + [role_id]})
        assert resp.status_code == 403, resp.get_json()
    assert c.post("/api/v1/roles", json={"code": "sneaky", "name": "Sneaky", "scope": "unit",
                                         "permission_codes": ["audit.view"]}).status_code == 403
    assert c.post("/api/v1/roles", json={"code": "wide", "name": "Wide", "scope": "all",
                                         "permission_codes": ["people.view"]}).status_code == 403
    mine = db.session.scalar(select(Role.id).where(Role.code == "role_mgr"))
    assert c.patch(f"/api/v1/roles/{mine}", json={"permission_codes": ["roles.manage", "settings.manage"]}).status_code == 403
    # Within their own access it still works.
    assert c.post("/api/v1/roles", json={"code": "viewer2", "name": "Viewer 2", "scope": "own",
                                         "permission_codes": ["people.view"]}).status_code == 201


def test_evidence_links_must_be_web_addresses(demo, as_user):
    from app.modules.work.models import WorkItem

    c = as_user("asha")
    portal = db.session.scalar(select(WorkItem).where(WorkItem.code == "PRJ-001"))
    for bad in ("javascript:alert(1)", "data:text/html,<script>alert(1)</script>"):
        resp = c.patch(f"/api/v1/work-items/{portal.id}", json={"evidence_url": bad, "version": portal.version})
        assert resp.status_code == 422, bad
