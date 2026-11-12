import pytest

from app import create_app
from app.extensions import db as _db
from app.modules.people.service import PersonService as UserService
from seed.cli import seed_base


@pytest.fixture()
def app():
    app = create_app("testing")
    with app.app_context():
        _db.create_all()
        seed_base()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def db(app):
    return _db


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def admin(app):
    from app.modules.auth.models import User
    return _db.session.scalar(_db.select(User).where(User.is_admin.is_(True)))


@pytest.fixture()
def make_user(app, admin):
    def _make(email="user@example.com", name="Normal User", password="Password123", is_admin=False):
        return UserService(admin).create(
            {"email": email, "full_name": name, "password": password, "is_admin": is_admin}
        )
    return _make


def login(client, email, password):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


@pytest.fixture()
def admin_client(client, app):
    resp = login(client, app.config["SEED_ADMIN_EMAIL"], app.config["SEED_ADMIN_PASSWORD"])
    assert resp.status_code == 200
    return client


@pytest.fixture()
def demo(app):
    """Demo organisation: Technology > Engineering > Platform/Mobile teams, Operations > Support, etc."""
    from app.modules.organisation.models import Tenant
    from seed.cli import seed_demo

    seed_demo(_db.session.scalar(_db.select(Tenant)))
    return app


@pytest.fixture()
def as_user(client):
    """as_user('meera') → a test client signed in as meera@demo.local."""
    def _as(prefix, password="Password123!"):
        client.post("/api/v1/auth/logout", json={})
        resp = login(client, f"{prefix}@demo.local", password)
        assert resp.status_code == 200, resp.get_json()
        return client
    return _as


def unit_id(code):
    from app.modules.organisation.models import OrgUnit
    return _db.session.scalar(_db.select(OrgUnit.id).where(OrgUnit.code == code))


def person(prefix):
    from app.modules.auth.models import User
    return _db.session.scalar(_db.select(User).where(User.email == f"{prefix}@demo.local"))
