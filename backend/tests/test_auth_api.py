from tests.conftest import login


def test_health(client):
    assert client.get("/api/v1/health").get_json() == {"status": "ok"}


def test_login_success_and_me(client, app):
    resp = login(client, app.config["SEED_ADMIN_EMAIL"], app.config["SEED_ADMIN_PASSWORD"])
    assert resp.status_code == 200
    assert resp.get_json()["user"]["is_admin"] is True
    me = client.get("/api/v1/auth/me").get_json()["user"]
    assert me["email"] == app.config["SEED_ADMIN_EMAIL"]
    assert "password_hash" not in me


def test_login_wrong_password(client, app):
    resp = login(client, app.config["SEED_ADMIN_EMAIL"], "wrong")
    assert resp.status_code == 401
    assert resp.get_json()["error"]["code"] == "unauthorized"


def test_me_requires_login(client):
    assert client.get("/api/v1/auth/me").status_code == 401


def test_logout(admin_client):
    admin_client.post("/api/v1/auth/logout", json={})
    assert admin_client.get("/api/v1/auth/me").status_code == 401


def test_mutating_requests_must_be_json(client):
    resp = client.post("/api/v1/auth/login", data={"email": "a", "password": "b"})
    assert resp.status_code == 422


def test_inactive_user_cannot_login(client, make_user, admin):
    from app.modules.people.service import PersonService as UserService
    user = make_user()
    UserService(admin).update(user.id, {"is_active": False})
    assert login(client, "user@example.com", "Password123").status_code == 401


def test_unknown_api_route_returns_json(client):
    resp = client.get("/api/v1/nope")
    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "not_found"
