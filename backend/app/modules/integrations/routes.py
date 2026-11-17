from flask import Blueprint, Response, current_app, redirect, request
from flask_login import current_user, login_user
from pydantic import Field

from app.core.errors import AppError, Unauthorized
from app.core.permissions import require_permission
from app.core.schemas import InputSchema, parse_body
from app.modules.integrations import calendar, entra, reporting
from app.modules.integrations.models import TOKEN_SCOPES
from app.modules.integrations.service import ApiTokenService, WebhookService, deliveries, user_for_token

bp = Blueprint("integrations", __name__, url_prefix="/api/v1")


class TokenIn(InputSchema):
    name: str = Field(min_length=1, max_length=120)
    scopes: list[str] = ["read"]
    expires_in_days: int | None = 90
    reason: str | None = None


class _WebhookFields(InputSchema):
    format: str | None = None
    events: list[str] | None = None
    unit_id: int | None = None
    description: str | None = None
    is_active: bool | None = None
    reason: str | None = None


class WebhookIn(_WebhookFields):
    name: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=8, max_length=500)


class WebhookUpdateIn(_WebhookFields):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    url: str | None = Field(default=None, min_length=8, max_length=500)
    version: int | None = None


# ---------------------------------------------------------------------- API tokens
@bp.get("/api-tokens")
@require_permission()  # everyone sees (and may revoke) their own tokens, e.g. a calendar address
def list_tokens():
    return {**ApiTokenService(current_user).list(request.args), "scopes": TOKEN_SCOPES}


@bp.post("/api-tokens")
@require_permission("api.tokens")
def create_token():
    data, _, reason = parse_body(TokenIn, request.get_json())
    svc = ApiTokenService(current_user)
    token, raw = svc.create_token(data, reason=reason)
    return {**svc.serialize(token), "token": raw}, 201


@bp.post("/api-tokens/<int:token_id>/revoke")
@require_permission()
def revoke_token(token_id):
    svc = ApiTokenService(current_user)
    return svc.serialize(svc.revoke(token_id, reason=(request.get_json(silent=True) or {}).get("reason")))


# ---------------------------------------------------------------------- calendar feed
@bp.post("/calendar/link")
@require_permission("work.view")
def calendar_link():
    """Make a calendar-only token and return the address to subscribe to in Outlook."""
    svc = ApiTokenService(current_user)
    svc.permissions = {**svc.permissions, "create": "work.view"}  # anyone may subscribe to their own calendar
    token, raw = svc.create_token({"name": "Calendar feed", "scopes": ["calendar"], "expires_in_days": None},
                                  reason="Calendar feed link")
    base = (current_app.config.get("APP_BASE_URL") or request.host_url).rstrip("/")
    return {**svc.serialize(token), "url": f"{base}/api/v1/calendar/feed.ics?token={raw}"}, 201


@bp.get("/calendar/feed.ics")
def calendar_feed():
    user, _ = user_for_token(request.args.get("token", ""), scope="calendar")
    if user is None:
        user, _ = user_for_token(request.args.get("token", ""), scope="read")
    if user is None:
        raise Unauthorized("This calendar address is not valid any more. Make a new one in Control Tower.")
    return Response(calendar.feed(user), mimetype="text/calendar",
                    headers={"Content-Disposition": "inline; filename=control-tower.ics"})


# ---------------------------------------------------------------------- reporting (Power BI)
@bp.get("/reporting")
@require_permission("work.view")
def reporting_catalog():
    return reporting.catalog()


@bp.get("/reporting/<dataset>")
@require_permission("work.view")
def reporting_dataset(dataset):
    data = reporting.dataset(current_user, dataset)
    if request.args.get("format") == "csv":
        return Response(reporting.to_csv(data["rows"]), mimetype="text/csv",
                        headers={"Content-Disposition": f"attachment; filename={dataset}.csv"})
    return data


# ---------------------------------------------------------------------- webhooks
@bp.get("/webhooks")
@require_permission("integrations.manage")
def list_webhooks():
    return {**WebhookService(current_user).list(request.args), "catalog": WebhookService.event_catalog()}


@bp.post("/webhooks")
@require_permission("integrations.manage")
def create_webhook():
    data, _, reason = parse_body(WebhookIn, request.get_json())
    svc = WebhookService(current_user)
    return svc.serialize(svc.create({k: v for k, v in data.items() if v is not None}, reason=reason), secret=True), 201


@bp.patch("/webhooks/<int:webhook_id>")
@require_permission("integrations.manage")
def update_webhook(webhook_id):
    data, version, reason = parse_body(WebhookUpdateIn, request.get_json())
    svc = WebhookService(current_user)
    return svc.serialize(svc.update(webhook_id, data, expected_version=version, reason=reason))


@bp.delete("/webhooks/<int:webhook_id>")
@require_permission("integrations.manage")
def delete_webhook(webhook_id):
    WebhookService(current_user).delete(webhook_id, reason=(request.get_json(silent=True) or {}).get("reason"))
    return {"ok": True}


@bp.post("/webhooks/<int:webhook_id>/rotate-secret")
@require_permission("integrations.manage")
def rotate_secret(webhook_id):
    svc = WebhookService(current_user)
    return svc.serialize(svc.rotate_secret(webhook_id), secret=True)


@bp.post("/webhooks/<int:webhook_id>/test")
@require_permission("integrations.manage")
def test_webhook(webhook_id):
    return WebhookService(current_user).test(webhook_id)


@bp.get("/deliveries")
@require_permission("integrations.manage")
def list_deliveries():
    return deliveries(current_user, request.args)


@bp.post("/deliveries/<int:delivery_id>/retry")
@require_permission("integrations.manage")
def retry_delivery(delivery_id):
    from app.core.errors import NotFound
    from app.extensions import db
    from app.modules.notifications.delivery import retry, serialize
    from app.modules.notifications.models import Delivery

    d = db.session.get(Delivery, delivery_id)
    if d is None or d.tenant_id != current_user.tenant_id:
        raise NotFound("Delivery not found")
    return serialize(retry(delivery_id))


@bp.get("/integrations/status")
@require_permission("integrations.manage")
def integration_status():
    c = current_app.config
    return {"email": {"configured": bool(c.get("MAIL_SERVER")), "server": c.get("MAIL_SERVER"),
                      "from": c.get("MAIL_FROM")},
            "entra": {"configured": entra.enabled(), "tenant_id": c.get("ENTRA_TENANT_ID"),
                      "client_id": c.get("ENTRA_CLIENT_ID"), "redirect_uri": entra.redirect_uri() if entra.enabled() else None,
                      "password_sign_in": entra.password_allowed()},
            "base_url": c.get("APP_BASE_URL")}


# ---------------------------------------------------------------------- Microsoft Entra ID sign-in
@bp.get("/auth/entra")
def entra_config():
    return {"enabled": entra.enabled(), "password_sign_in": entra.password_allowed()}


@bp.get("/auth/entra/login")
def entra_login():
    if not entra.enabled():
        return redirect("/?error=entra_not_configured")
    return redirect(entra.authorize_url(request.args.get("next")))


@bp.get("/auth/entra/callback")
def entra_callback():
    from urllib.parse import quote

    if not entra.enabled():
        return redirect("/?error=entra_not_configured")
    try:
        user, next_path = entra.complete(request.args)
    except AppError as exc:
        return redirect(f"/?error={quote(exc.message)}")
    except Exception:  # noqa: BLE001 — Microsoft unreachable or an unexpected answer
        current_app.logger.exception("Microsoft Entra ID sign-in failed")
        return redirect(f"/?error={quote('Microsoft sign-in failed. Please try again.')}")
    login_user(user)
    return redirect(next_path)
