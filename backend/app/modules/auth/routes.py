from flask import Blueprint, request
from flask_login import current_user, login_user, logout_user

from app.core.errors import Unauthorized, ValidationFailed
from app.core.permissions import login_required
from app.modules.auth.schemas import LoginIn, PasswordChangeIn
from app.modules.auth.service import authenticate, session_payload
from app.modules.people.service import PersonService

bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")


@bp.post("/login")
def login():
    body = LoginIn.model_validate(request.get_json() or {})
    user = authenticate(body.email, body.password)
    from app.modules.integrations.entra import password_allowed

    if not password_allowed() and not user.is_admin:  # administrators keep a way in if Microsoft is down
        raise Unauthorized("Use “Sign in with Microsoft”")
    login_user(user, remember=body.remember)
    return {"user": session_payload(user)}


@bp.post("/logout")
def logout():
    logout_user()
    return {"ok": True}


@bp.get("/me")
@login_required
def me():
    return {"user": session_payload(current_user)}


@bp.post("/change-password")
@login_required
def change_password():
    body = PasswordChangeIn.model_validate(request.get_json() or {})
    if not current_user.check_password(body.current_password):
        raise ValidationFailed("Current password is incorrect", {"field": "current_password"})
    user = PersonService(current_user).reset_password(current_user.id, body.new_password, reason="Changed own password")
    login_user(user or current_user._get_current_object())  # this session continues; every other one ends
    return {"ok": True}
