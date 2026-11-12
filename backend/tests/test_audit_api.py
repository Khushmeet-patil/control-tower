from tests.conftest import login


def test_admin_can_list_audit_events_newest_first(admin_client):
    data = admin_client.get("/api/v1/audit-events").get_json()
    assert data["total"] >= 2  # admin create + login
    assert data["items"][0]["operation"] == "login"


def test_filters_and_pagination(admin_client, make_user):
    for i in range(3):
        make_user(email=f"u{i}@example.com", name=f"User {i}")
    data = admin_client.get("/api/v1/audit-events?operation=create&entity_type=person&per_page=2&page=1").get_json()
    assert data["per_page"] == 2 and len(data["items"]) == 2
    assert data["total"] == 4 and data["pages"] == 2  # seeded admin + 3 new people
    assert all(i["operation"] == "create" and i["entity_type"] == "person" for i in data["items"])


def test_unknown_filter_is_rejected(admin_client):
    assert admin_client.get("/api/v1/audit-events?password=x").status_code == 422


def test_facets(admin_client):
    data = admin_client.get("/api/v1/audit-events/facets").get_json()
    assert "person" in data["entity_type"] and "create" in data["operation"]


def test_non_admin_cannot_read_audit(client, make_user):
    make_user()
    login(client, "user@example.com", "Password123")
    assert client.get("/api/v1/audit-events").status_code == 403
