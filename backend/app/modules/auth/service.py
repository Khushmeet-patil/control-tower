from sqlalchemy import select

from app.core.errors import Unauthorized
from app.core.models import utcnow
from app.extensions import db
from app.modules.auth.models import User
from app.modules.people.service import PersonService


def authenticate(email: str, password: str) -> User:
    user = db.session.scalar(
        select(User).where(User.email == email.strip().lower(), User.is_deleted.is_(False))
    )
    if user is None or not user.is_active or not user.check_password(password):
        raise Unauthorized("Email or password is incorrect")
    svc = PersonService(user, source="screen")
    with svc._transaction():
        user.last_login_at = utcnow()
        svc._audit(user.id, "login")
    return user


def session_payload(user: User) -> dict:
    """What the frontend needs about the signed-in person: profile, permissions and scope."""
    data = PersonService(user).serialize(user)
    data["permissions"] = sorted(user.permission_codes())
    data["scope"] = user.scope
    return data
