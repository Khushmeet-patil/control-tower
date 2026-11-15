"""Phase 2: lookups, custom fields, terminology and settings versions."""
import pytest

from app.core.audit import AuditEvent
from app.core.errors import ValidationFailed
from app.extensions import db
from app.modules.config.service import FieldService, SettingsService
from app.modules.lookups.models import LookupType, LookupValue
from app.modules.lookups.service import LookupTypeService, LookupValueService
from app.modules.people.service import PersonService
from seed.cli import AMBER
from tests.conftest import person


def lookup(type_code):
    return db.session.scalar(db.select(LookupType).where(LookupType.code == type_code))


def value(type_code, code):
    return db.session.scalar(db.select(LookupValue).join(LookupType, LookupType.id == LookupValue.lookup_type_id)
                             .where(LookupType.code == type_code, LookupValue.code == code))


def make_list(admin, code="business_impact", name="Business Impact", values=(("low", "Low", "#94A3B8"),
                                                                            ("high", "High", "#B42318"))):
    t = LookupTypeService(admin).create({"code": code, "name": name})
    for v_code, label, color in values:
        LookupValueService(admin).create({"lookup_type_id": t.id, "code": v_code, "label": label, "color": color})
    return t


def make_field(admin, code, field_type, lookup_type_id=None, **extra):
    return FieldService(admin).create({"entity_type": "person", "code": code, "label": code.title(),
                                       "field_type": field_type, "lookup_type_id": lookup_type_id, **extra})


# ---------------------------------------------------------------------- the "Done when" scenario
def test_admin_adds_business_impact_field_without_code_change(demo, admin_client, as_user):
    c = admin_client
    t = c.post("/api/v1/lookup-types", json={"code": "business_impact", "name": "Business Impact"}).get_json()
    high = c.post("/api/v1/lookup-values", json={"lookup_type_id": t["id"], "code": "high", "label": "High",
                                                 "color": "#b42318"}).get_json()
    c.post("/api/v1/lookup-values", json={"lookup_type_id": t["id"], "code": "low", "label": "Low", "color": "#94A3B8"})
    resp = c.post("/api/v1/field-definitions", json={
        "entity_type": "person", "code": "business_impact", "label": "Business Impact", "field_type": "select",
        "lookup_type_id": t["id"], "show_in_list": True, "is_filterable": True})
    assert resp.status_code == 201, resp.get_json()

    # Draft only: nothing changes for users until it is published.
    assert c.get("/api/v1/settings").get_json()["fields"]["person"] == []
    status = c.get("/api/v1/settings/status").get_json()
    assert status["has_changes"] and {ch["change"] for ch in status["changes"]} == {"added"}

    assert c.post("/api/v1/settings/publish", json={"note": "Business impact"}).status_code == 201
    settings = c.get("/api/v1/settings").get_json()
    field = settings["fields"]["person"][0]
    assert field["code"] == "business_impact" and field["lookup"] == "business_impact"
    assert {v["label"]: v["color"] for v in settings["lookups"]["business_impact"]["values"]}["High"] == "#B42318"

    # The form saves it, the API returns it, the list filters on it.
    arjun = person("arjun")
    resp = c.patch(f"/api/v1/people/{arjun.id}", json={"custom_fields": {"business_impact": high["id"]},
                                                       "reason": "Key person"})
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["custom_fields"] == {"business_impact": high["id"]}
    listed = c.get("/api/v1/people", query_string={"cf.business_impact": high["id"]}).get_json()
    assert [p["full_name"] for p in listed["items"]] == ["Arjun Nair"]

    audit = db.session.scalar(db.select(AuditEvent).where(AuditEvent.field == "custom_fields.business_impact"))
    assert audit.new_value == str(high["id"]) and audit.reason == "Key person"


# ---------------------------------------------------------------------- lookups
def test_retired_value_stays_on_old_records_but_cannot_be_newly_chosen(demo, admin):
    t = make_list(admin)
    make_field(admin, "business_impact", "select", t.id)
    SettingsService(admin).publish()
    high = value("business_impact", "high")
    svc = PersonService(admin)
    svc.update(person("arjun").id, {"custom_fields": {"business_impact": high.id}})

    LookupValueService(admin).update(high.id, {"is_active": False}, reason="No longer used")
    SettingsService(admin).publish()
    from app.modules.config.versioning import settings_payload
    retired = [v for v in settings_payload(admin.tenant_id)["lookups"]["business_impact"]["values"] if v["code"] == "high"]
    assert retired and retired[0]["is_active"] is False  # still listed, so old records show its label and colour

    svc.update(person("arjun").id, {"job_title": "Senior Backend Developer",
                                    "custom_fields": {"business_impact": high.id}})  # unchanged: allowed
    with pytest.raises(ValidationFailed):
        svc.update(person("divya").id, {"custom_fields": {"business_impact": high.id}})


def test_built_in_lists_and_values_are_protected(admin):
    with pytest.raises(ValidationFailed):
        LookupTypeService(admin).update(lookup("health").id, {"is_active": False})
    with pytest.raises(ValidationFailed):
        LookupValueService(admin).update(value("health", "red").id, {"is_active": False})
    with pytest.raises(ValidationFailed):
        LookupValueService(admin).update(value("priority", "high").id, {"code": "urgent"})
    LookupValueService(admin).update(value("health", "red").id, {"label": "At risk", "color": "#a01010"})
    assert value("health", "red").color == "#A01010"


def test_only_one_default_value_per_list(admin):
    LookupValueService(admin).update(value("priority", "high").id, {"is_default": True})
    assert value("priority", "high").is_default and not value("priority", "medium").is_default


def test_rename_item_type_initiative(admin_client):
    """Admins rename terms: 'Programme' becomes 'Initiative' everywhere once published."""
    prog = value("item_type", "programme")
    admin_client.patch(f"/api/v1/lookup-values/{prog.id}", json={"label": "Initiative", "version": prog.version})
    t = admin_client.get("/api/v1/terms").get_json()["items"]
    person_term = next(x for x in t if x["key"] == "person")
    admin_client.patch(f"/api/v1/terms/{person_term['id']}", json={"singular": "Colleague", "plural": "Colleagues"})
    admin_client.post("/api/v1/settings/publish", json={})
    s = admin_client.get("/api/v1/settings").get_json()
    assert [v["label"] for v in s["lookups"]["item_type"]["values"]][0] == "Initiative"
    assert s["terms"]["person"] == {"singular": "Colleague", "plural": "Colleagues"}


# ---------------------------------------------------------------------- versions
def test_publish_rollback_and_discard(admin):
    settings = SettingsService(admin)
    v1 = settings.status()["current"]
    high = value("priority", "high")
    LookupValueService(admin).update(high.id, {"label": "Urgent"})
    v2 = settings.publish("Rename high")
    assert v2.number == v1["number"] + 1

    rolled = settings.rollback(v1["id"], reason="Users preferred High")
    assert rolled.number == v2.number + 1 and rolled.restored_from_id == v1["id"]
    assert value("priority", "high").label == "High"
    assert not settings.status()["has_changes"]

    LookupValueService(admin).update(high.id, {"color": "#000000"})
    make_list(admin, "risk", "Risk")
    assert settings.status()["has_changes"]
    settings.discard()
    assert value("priority", "high").color == AMBER  # seeded colour restored
    assert lookup("risk").is_active is False  # created after the live version: retired, not deleted
    assert not settings.status()["has_changes"]


def test_publish_with_nothing_to_publish_fails_without_audit(admin):
    before = db.session.scalar(db.select(db.func.count()).select_from(AuditEvent))
    with pytest.raises(ValidationFailed):
        SettingsService(admin).publish()
    assert db.session.scalar(db.select(db.func.count()).select_from(AuditEvent)) == before


def test_versions_api_lists_history(admin_client):
    data = admin_client.get("/api/v1/settings/versions").get_json()
    assert data["total"] == 1 and data["items"][0]["is_current"]


# ---------------------------------------------------------------------- custom field values
def test_custom_field_value_validation(demo, admin):
    for code, kind in [("budget", "number"), ("start", "date"), ("site", "url"), ("buddy", "person"),
                       ("notes", "text")]:
        make_field(admin, code, kind)
    SettingsService(admin).publish()
    svc, pid = PersonService(admin), person("arjun").id
    for bad in [{"budget": "lots"}, {"start": "31/12/2026"}, {"site": "example.com"}, {"buddy": 999999},
                {"nope": 1}]:
        with pytest.raises(ValidationFailed):
            svc.update(pid, {"custom_fields": bad})
    svc.update(pid, {"custom_fields": {"budget": 1500, "start": "2026-12-31", "site": "https://x.org",
                                       "buddy": person("divya").id, "notes": "  hi  "}})
    p = person("arjun")
    assert p.custom_fields == {"budget": 1500, "start": "2026-12-31", "site": "https://x.org",
                               "buddy": person("divya").id, "notes": "hi"}
    assert svc.serialize(p)["custom_people"]["buddy"]["full_name"] == "Divya Patel"
    svc.update(pid, {"custom_fields": {"notes": None}})  # clearing removes only that key
    assert "notes" not in person("arjun").custom_fields and person("arjun").custom_fields["budget"] == 1500


def test_required_field_enforced_on_create(demo, admin):
    make_field(admin, "cost_centre", "text", is_required=True)
    SettingsService(admin).publish()
    data = {"email": "n@demo.local", "full_name": "N", "password": "Password123!"}
    with pytest.raises(ValidationFailed):
        PersonService(admin).create(dict(data))
    p = PersonService(admin).create({**data, "custom_fields": {"cost_centre": "CC-1"}})
    assert p.custom_fields == {"cost_centre": "CC-1"}


def test_field_type_and_list_cannot_change(admin):
    t = make_list(admin)
    f = make_field(admin, "impact", "select", t.id)
    with pytest.raises(ValidationFailed):
        FieldService(admin).update(f.id, {"field_type": "text"})
    with pytest.raises(ValidationFailed):
        make_field(admin, "orphan", "select")  # select needs a list


def test_filters_on_multi_select_number_and_text(demo, admin_client, admin):
    t = make_list(admin, "skills", "Skills", (("py", "Python", "#2F5D8A"), ("js", "JavaScript", "#3E8E7E")))
    make_field(admin, "skills", "multi_select", t.id)
    make_field(admin, "budget", "number")
    make_field(admin, "vendor", "text")
    SettingsService(admin).publish()
    py, js = value("skills", "py").id, value("skills", "js").id
    svc = PersonService(admin)
    svc.update(person("arjun").id, {"custom_fields": {"skills": [py, js], "budget": 50, "vendor": "Acme Ltd"}})
    svc.update(person("divya").id, {"custom_fields": {"skills": [js], "budget": 500}})

    def names(**params):
        resp = admin_client.get("/api/v1/people", query_string=params)
        assert resp.status_code == 200, resp.get_json()
        return sorted(p["full_name"] for p in resp.get_json()["items"])

    assert names(**{"cf.skills": py}) == ["Arjun Nair"]
    assert names(**{"cf.skills__in": f"{py},{js}"}) == ["Arjun Nair", "Divya Patel"]
    assert names(**{"cf.budget__gte": "100"}) == ["Divya Patel"]
    assert names(**{"cf.vendor__contains": "acme"}) == ["Arjun Nair"]
    assert admin_client.get("/api/v1/people", query_string={"cf.unknown": 1}).status_code == 422


# ---------------------------------------------------------------------- access
def test_only_settings_managers_edit_the_draft(demo, as_user):
    c = as_user("arjun")
    assert c.get("/api/v1/settings").status_code == 200  # everyone reads published settings
    for path in ("/api/v1/lookup-types", "/api/v1/field-definitions", "/api/v1/terms", "/api/v1/settings/status"):
        assert c.get(path).status_code == 403
    assert c.post("/api/v1/settings/publish", json={}).status_code == 403
    assert c.post("/api/v1/lookup-values", json={"lookup_type_id": 1, "code": "x", "label": "X",
                                                "color": "#000000"}).status_code == 403


def test_settings_writes_are_audited(admin):
    t = make_list(admin, "risk", "Risk", ())
    assert db.session.scalar(db.select(AuditEvent).where(AuditEvent.entity_type == "lookup_type",
                                                         AuditEvent.entity_id == t.id))
    SettingsService(admin).publish("Risk list")
    assert db.session.scalar(db.select(AuditEvent).where(AuditEvent.entity_type == "config_version",
                                                         AuditEvent.operation == "publish",
                                                         AuditEvent.reason == "Risk list"))
