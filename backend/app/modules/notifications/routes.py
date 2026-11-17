from flask import Blueprint, request
from flask_login import current_user

from app.core.permissions import login_required
from app.modules.notifications.service import NotificationService

bp = Blueprint("notifications", __name__, url_prefix="/api/v1/notifications")


@bp.get("")
@login_required
def list_notifications():
    return NotificationService(current_user).list(request.args)


@bp.get("/count")
@login_required
def unread_count():
    return {"unread": NotificationService(current_user).unread_count()}


@bp.post("/read")
@login_required
def mark_read():
    body = request.get_json() or {}
    n = NotificationService(current_user).mark_read(body.get("ids"), all_=bool(body.get("all")))
    return {"marked": n}


@bp.get("/preferences")
@login_required
def get_preferences():
    return NotificationService(current_user).preferences()


@bp.put("/preferences")
@login_required
def set_preferences():
    return NotificationService(current_user).set_preferences((request.get_json() or {}).get("kinds") or {})
