"""The one-write-path guarantees: audit on success, nothing on failure, safe conflicts."""
import pytest

from app.core.audit import AuditEvent
from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.modules.auth.models import User
from app.modules.people.service import PersonService as UserService


def audit_rows(db, **filters):
    stmt = db.select(AuditEvent).filter_by(**filters).order_by(AuditEvent.id)
    return db.session.scalars(stmt).all()


def test_create_writes_one_audit_row_with_masked_password(db, make_user):
    user = make_user()
    rows = audit_rows(db, entity_type="person", entity_id=user.id)
    assert [r.operation for r in rows] == ["create"]
    assert "Password123" not in rows[0].new_value
    assert "••••••" in rows[0].new_value
    assert rows[0].actor_name == "Platform Administrator"


def test_update_writes_one_row_per_changed_field(db, admin, make_user):
    user = make_user()
    UserService(admin).update(user.id, {"full_name": "Renamed", "is_admin": False}, reason="Name fix")
    rows = audit_rows(db, entity_type="person", entity_id=user.id, operation="update")
    assert len(rows) == 1  # is_admin did not change
    assert rows[0].field == "full_name"
    assert rows[0].old_value == '"Normal User"' and rows[0].new_value == '"Renamed"'
    assert rows[0].reason == "Name fix"


def test_failed_validation_leaves_no_record_and_no_audit(db, admin):
    before = len(audit_rows(db))
    with pytest.raises(ValidationFailed):
        UserService(admin).create({"email": "x@example.com", "full_name": "X", "password": "short"})
    assert len(audit_rows(db)) == before
    assert db.session.scalar(db.select(User).where(User.email == "x@example.com")) is None


def test_database_error_rolls_back_audit_too(db, admin, make_user):
    make_user(email="dup@example.com")

    class NoCheckService(UserService):
        def validate_create(self, data):  # skip the friendly duplicate check
            data["email"] = data["email"].lower()

    before = len(audit_rows(db))
    with pytest.raises(Conflict):
        NoCheckService(admin).create({"email": "dup@example.com", "full_name": "Dup", "password": "Password123"})
    assert len(audit_rows(db)) == before


def test_stale_version_is_rejected(admin, make_user):
    user = make_user()
    with pytest.raises(Conflict):
        UserService(admin).update(user.id, {"full_name": "Late edit"}, expected_version=user.version - 1)


def test_version_increments_on_update(admin, make_user):
    user = make_user()
    v = user.version
    UserService(admin).update(user.id, {"full_name": "Changed"})
    assert user.version == v + 1


def test_system_and_unknown_fields_are_rejected(admin, make_user):
    user = make_user()
    for bad in ({"id": 99}, {"tenant_id": 2}, {"password_hash": "x"}, {"not_a_field": 1}):
        with pytest.raises(ValidationFailed):
            UserService(admin).update(user.id, bad)


def test_soft_delete_hides_record_and_is_audited(db, admin, make_user):
    user = make_user()
    UserService(admin).delete(user.id, reason="Left company")
    with pytest.raises(NotFound):
        UserService(admin).get(user.id)
    assert db.session.get(User, user.id) is not None  # row kept for history
    assert audit_rows(db, entity_id=user.id, operation="delete")[0].reason == "Left company"


def test_non_admin_without_permission_is_forbidden(make_user):
    user = make_user()
    with pytest.raises(Forbidden):
        UserService(user).create({"email": "y@example.com", "full_name": "Y", "password": "Password123"})


def test_one_request_shares_one_correlation_id(app, db, admin):
    with app.test_request_context("/"):
        svc = UserService(admin)
        a = svc.create({"email": "a@example.com", "full_name": "A", "password": "Password123"})
        svc.update(a.id, {"full_name": "A2"})
        ids = {r.correlation_id for r in audit_rows(db, entity_type="person", entity_id=a.id)}
    assert len(ids) == 1
