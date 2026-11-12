"""Who sees what — the Phase 1 'Done when' checks."""
from tests.conftest import unit_id


def names(resp):
    return {p["full_name"] for p in resp.get_json()["items"]}


def unit_codes(client):
    return {u["code"] for u in client.get("/api/v1/units").get_json()["items"]}


def test_manager_sees_only_own_branch(demo, as_user):
    c = as_user("meera")  # Engineering
    assert unit_codes(c) == {"ENG", "PLAT", "MOB"}
    people = names(c.get("/api/v1/people?per_page=100"))
    assert {"Arjun Nair", "Isha Gupta", "Karan Mehta"} <= people
    assert "Leela Menon" not in people  # Support team, other branch


def test_contributor_cannot_open_another_branch(demo, as_user):
    c = as_user("arjun")
    assert c.get(f"/api/v1/units/{unit_id('SUP')}").status_code == 404
    leela = c.get("/api/v1/people?q=Leela").get_json()
    assert leela["total"] == 0
    assert unit_codes(c) == {"PLAT"}


def test_contributor_sees_only_self(demo, as_user):
    assert names(as_user("arjun").get("/api/v1/people")) == {"Arjun Nair"}


def test_executive_sees_everything(demo, as_user):
    c = as_user("asha")
    assert {"ORG", "OPS", "SUP", "PLAT"} <= unit_codes(c)
    assert "Leela Menon" in names(c.get("/api/v1/people?per_page=100"))


def test_functional_lead_sees_people_in_their_function(demo, as_user):
    c = as_user("vikram")  # heads Quality unit, leads QA function
    people = names(c.get("/api/v1/people?per_page=100"))
    assert "Rohan Das" in people  # QA engineer sitting in the Platform team (another unit)
    assert "Arjun Nair" not in people


def test_include_descendants_filter(demo, admin_client):
    data = admin_client.get(f"/api/v1/people?unit_id={unit_id('ENG')}&include_descendants=1&per_page=100").get_json()
    assert {"Arjun Nair", "Isha Gupta", "Meera Iyer"} <= names_of(data)


def names_of(data):
    return {p["full_name"] for p in data["items"]}


def test_me_returns_permissions_and_scope(demo, as_user):
    me = as_user("meera").get("/api/v1/auth/me").get_json()["user"]
    assert me["scope"] == "unit" and "org.manage" in me["permissions"]
    assert "roles.manage" not in me["permissions"]


def test_member_counts_match_visible_people(demo, as_user):
    c = as_user("arjun")
    plat = c.get(f"/api/v1/units/{unit_id('PLAT')}").get_json()
    listed = c.get(f"/api/v1/people?unit_id={unit_id('PLAT')}").get_json()["total"]
    assert plat["member_count"] == listed == 1
