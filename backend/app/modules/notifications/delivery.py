"""Sending the outbox (Delivery rows): email over SMTP and webhook calls over HTTPS.

Run on a schedule (every minute or two):  flask --app run notify --deliver

Each message is tried, and on failure tried again later (1, 2, 4 … minutes, up to MAX_ATTEMPTS), then
marked failed; administrators see failures in Integrations. Each row is committed on its own, so one
bad address never holds up the rest.

Webhooks:
- format "json": POST of {"event", "occurred_at", "data"} signed with the webhook's secret:
  header X-ControlTower-Signature = "sha256=" + HMAC-SHA256(secret, body). Receivers should check it.
- format "teams": a Microsoft Teams incoming-webhook message card (title, text, link button).
"""
import hashlib
import hmac
import json
import smtplib
import ssl
import urllib.error
import urllib.request
from datetime import timedelta
from email.message import EmailMessage

from flask import current_app
from sqlalchemy import or_, select

from app.core.models import utcnow
from app.extensions import db
from app.modules.notifications.models import Delivery

MAX_ATTEMPTS = 8
TIMEOUT = 10


def _backoff(attempts: int) -> timedelta:
    return timedelta(minutes=min(2 ** (attempts - 1), 240))


# ---------------------------------------------------------------------- email
def _email_text(payload: dict) -> str:
    lines = [f"Hello {payload.get('name') or ''},".strip(), "", payload.get("title") or ""]
    if payload.get("body"):
        lines += ["", payload["body"]]
    if payload.get("link"):
        lines += ["", f"Open: {payload['link']}"]
    lines += ["", "—", "Control Tower. Change which emails you get under your name → Notifications."]
    return "\n".join(lines)


def send_email(d: Delivery) -> None:
    cfg = current_app.config
    msg = EmailMessage()
    msg["Subject"] = d.subject or "Control Tower"
    msg["From"] = cfg.get("MAIL_FROM") or "control-tower@localhost"
    msg["To"] = d.target
    msg.set_content(_email_text(d.payload or {}))
    port = int(cfg.get("MAIL_PORT") or 587)
    if cfg.get("MAIL_USE_SSL"):
        server = smtplib.SMTP_SSL(cfg["MAIL_SERVER"], port, timeout=TIMEOUT, context=ssl.create_default_context())
    else:
        server = smtplib.SMTP(cfg["MAIL_SERVER"], port, timeout=TIMEOUT)
    with server:
        if cfg.get("MAIL_USE_TLS", True) and not cfg.get("MAIL_USE_SSL"):
            server.starttls(context=ssl.create_default_context())
        if cfg.get("MAIL_USERNAME"):
            server.login(cfg["MAIL_USERNAME"], cfg.get("MAIL_PASSWORD") or "")
        server.send_message(msg)


# ---------------------------------------------------------------------- webhooks
def teams_card(payload: dict) -> dict:
    data = payload.get("data") or {}
    card = {"@type": "MessageCard", "@context": "https://schema.org/extensions", "themeColor": "2F5D8A",
            "summary": data.get("title") or payload.get("event"), "title": data.get("title") or payload.get("event"),
            "text": data.get("text") or ""}
    if data.get("link"):
        card["potentialAction"] = [{"@type": "OpenUri", "name": "Open in Control Tower",
                                    "targets": [{"os": "default", "uri": data["link"]}]}]
    return card


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new((secret or "").encode(), body, hashlib.sha256).hexdigest()


def send_webhook(d: Delivery) -> int:
    from app.modules.integrations.models import Webhook

    hook = db.session.get(Webhook, d.webhook_id) if d.webhook_id else None
    if hook is None or hook.is_deleted or not hook.is_active:
        raise RuntimeError("The webhook was removed or switched off")
    payload = d.payload or {}
    body = json.dumps(teams_card(payload) if hook.format == "teams" else payload, default=str).encode()
    req = urllib.request.Request(hook.url, data=body, method="POST", headers={
        "Content-Type": "application/json", "User-Agent": "ControlTower-Webhooks/1.0",
        "X-ControlTower-Event": d.event, "X-ControlTower-Delivery": str(d.id),
        "X-ControlTower-Signature": sign(hook.secret, body)})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:  # noqa: S310 — admin-set https/http address
            return resp.status
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}") from exc


# ---------------------------------------------------------------------- the loop
def deliver_one(d: Delivery) -> bool:
    d.attempts += 1
    try:
        if d.channel == "email":
            send_email(d)
        elif d.channel == "webhook":
            d.response_code = send_webhook(d)
        else:
            raise RuntimeError(f"Unknown channel {d.channel}")
    except Exception as exc:  # noqa: BLE001 — any failure is recorded and retried
        d.last_error = str(exc)[:1000] or type(exc).__name__
        if d.attempts >= MAX_ATTEMPTS:
            d.status, d.next_attempt_at = "failed", None
        else:
            d.next_attempt_at = utcnow() + _backoff(d.attempts)
        db.session.commit()
        return False
    d.status, d.sent_at, d.last_error, d.next_attempt_at = "sent", utcnow(), None, None
    db.session.commit()
    return True


def deliver_pending(limit: int = 200) -> dict:
    now = utcnow()
    rows = db.session.scalars(select(Delivery).where(
        Delivery.status == "pending", or_(Delivery.next_attempt_at.is_(None), Delivery.next_attempt_at <= now))
        .order_by(Delivery.id).limit(limit)).all()
    sent = sum(1 for d in rows if deliver_one(d))
    return {"tried": len(rows), "sent": sent, "failed": len(rows) - sent}


def retry(delivery_id: int) -> Delivery:
    d = db.session.get(Delivery, delivery_id)
    d.status, d.next_attempt_at, d.attempts = "pending", utcnow(), 0
    db.session.commit()
    return d


def serialize(d: Delivery) -> dict:
    return {"id": d.id, "channel": d.channel, "target": d.target if d.channel == "email" else _mask(d.target),
            "webhook_id": d.webhook_id, "event": d.event, "subject": d.subject, "status": d.status,
            "attempts": d.attempts, "last_error": d.last_error, "response_code": d.response_code,
            "created_at": d.created_at.isoformat(), "sent_at": d.sent_at.isoformat() if d.sent_at else None,
            "next_attempt_at": d.next_attempt_at.isoformat() if d.next_attempt_at else None}


def _mask(url: str) -> str:
    """Webhook addresses often carry a secret in the path (Teams does): show only the host."""
    from urllib.parse import urlparse

    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}/…"
