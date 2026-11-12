from flask import Blueprint, request
from flask_login import current_user

from app.core.permissions import require_permission
from app.core.schemas import parse_body
from app.modules.people.schemas import PasswordResetIn, PersonCreateIn, PersonUpdateIn
from app.modules.people.service import PersonService

bp = Blueprint("people", __name__, url_prefix="/api/v1/people")


@bp.get("")
@require_permission("people.view")
def list_people():
    return PersonService(current_user).list(request.args)


@bp.get("/<int:person_id>")
@require_permission("people.view")
def get_person(person_id):
    svc = PersonService(current_user)
    return svc.serialize(svc.get(person_id))


@bp.post("")
@require_permission("people.manage")
def create_person():
    data, _, reason = parse_body(PersonCreateIn, request.get_json())
    svc = PersonService(current_user)
    return svc.serialize(svc.create(data, reason=reason)), 201


@bp.patch("/<int:person_id>")
@require_permission("people.manage")
def update_person(person_id):
    data, version, reason = parse_body(PersonUpdateIn, request.get_json())
    svc = PersonService(current_user)
    return svc.serialize(svc.update(person_id, data, expected_version=version, reason=reason))


@bp.post("/<int:person_id>/reset-password")
@require_permission("people.manage")
def reset_password(person_id):
    body = PasswordResetIn.model_validate(request.get_json() or {})
    PersonService(current_user).reset_password(person_id, body.password, reason=body.reason)
    return {"ok": True}
