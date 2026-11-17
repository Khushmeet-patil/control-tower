"""Signing in.

Protection against guessing passwords: after LOGIN_MAX_FAILURES wrong passwords in a row an account is
locked for LOGIN_LOCK_MINUTES (both audited). Unknown emails take as long as known ones (a dummy hash is
checked), so response times do not reveal which emails have accounts.
"""
from datetime import timedelta

from flask import current_app
from sqlalchemy import select
from werkzeug.security import check_password_hash, generate_password_hash

from app.core.errors import Unauthorized
from app.core.models import utcnow
from app.extensions import db
from app.modules.auth.models import User
from app.modules.people.service import PersonService

WRONG = "Email or password is incorrect"
_DUMMY = {}


def _dummy_hash():
    method = current_app.config.get("PASSWORD_HASH_METHOD", "scrypt")
    if method not in _DUMMY:
        _DUMMY[method] = generate_password_hash("not-a-real-password", method=method)
    return _DUMMY[method]


def authenticate(email: str, password: str) -> User:
    user = db.session.scalar(
        select(User).where(User.email == email.strip().lower(), User.is_deleted.is_(False))
    )
    now = utcnow()
    if user is None:
        check_password_hash(_dummy_hash(), password)  # same work as a real check
        raise Unauthorized(WRONG)
    if user.locked_until and user.locked_until > now:
        minutes = max(1, int((user.locked_until - now).total_seconds() // 60) + 1)
        raise Unauthorized(f"Too many failed sign-ins. Try again in {minutes} minute{'s' if minutes != 1 else ''}.")
    if not user.is_active or not user.check_password(password):
        if user.is_active:
            _failed(user, now)
        raise Unauthorized(WRONG)
    svc = PersonService(user, source="screen")
    with svc._transaction():
        user.last_login_at = now
        user.failed_logins = 0
        user.locked_until = None
        svc._audit(user.id, "login")
    return user


def _failed(user: User, now) -> None:
    """Count a wrong password; lock the account after too many in a row."""
    svc = PersonService(None, tenant_id=user.tenant_id, source="screen")
    limit = current_app.config["LOGIN_MAX_FAILURES"]
    with svc._transaction():
        user.failed_logins = (user.failed_logins or 0) + 1
        svc._audit(user.id, "login_failed", new={"attempt": user.failed_logins}, reason="Wrong password")
        if user.failed_logins >= limit:
            user.locked_until = now + timedelta(minutes=current_app.config["LOGIN_LOCK_MINUTES"])
            user.failed_logins = 0
            svc._audit(user.id, "locked", new={"until": user.locked_until.isoformat(timespec="minutes")},
                       reason=f"{limit} wrong passwords in a row")


def session_payload(user: User) -> dict:
    """What the frontend needs about the signed-in person: profile, permissions and scope."""
    data = PersonService(user).serialize(user)
    data["permissions"] = sorted(user.permission_codes())
    data["scope"] = user.scope
    return data
