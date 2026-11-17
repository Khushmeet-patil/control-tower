"""API tokens and webhooks.

Tokens: anyone holding `api.tokens` makes tokens for themselves; `integrations.manage` (administrators)
sees and revokes everyone's. A token is "ct_" + 40 random characters; only its SHA-256 is stored, and
the plain token is returned once by create(). Resolving a token (`user_for_token`) checks it is not
revoked or expired, that its owner is still active, and records when it was last used.

Webhooks: `integrations.manage` only. The secret is generated, shown once, and can be rotated.
"""
import hashlib
import secrets
from datetime import timedelta
from urllib.parse import urlparse

from sqlalchemy import select

from app.core.command import CommandService
from app.core.errors import Forbidden, ValidationFailed
from app.core.models import utcnow
from app.core.pagination import paginate
from app.core.permissions import actor_can
from app.extensions import db
from app.modules.auth.models import User
from app.modules.integrations.events import WEBHOOK_ENTITIES, forget_webhooks, new_secret
from app.modules.integrations.models import TOKEN_SCOPES, WEBHOOK_FORMATS, ApiToken, Webhook
from app.modules.notifications.models import KINDS
from app.modules.organisation.models import OrgUnit

TOKEN_PREFIX = "ct_"
MAX_TOKEN_DAYS = 366
OPERATIONS = ("create", "update", "delete", "approve", "reject", "skip", "complete", "cancel", "decide", "apply")


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def user_for_token(raw: str, *, scope: str | None = None):
    """(user, token) for a valid token, else (None, None). `scope` must be one of the token's scopes."""
    if not raw or not raw.startswith(TOKEN_PREFIX) or len(raw) > 100:
        return None, None
    token = db.session.scalar(select(ApiToken).where(ApiToken.token_hash == hash_token(raw),
                                                     ApiToken.is_deleted.is_(False)))
    now = utcnow()
    if token is None or token.revoked_at is not None or (token.expires_at and token.expires_at <= now):
        return None, None
    if scope and scope not in token.scopes:
        return None, None
    user = db.session.get(User, token.user_id)
    if user is None or user.is_deleted or not user.is_active:
        return None, None
    if token.last_used_at is None or now - token.last_used_at > timedelta(minutes=5):
        token.last_used_at = now  # not audited: usage bookkeeping, at most every five minutes
        db.session.commit()
    return user, token


class ApiTokenService(CommandService):
    model = ApiToken
    entity_type = "api_token"
    permissions = {"create": "api.tokens", "update": "api.tokens", "delete": "api.tokens"}
    protected_fields = frozenset({"token_hash", "token_prefix", "last_used_at", "revoked_at", "user_id"})

    def _accepted_inputs(self):
        return {"expires_in_days"}

    def is_admin(self) -> bool:
        return actor_can(self.actor, "integrations.manage")

    def base_query(self):
        stmt = super().base_query()
        return stmt if self.is_admin() else stmt.where(ApiToken.user_id == self.actor.id)

    def list(self, params):
        stmt = self.base_query()
        if params.get("mine") in ("1", "true") or not self.is_admin():
            stmt = stmt.where(ApiToken.user_id == self.actor.id)
        return paginate(stmt.order_by(ApiToken.created_at.desc()), params, self.serialize)

    @staticmethod
    def serialize(t: ApiToken) -> dict:
        now = utcnow()
        state = "revoked" if t.revoked_at else "expired" if t.expires_at and t.expires_at <= now else "active"
        iso = lambda d: d.isoformat() if d else None  # noqa: E731
        return {"id": t.id, "name": t.name, "prefix": t.token_prefix, "scopes": t.scopes, "state": state,
                "owner": {"id": t.user.id, "full_name": t.user.full_name} if t.user else None,
                "created_at": iso(t.created_at), "expires_at": iso(t.expires_at), "last_used_at": iso(t.last_used_at),
                "revoked_at": iso(t.revoked_at)}

    def validate_create(self, data):
        scopes = sorted(set(data.get("scopes") or ["read"]))
        if bad := [s for s in scopes if s not in TOKEN_SCOPES]:
            raise ValidationFailed(f"Unknown scope: {', '.join(bad)}", {"field": "scopes"})
        if "write" in scopes and "read" not in scopes:
            scopes = sorted(scopes + ["read"])
        data["scopes"] = scopes
        days = data.pop("expires_in_days", 90)
        if days is not None:
            if not isinstance(days, int) or not 1 <= days <= MAX_TOKEN_DAYS:
                raise ValidationFailed(f"Choose 1 to {MAX_TOKEN_DAYS} days", {"field": "expires_in_days"})
            data["expires_at"] = utcnow() + timedelta(days=days)
        elif "calendar" not in scopes or len(scopes) > 1:
            raise ValidationFailed("Only calendar-only tokens can be made without an end date",
                                   {"field": "expires_in_days"})

    def create_token(self, data: dict, reason=None) -> tuple[ApiToken, str]:
        raw = TOKEN_PREFIX + secrets.token_urlsafe(30)
        self._raw = raw
        token = self.create(data, reason=reason or "API token created")
        return token, raw

    def apply_create(self, data):
        raw = self._raw
        return ApiToken(**data, user_id=self.actor.id, token_prefix=raw[:10], token_hash=hash_token(raw))

    def audit_value(self, field, value):
        return "…" if field == "token_hash" else value

    def revoke(self, token_id, reason=None) -> ApiToken:
        token = self.get(token_id)
        if token.user_id != self.actor.id and not self.is_admin():
            raise Forbidden("You can revoke only your own tokens")
        if token.revoked_at is None:
            with self.transaction():
                token.revoked_at = utcnow()
                token.updated_by_id = self.actor.id
                self._audit(token.id, "revoke", reason=reason or "Revoked")
        return token


class WebhookService(CommandService):
    model = Webhook
    entity_type = "webhook"
    permissions = {"create": "integrations.manage", "update": "integrations.manage", "delete": "integrations.manage"}
    protected_fields = frozenset({"secret"})

    def base_query(self):
        if not actor_can(self.actor, "integrations.manage"):
            raise Forbidden("Only administrators manage webhooks")
        return super().base_query()

    def list(self, params):
        return paginate(self.base_query().order_by(Webhook.name), params, self.serialize)

    @staticmethod
    def serialize(w: Webhook, *, secret: bool = False) -> dict:
        from sqlalchemy import func

        from app.modules.notifications.models import Delivery

        unit = db.session.get(OrgUnit, w.unit_id) if w.unit_id else None
        stats = dict(db.session.execute(select(Delivery.status, func.count()).where(Delivery.webhook_id == w.id)
                                        .group_by(Delivery.status)).all())
        p = urlparse(w.url)
        out = {"id": w.id, "name": w.name, "url": w.url, "host": p.netloc, "format": w.format, "events": w.events,
               "unit_id": w.unit_id, "unit": {"id": unit.id, "name": unit.name} if unit else None,
               "description": w.description, "is_active": w.is_active, "version": w.version,
               "deliveries": {"pending": stats.get("pending", 0), "sent": stats.get("sent", 0),
                              "failed": stats.get("failed", 0)}}
        if secret:
            out["secret"] = w.secret
        return out

    def audit_value(self, field, value):
        return "…" if field == "secret" else value

    @staticmethod
    def event_catalog() -> dict:
        return {"entities": [{"code": k, "label": v} for k, v in WEBHOOK_ENTITIES.items()],
                "operations": list(OPERATIONS),
                "alerts": [{"code": f"alert.{k}", "label": label} for k, (label, _, _) in KINDS.items()],
                "formats": [{"code": k, "label": v} for k, v in WEBHOOK_FORMATS.items()]}

    def _check(self, data, obj=None):
        if "url" in data:
            p = urlparse(data["url"] or "")
            if p.scheme not in ("https", "http") or not p.netloc:
                raise ValidationFailed("Enter an address starting with https://", {"field": "url"})
        if "format" in data and data["format"] not in WEBHOOK_FORMATS:
            raise ValidationFailed("Choose JSON or Microsoft Teams", {"field": "format"})
        if "events" in data:
            events = sorted(set(data["events"] or []))
            if not events:
                raise ValidationFailed("Choose at least one event", {"field": "events"})
            alerts = {f"alert.{k}" for k in KINDS}
            for e in events:
                entity, _, op = e.partition(".")
                if e in alerts or (entity in WEBHOOK_ENTITIES and (op == "*" or op in OPERATIONS)):
                    continue
                raise ValidationFailed(f"Unknown event: {e}", {"field": "events"})
            data["events"] = events
        if data.get("unit_id") is not None:
            unit = db.session.get(OrgUnit, data["unit_id"])
            if unit is None or unit.tenant_id != self.tenant_id or unit.is_deleted:
                raise ValidationFailed("Unit not found", {"field": "unit_id"})

    def validate_create(self, data):
        for field in ("name", "url", "events"):
            if not data.get(field):
                raise ValidationFailed("Fill this in", {"field": field})
        data.setdefault("format", "json")
        self._check(data)

    def apply_create(self, data):
        return Webhook(**data, secret=new_secret())

    def validate_update(self, obj, changes):
        self._check(changes, obj)

    def create(self, data, reason=None):
        obj = super().create(data, reason=reason)
        forget_webhooks()
        return obj

    def update(self, record_id, changes, **kwargs):
        obj = super().update(record_id, changes, **kwargs)
        forget_webhooks()
        return obj

    def delete(self, record_id, **kwargs):
        obj = super().delete(record_id, **kwargs)
        forget_webhooks()
        return obj

    def rotate_secret(self, webhook_id) -> Webhook:
        w = self.get(webhook_id)
        with self.transaction():
            w.secret = new_secret()
            w.updated_by_id = self.actor.id
            self._audit(w.id, "update", field="secret", old="…", new="…", reason="Secret rotated")
        return w

    def test(self, webhook_id) -> dict:
        """Queue a test message to the webhook and try to send it straight away."""
        from app.modules.notifications.delivery import deliver_one, serialize
        from app.modules.notifications.models import Delivery

        w = self.get(webhook_id)
        now = utcnow()
        d = Delivery(tenant_id=self.tenant_id, channel="webhook", target=w.url, webhook_id=w.id, event="test",
                     subject="Test message", status="pending", attempts=0, next_attempt_at=now, created_at=now,
                     payload={"event": "test", "occurred_at": now.isoformat(),
                              "data": {"title": "Control Tower test message",
                                       "text": f"Sent by {self.actor.full_name} to check the “{w.name}” webhook."}})
        db.session.add(d)
        db.session.commit()
        deliver_one(d)
        return serialize(d)


def deliveries(actor, params) -> dict:
    from app.modules.notifications.delivery import serialize
    from app.modules.notifications.models import Delivery

    if not actor_can(actor, "integrations.manage"):
        raise Forbidden("Only administrators see deliveries")
    stmt = select(Delivery).where(Delivery.tenant_id == actor.tenant_id)
    if status := params.get("status"):
        stmt = stmt.where(Delivery.status == status)
    if hook := params.get("webhook_id"):
        stmt = stmt.where(Delivery.webhook_id == int(hook))
    if channel := params.get("channel"):
        stmt = stmt.where(Delivery.channel == channel)
    return paginate(stmt.order_by(Delivery.id.desc()), params, serialize)
