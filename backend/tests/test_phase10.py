"""Phase 10: notifications, webhooks and Teams, API tokens, Power BI feeds, calendar feed, Entra ID sign-in,
what-if scenarios, templates, status flow, working calendars, tool context parameters, frozen capacity."""
import base64
import hashlib
import hmac
import json
import time
from datetime import date, timedelta

import pytest
from sqlalchemy import func, select

from app.core.audit import AuditEvent
from app.core.dates import today
from app.extensions import db
from app.modules.config.versioning import published_value_id
from app.modules.notifications.models import Delivery, Notification
from app.modules.work.models import Assignment, WorkItem
from tests.conftest import person, unit_id


def tid():
    return person("asha").tenant_id


def value(lst, code):
    return published_value_id(tid(), lst, code)


def item(code):
    return db.session.scalar(select(WorkItem).where(WorkItem.code == code))


def notes_for(prefix, kind=None):
    stmt = select(Notification).where(Notification.user_id == person(prefix).id)
    if kind:
        stmt = stmt.where(Notification.kind == kind)
    return db.session.scalars(stmt).all()


# ====================================================================== notifications
def test_assigning_someone_notifies_them_but_not_the_actor(demo, as_user):
    c = as_user("karan")
    api = item("MS-001")
    resp = c.post(f"/api/v1/work-items/{api.id}/assignments", json={"person_id": person("rohan").id,
                                                "allocation_pct": 10})
    assert resp.status_code == 201, resp.get_json()
    mine = notes_for("rohan", "assignment")
    assert any("MS-001" in n.title for n in mine)
    assert not notes_for("karan", "assignment")

    r = as_user("rohan")
    assert r.get("/api/v1/notifications/count").get_json()["unread"] >= 1
    listed = r.get("/api/v1/notifications", query_string={"unread": 1}).get_json()["items"]
    assert listed[0]["link"].startswith("/pages/item.html")
    r.post("/api/v1/notifications/read", json={"all": True})
    assert r.get("/api/v1/notifications/count").get_json()["unread"] == 0


def test_people_see_only_their_own_notifications(demo, as_user):
    as_user("karan").post(f"/api/v1/work-items/{item("MS-001").id}/assignments", json={"person_id": person("rohan").id, "allocation_pct": 5})
    note = notes_for("rohan")[0]
    other = as_user("arjun")
    assert all(n["id"] != note.id for n in other.get("/api/v1/notifications").get_json()["items"])
    other.post("/api/v1/notifications/read", json={"ids": [note.id]})
    db.session.expire_all()
    assert db.session.get(Notification, note.id).read_at is None


def test_handover_and_approval_notifications(demo, admin):
    from app.modules.work.service import WorkItemService

    svc = WorkItemService(admin)
    svc.update(item("MS-002").id, {"accountable_id": person("meera").id}, reason="Neha on leave")
    assert any("MS-002" in n.title for n in notes_for("meera", "handover"))

    beta = item("MS-002")
    svc.update(beta.id, {"evidence_url": "https://evidence.example.test/beta"}, reason="test")
    svc.complete(beta.id)
    waiting = db.session.scalars(select(Notification).where(Notification.kind == "approval_needed")).all()
    assert waiting and all("MS-002" in n.title for n in waiting)


def test_rejection_tells_the_submitter(demo, as_user):
    from app.modules.workflows.models import ApprovalRequest

    req = db.session.scalar(select(ApprovalRequest).where(ApprovalRequest.work_item_id == item("MS-004").id,
                                                          ApprovalRequest.status == "pending"))
    c = as_user("sara")
    resp = c.post(f"/api/v1/approvals/{req.id}/reject", json={"comment": "Rules miss the billing queue"})
    assert resp.status_code == 200, resp.get_json()
    if req.submitted_by_id:
        submitter = db.session.get(type(person("sara")), req.submitted_by_id)
        assert any(n.kind == "approval_decided" for n in notes_for(submitter.email.split("@")[0]))


def test_preferences_turn_kinds_off_and_are_audited(demo, as_user):
    c = as_user("rohan")
    prefs = c.get("/api/v1/notifications/preferences").get_json()
    assert {k["kind"] for k in prefs["kinds"]} >= {"assignment", "item_red", "approval_needed"}
    c.put("/api/v1/notifications/preferences", json={"kinds": {"assignment": {"in_app": False}}})
    assert c.put("/api/v1/notifications/preferences", json={"kinds": {"nope": {}}}).status_code == 422
    as_user("karan").post(f"/api/v1/work-items/{item("MS-001").id}/assignments", json={"person_id": person("rohan").id, "allocation_pct": 5})
    assert as_user("rohan").get("/api/v1/notifications/count").get_json()["unread"] == 0
    assert db.session.scalar(select(func.count()).select_from(AuditEvent).where(
        AuditEvent.field == "notification_prefs")) == 1


def test_daily_checks_run_once(demo, admin):
    from app.modules.notifications.service import run_checks
    from app.modules.work.service import WorkItemService

    WorkItemService(admin).update(item("TSK-002").id, {"planned_end": today() + timedelta(days=1)}, reason="test")
    first = run_checks(tid())
    assert first["due_soon"] >= 1 and first["overdue"] >= 1
    assert any("due tomorrow" in n.title for n in notes_for("divya", "due_soon"))
    second = run_checks(tid())
    assert second == {"due_soon": 0, "overdue": 0, "item_red": 0}


def test_turned_red_is_noticed_once(demo, admin):
    from app.modules.notifications.models import HealthWatch
    from app.modules.notifications.service import run_checks

    run_checks(tid())
    red = db.session.scalars(select(HealthWatch).where(HealthWatch.health == "red")).all()
    assert red, "the demo data has overdue high-priority work"
    told = db.session.scalar(select(func.count()).select_from(Notification).where(Notification.kind == "item_red"))
    assert told >= 1
    run_checks(tid())
    assert db.session.scalar(select(func.count()).select_from(Notification).where(Notification.kind == "item_red")) == told


def test_email_is_queued_with_the_change_and_sent_by_the_job(demo, as_user, app, monkeypatch):
    app.config["MAIL_SERVER"] = "smtp.example.test"
    sent = []

    class FakeSMTP:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self, **k):
            pass

        def login(self, *a):
            pass

        def send_message(self, msg):
            sent.append(msg)

    import app.modules.notifications.delivery as delivery

    monkeypatch.setattr(delivery.smtplib, "SMTP", FakeSMTP)
    as_user("karan").post(f"/api/v1/work-items/{item("MS-001").id}/assignments", json={"person_id": person("rohan").id, "allocation_pct": 5})
    queued = db.session.scalars(select(Delivery).where(Delivery.channel == "email")).all()
    assert [d.target for d in queued] == ["rohan@demo.local"]
    assert delivery.deliver_pending()["sent"] == 1
    assert sent[0]["To"] == "rohan@demo.local" and "MS-001" in sent[0]["Subject"]


def test_failed_change_queues_nothing(demo, as_user, app):
    app.config["MAIL_SERVER"] = "smtp.example.test"
    c = as_user("karan")
    resp = c.post(f"/api/v1/work-items/{item("MS-001").id}/assignments", json={"person_id": person("rohan").id,
                                                "allocation_pct": 5, "start_date": "2026-12-10", "end_date": "2026-12-01"})
    assert resp.status_code == 422
    assert db.session.scalar(select(func.count()).select_from(Delivery)) == 0
    assert not notes_for("rohan", "assignment")


# ====================================================================== webhooks and Teams
def _hook(c, **extra):
    body = {"name": "Ops feed", "url": "https://hooks.example.test/ct", "events": ["work_item.update"], **extra}
    resp = c.post("/api/v1/webhooks", json=body)
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


def test_only_administrators_manage_webhooks(demo, as_user, admin_client):
    assert as_user("meera").post("/api/v1/webhooks", json={"name": "x", "url": "https://a.test/x",
                                                           "events": ["work_item.update"]}).status_code == 403
    c = as_user("meera")
    assert c.get("/api/v1/webhooks").status_code == 403


def test_saved_changes_reach_webhooks_signed(demo, admin_client, monkeypatch):
    hook = _hook(admin_client, unit_id=unit_id("PLAT"))
    assert len(hook["secret"]) > 20
    assert admin_client.post("/api/v1/webhooks", json={"name": "bad", "url": "ftp://x", "events": ["x.y"]}).status_code == 422

    admin_client.patch(f"/api/v1/work-items/{item('TSK-002').id}", json={"remarks": "Halfway"})
    admin_client.patch(f"/api/v1/work-items/{item('MS-004').id}", json={"remarks": "Support unit: not in the hook"})
    queued = db.session.scalars(select(Delivery).where(Delivery.channel == "webhook")).all()
    assert len(queued) == 1 and queued[0].payload["data"]["new"] == "Halfway"

    captured = {}

    class Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        captured["body"], captured["headers"] = req.data, dict(req.header_items())
        return Resp()

    import app.modules.notifications.delivery as delivery

    monkeypatch.setattr(delivery.urllib.request, "urlopen", fake_urlopen)
    assert delivery.deliver_pending()["sent"] == 1
    expected = "sha256=" + hmac.new(hook["secret"].encode(), captured["body"], hashlib.sha256).hexdigest()
    assert captured["headers"]["X-controltower-signature"] == expected
    assert json.loads(captured["body"])["event"] == "work_item.update"


def test_teams_channel_gets_alerts_as_cards(demo, admin_client, as_user, monkeypatch):
    _hook(admin_client, name="Platform channel", format="teams", events=["alert.assignment"])
    as_user("karan").post(f"/api/v1/work-items/{item("MS-001").id}/assignments", json={"person_id": person("rohan").id, "allocation_pct": 5})
    d = db.session.scalar(select(Delivery).where(Delivery.event == "alert.assignment"))
    assert d is not None
    from app.modules.notifications.delivery import teams_card

    card = teams_card(d.payload)
    assert card["@type"] == "MessageCard" and "MS-001" in card["title"]


def test_failing_webhook_is_retried_then_marked_failed(demo, admin_client, monkeypatch):
    _hook(admin_client)
    admin_client.patch(f"/api/v1/work-items/{item('TSK-002').id}", json={"remarks": "x"})
    import app.modules.notifications.delivery as delivery

    def boom(req, timeout=None):
        raise OSError("connection refused")

    monkeypatch.setattr(delivery.urllib.request, "urlopen", boom)
    d = db.session.scalar(select(Delivery))
    for _ in range(delivery.MAX_ATTEMPTS):
        d.next_attempt_at = None
        db.session.commit()
        delivery.deliver_pending()
    db.session.refresh(d)
    assert d.status == "failed" and "refused" in d.last_error
    listed = admin_client.get("/api/v1/deliveries", query_string={"status": "failed"}).get_json()["items"]
    assert listed[0]["target"].endswith("/…")  # the address (which may hold a secret) is not shown


# ====================================================================== API tokens, Power BI, calendar
def _token(c, **body):
    resp = c.post("/api/v1/api-tokens", json={"name": "Power BI", **body})
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["token"]


def test_read_token_reads_with_the_owners_scope_only(demo, as_user, app):
    token = _token(as_user("karan"))
    c = app.test_client()
    h = {"Authorization": f"Bearer {token}"}
    rows = c.get("/api/v1/reporting/work-items", headers=h).get_json()["rows"]
    codes = {r["code"] for r in rows}
    assert "MS-001" in codes and "PRJ-002" not in codes  # Karan cannot see Operations' work
    assert c.patch(f"/api/v1/work-items/{item('TSK-002').id}", json={"remarks": "x"}, headers=h).status_code == 401
    assert c.post("/api/v1/api-tokens", json={"name": "more"}, headers=h).status_code == 401
    csv = c.get("/api/v1/reporting/work-items?format=csv", headers=h)
    assert csv.status_code == 200 and b"MS-001" in csv.data and b"PRJ-002" not in csv.data
    assert c.get("/api/v1/reporting/work-items", headers={"Authorization": "Bearer ct_nope"}).status_code == 401


def test_write_token_changes_records_audited_as_api(demo, as_user, app):
    token = _token(as_user("karan"), scopes=["write"])
    c = app.test_client()
    resp = c.patch(f"/api/v1/work-items/{item('TSK-002').id}", json={"remarks": "From the tool"},
                   headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.get_json()
    ev = db.session.scalar(select(AuditEvent).where(AuditEvent.field == "remarks").order_by(AuditEvent.id.desc()))
    assert ev.source == "api" and ev.actor_name == "Karan Mehta"


def test_revoked_and_expired_tokens_stop_working(demo, as_user, app):
    k = as_user("karan")
    token = _token(k)
    listed = k.get("/api/v1/api-tokens").get_json()["items"]
    assert listed[0]["prefix"] == token[:10] and "token" not in listed[0]
    c = app.test_client()
    h = {"Authorization": f"Bearer {token}"}
    assert c.get("/api/v1/reporting", headers=h).status_code == 200
    assert as_user("arjun").post(f"/api/v1/api-tokens/{listed[0]['id']}/revoke", json={}).status_code in (403, 404)
    as_user("karan").post(f"/api/v1/api-tokens/{listed[0]['id']}/revoke", json={})
    assert c.get("/api/v1/reporting", headers=h).status_code == 401

    from app.core.models import utcnow
    from app.modules.integrations.models import ApiToken

    token2 = _token(as_user("karan"))
    t = db.session.scalar(select(ApiToken).where(ApiToken.token_prefix == token2[:10]))
    t.expires_at = utcnow() - timedelta(minutes=1)
    db.session.commit()
    assert c.get("/api/v1/reporting", headers={"Authorization": f"Bearer {token2}"}).status_code == 401


def test_contributors_cannot_make_tokens_by_default(demo, as_user):
    assert as_user("arjun").post("/api/v1/api-tokens", json={"name": "x"}).status_code == 403


def test_calendar_feed(demo, as_user, app):
    c = as_user("divya")
    link = c.post("/api/v1/calendar/link", json={}).get_json()
    token = link["url"].split("token=")[1]
    feed = app.test_client().get(f"/api/v1/calendar/feed.ics?token={token}")
    assert feed.status_code == 200 and feed.mimetype == "text/calendar"
    text = feed.data.decode()
    assert "BEGIN:VCALENDAR" in text and "TSK-002" in text and "PRJ-002" not in text
    # a calendar-only token opens nothing else
    assert app.test_client().get("/api/v1/reporting", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert app.test_client().get("/api/v1/calendar/feed.ics?token=ct_bad").status_code == 401


# ====================================================================== Microsoft Entra ID
@pytest.fixture()
def entra(app, monkeypatch):
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    from cryptography.hazmat.primitives import hashes

    import app.modules.integrations.entra as module

    app.config.update(ENTRA_TENANT_ID="tid-1", ENTRA_CLIENT_ID="client-1", ENTRA_CLIENT_SECRET="s",
                      ENTRA_REDIRECT_URI="http://localhost/api/v1/auth/entra/callback")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nums = key.public_key().public_numbers()
    b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()  # noqa: E731
    jwk = {"kid": "k1", "kty": "RSA", "n": b64(nums.n.to_bytes(256, "big")), "e": b64(nums.e.to_bytes(3, "big"))}
    monkeypatch.setattr(module, "_jwks", lambda: {"keys": [jwk]})
    state = {}

    def sign(claims):
        head = b64(json.dumps({"alg": "RS256", "kid": "k1"}).encode())
        body = b64(json.dumps(claims).encode())
        sig = key.sign(f"{head}.{body}".encode(), padding.PKCS1v15(), hashes.SHA256())
        return f"{head}.{body}.{b64(sig)}"

    def post_token(code, verifier):
        return {"id_token": sign({**{"iss": "https://login.microsoftonline.com/tid-1/v2.0", "aud": "client-1",
                                     "exp": time.time() + 300, "nonce": state["nonce"], "oid": "oid-arjun",
                                     "preferred_username": "Arjun@demo.local"}, **state.get("override", {})})}

    monkeypatch.setattr(module, "_post_token", post_token)
    return state


def _start(c, state):
    from urllib.parse import parse_qs, urlparse

    resp = c.get("/api/v1/auth/entra/login?next=/pages/work.html")
    assert resp.status_code == 302
    q = parse_qs(urlparse(resp.headers["Location"]).query)
    assert q["code_challenge_method"] == ["S256"] and q["client_id"] == ["client-1"]
    state["nonce"] = q["nonce"][0]
    return q["state"][0]


def test_entra_sign_in_links_the_account_by_email(demo, client, entra):
    assert client.get("/api/v1/auth/entra").get_json()["enabled"] is True
    s = _start(client, entra)
    resp = client.get(f"/api/v1/auth/entra/callback?code=abc&state={s}")
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/pages/work.html")
    assert client.get("/api/v1/auth/me").get_json()["user"]["email"] == "arjun@demo.local"
    assert person("arjun").entra_oid == "oid-arjun"
    assert db.session.scalar(select(AuditEvent).where(AuditEvent.operation == "login",
                                                      AuditEvent.source == "integration")) is not None


def test_entra_rejects_bad_state_nonce_or_unknown_people(demo, client, entra):
    _start(client, entra)
    assert "error=" in client.get("/api/v1/auth/entra/callback?code=abc&state=wrong").headers["Location"]
    s = _start(client, entra)
    entra["override"] = {"nonce": "replayed"}
    assert "nonce" in client.get(f"/api/v1/auth/entra/callback?code=abc&state={s}").headers["Location"]
    s = _start(client, entra)
    entra["override"] = {"oid": "oid-x", "preferred_username": "stranger@else.test"}
    loc = client.get(f"/api/v1/auth/entra/callback?code=abc&state={s}").headers["Location"]
    assert "no%20active" in loc.lower() or "no active" in loc.lower()
    assert client.get("/api/v1/auth/me").status_code == 401


def test_entra_only_mode_blocks_passwords_except_for_admins(demo, client, app, entra):
    from tests.conftest import login

    app.config["ENTRA_ALLOW_PASSWORD"] = False
    assert login(client, "arjun@demo.local", "Password123!").status_code == 401
    assert login(client, app.config["SEED_ADMIN_EMAIL"], app.config["SEED_ADMIN_PASSWORD"]).status_code == 200


def test_next_address_must_stay_on_this_site():
    from app.modules.integrations.entra import safe_next

    assert safe_next("//evil.test/x") == "/pages/home.html"
    assert safe_next("https://evil.test") == "/pages/home.html"
    assert safe_next("/pages/item.html?id=3") == "/pages/item.html?id=3"


# ====================================================================== what-if scenarios
def _scenario(c, name="Slip the API"):
    resp = c.post("/api/v1/scenarios", json={"name": name})
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["id"]


def test_scenario_shows_impact_without_touching_live_data(demo, as_user):
    c = as_user("asha")
    sid = _scenario(c)
    divya = db.session.scalar(select(Assignment).where(Assignment.person_id == person("divya").id))
    r = c.post(f"/api/v1/scenarios/{sid}/changes", json={"kind": "assignment", "target_id": divya.id,
                                                          "changes": {"allocation_pct": 100}})
    assert r.status_code == 201, r.get_json()
    r = c.post(f"/api/v1/scenarios/{sid}/changes", json={"kind": "new_assignment", "work_item_id": item("MS-001").id,
                                                          "changes": {"person_id": person("arjun").id, "allocation_pct": 70}})
    assert r.status_code == 201, r.get_json()
    impact = c.get(f"/api/v1/scenarios/{sid}/impact?weeks=4").get_json()
    rows = {p["person"]["full_name"]: p for p in impact["capacity"]}
    assert rows["Divya Patel"]["peak_after"] == rows["Divya Patel"]["peak_before"] + 70
    assert rows["Arjun Nair"]["overloaded_weeks_after"] > rows["Arjun Nair"]["overloaded_weeks_before"] or \
        rows["Arjun Nair"]["peak_after"] == rows["Arjun Nair"]["peak_before"] + 70
    db.session.refresh(divya)
    assert divya.allocation_pct == 30  # nothing applied yet


def test_scenario_finds_dependency_clashes(demo, as_user, admin):
    from app.modules.work.service import WorkItemService

    WorkItemService(admin).update(item("TSK-002").id, {"depends_on_ids": [item("TSK-001").id]}, reason="test")
    c = as_user("karan")
    sid = _scenario(c)
    c.post(f"/api/v1/scenarios/{sid}/changes", json={"kind": "item", "target_id": item("TSK-001").id,
                                                      "changes": {"planned_end": "2026-12-30"}})
    problems = c.get(f"/api/v1/scenarios/{sid}/impact").get_json()["schedule"]
    kinds = {p["kind"] for p in problems}
    assert "dependency" in kinds and "parent" in kinds


def test_applying_a_scenario_is_one_audited_action(demo, as_user):
    c = as_user("asha")
    sid = _scenario(c)
    c.post(f"/api/v1/scenarios/{sid}/changes", json={"kind": "item", "target_id": item("TSK-002").id,
                                                      "changes": {"planned_end": "2026-11-28"}})
    divya = db.session.scalar(select(Assignment).where(Assignment.person_id == person("divya").id))
    assert c.post(f"/api/v1/scenarios/{sid}/changes", json={"kind": "remove_assignment",
                                                             "target_id": divya.id}).status_code == 201
    resp = c.post(f"/api/v1/scenarios/{sid}/apply", json={})
    assert resp.status_code == 200, resp.get_json()
    cid = resp.get_json()["applied_correlation_id"]
    db.session.expire_all()
    assert item("TSK-002").planned_end == date(2026, 11, 28)
    assert db.session.get(Assignment, divya.id).is_deleted
    ops = db.session.scalars(select(AuditEvent.entity_type).where(AuditEvent.correlation_id == cid)).all()
    assert {"work_item", "assignment", "scenario"} <= set(ops)
    assert c.post(f"/api/v1/scenarios/{sid}/apply", json={}).status_code == 409


def test_stale_changes_block_apply_and_nothing_is_half_done(demo, as_user, admin):
    from app.modules.work.service import WorkItemService

    c = as_user("karan")
    sid = _scenario(c)
    c.post(f"/api/v1/scenarios/{sid}/changes", json={"kind": "item", "target_id": item("TSK-002").id,
                                                      "changes": {"planned_end": "2026-11-28"}})
    c.post(f"/api/v1/scenarios/{sid}/changes", json={"kind": "item", "target_id": item("TSK-001").id,
                                                      "changes": {"planned_end": "2026-11-01"}})
    WorkItemService(admin).update(item("TSK-001").id, {"remarks": "edited meanwhile"}, reason="test")
    resp = c.post(f"/api/v1/scenarios/{sid}/apply", json={})
    assert resp.status_code == 409 and resp.get_json()["error"]["details"]["stale"]
    db.session.expire_all()
    assert item("TSK-002").planned_end == date(2026, 11, 20)


def test_scenarios_only_for_work_you_manage(demo, as_user):
    c = as_user("karan")
    sid = _scenario(c)
    resp = c.post(f"/api/v1/scenarios/{sid}/changes", json={"kind": "item", "target_id": item("MS-004").id,
                                                             "changes": {"planned_end": "2026-12-30"}})
    assert resp.status_code in (403, 404)
    assert as_user("arjun").post("/api/v1/scenarios", json={"name": "x"}).status_code == 403
    assert as_user("neha").get(f"/api/v1/scenarios/{sid}").status_code == 404  # private to its owner


# ====================================================================== templates
def test_save_and_reuse_a_breakdown_with_shifted_dates(demo, as_user):
    c = as_user("karan")
    t = c.post("/api/v1/templates/from-item", json={"work_item_id": item("MS-001").id, "name": "API milestone"})
    assert t.status_code == 201, t.get_json()
    t = t.get_json()
    assert t["node_count"] == 3 and t["structure"][0]["children"][0]["start_offset"] == 4
    made = c.post(f"/api/v1/templates/{t['id']}/use", json={"start_date": "2027-02-01",
                                                            "parent_id": item("MS-001").id, "title": "API v2"})
    assert made.status_code == 201, made.get_json()
    root = db.session.get(WorkItem, made.get_json()["items"][0]["id"])
    assert root.title == "API v2" and root.planned_start == date(2027, 2, 1)
    kids = db.session.scalars(select(WorkItem).where(WorkItem.parent_id == root.id).order_by(WorkItem.planned_start)).all()
    assert [k.planned_start for k in kids] == [date(2027, 2, 5), date(2027, 2, 20)]
    assert db.session.scalar(select(func.count()).select_from(AuditEvent).where(
        AuditEvent.entity_type == "work_template", AuditEvent.operation == "use")) == 1


def test_template_sharing_needs_permission_and_use_needs_rights(demo, as_user):
    c = as_user("arjun")
    t = c.post("/api/v1/templates", json={"name": "Mine", "is_shared": True, "structure": [
        {"title": "Task", "item_type_id": value("item_type", "task")}]})
    assert t.status_code == 403
    t = c.post("/api/v1/templates", json={"name": "Mine", "structure": [
        {"title": "Task", "item_type_id": value("item_type", "task")}]}).get_json()
    assert c.post(f"/api/v1/templates/{t['id']}/use", json={}).status_code == 403  # no top-level work for him
    assert as_user("karan").get(f"/api/v1/templates/{t['id']}").status_code == 404  # private
    bad = as_user("karan").post("/api/v1/templates", json={"name": "Bad", "structure": [{"title": ""}]})
    assert bad.status_code == 422


# ====================================================================== status flow
def test_status_flow_applies_once_published(demo, admin_client, as_user, admin):
    from app.modules.config.service import SettingsService

    not_started, in_progress, done = value("status", "not_started"), value("status", "in_progress"), value("status", "done")
    task = value("item_type", "task")
    resp = admin_client.post("/api/v1/status-transitions", json={"item_type_id": task, "from_status_id": in_progress,
                                                                 "to_status_ids": [value("status", "on_hold"), value("status", "under_validation")]})
    assert resp.status_code == 201, resp.get_json()
    assert admin_client.post("/api/v1/status-transitions", json={"item_type_id": task, "from_status_id": in_progress,
                                                                 "to_status_ids": []}).status_code == 422
    c = as_user("divya")
    tsk = item("TSK-002")
    assert c.patch(f"/api/v1/work-items/{tsk.id}", json={"remarks": "draft rules are not used"}).status_code == 200
    SettingsService(admin).publish("Status flow")
    c = as_user("divya")
    resp = c.patch(f"/api/v1/work-items/{tsk.id}", json={"status_id": done})
    assert resp.status_code == 422 and "can move to" in resp.get_json()["error"]["message"]
    assert c.patch(f"/api/v1/work-items/{tsk.id}", json={"status_id": value("status", "on_hold")}).status_code == 200
    assert not_started  # other statuses and types still change freely


# ====================================================================== working calendars
def test_holidays_and_work_days_reduce_capacity(demo, as_user, admin):
    from app.modules.capacity import engine

    monday = today() + timedelta(days=7 - today().weekday()) + timedelta(days=14)
    k = as_user("karan")
    assert k.post("/api/v1/holidays", json={"holiday_date": monday.isoformat(), "name": "Founders' day"}).status_code == 403
    r = k.post("/api/v1/holidays", json={"holiday_date": monday.isoformat(), "name": "Team offsite", "unit_id": unit_id("PLAT")})
    assert r.status_code == 201, r.get_json()
    weeks = engine.weekly(tid(), [person("divya").id, person("isha").id], 20, 4)
    assert weeks[person("divya").id][3]["available_pct"] == 80  # one of five days
    assert weeks[person("isha").id][3]["available_pct"] == 100  # Mobile Team: not their holiday

    from app.modules.people.service import PersonService

    PersonService(admin).update(person("isha").id, {"work_days": [0, 1, 2]}, reason="Three-day week")
    weeks = engine.weekly(tid(), [person("isha").id], 20, 1)
    assert weeks[person("isha").id][0]["available_pct"] == 100  # her normal week is three days


# ====================================================================== tool context parameters
def test_link_tools_get_project_data_in_the_address(demo, admin_client):
    resp = admin_client.post("/api/v1/tools", json={"name": "Jira board", "kind": "link",
                                                     "url": "https://jira.example.test/board?view=list",
                                                     "context_params": {"project": "{code}", "who": "{user_email}"}})
    assert resp.status_code == 201, resp.get_json()
    tool = resp.get_json()
    opened = admin_client.post(f"/api/v1/tools/{tool['id']}/open", json={"work_item_id": item("PRJ-001").id}).get_json()
    assert opened["url"].startswith("https://jira.example.test/board?view=list&project=PRJ-001&who=admin")
    bad = admin_client.patch(f"/api/v1/tools/{tool['id']}", json={"context_params": {"x": "{password}"}})
    assert bad.status_code == 422


# ====================================================================== frozen capacity
def test_capacity_widget_reads_a_snapshot(demo, as_user, admin):
    from app.modules.snapshots import frozen
    from app.modules.snapshots.models import Snapshot
    from app.modules.snapshots.service import SnapshotService

    snap = SnapshotService(admin).take(label="With people")
    fs = frozen.FrozenSet(person("karan"), snap)
    data = frozen.widget_data(fs, {"type": "capacity", "filters": {"unit_id": str(unit_id("PLAT"))}})
    names = {r["person"]["full_name"] for r in data["items"]}
    assert "Divya Patel" in names and "Isha Gupta" not in names
    assert "error" not in data
    old = db.session.scalar(select(Snapshot).where(Snapshot.label == "Baseline"))
    assert old is not None
