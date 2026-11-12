"""One error format for the whole API: {"error": {"code", "message", "details"}}."""
from flask import jsonify, request
from pydantic import ValidationError as PydanticValidationError
from werkzeug.exceptions import HTTPException


class AppError(Exception):
    status = 400
    code = "bad_request"

    def __init__(self, message: str | None = None, details=None):
        super().__init__(message or self.code)
        self.message = message or self.code.replace("_", " ").capitalize()
        self.details = details


class ValidationFailed(AppError):
    status = 422
    code = "validation_failed"


class Unauthorized(AppError):
    status = 401
    code = "unauthorized"


class Forbidden(AppError):
    status = 403
    code = "forbidden"


class NotFound(AppError):
    status = 404
    code = "not_found"


class Conflict(AppError):
    status = 409
    code = "conflict"


def error_response(status: int, code: str, message: str, details=None):
    return jsonify({"error": {"code": code, "message": message, "details": details}}), status


def _pydantic_details(exc: PydanticValidationError):
    return [
        {"field": ".".join(str(p) for p in err["loc"]), "message": err["msg"]}
        for err in exc.errors()
    ]


def register_error_handlers(app):
    @app.errorhandler(AppError)
    def handle_app_error(exc: AppError):
        return error_response(exc.status, exc.code, exc.message, exc.details)

    @app.errorhandler(PydanticValidationError)
    def handle_pydantic(exc: PydanticValidationError):
        return error_response(422, "validation_failed", "Some fields are invalid", _pydantic_details(exc))

    @app.errorhandler(HTTPException)
    def handle_http(exc: HTTPException):
        if request.path.startswith("/api/"):
            return error_response(exc.code or 500, (exc.name or "error").lower().replace(" ", "_"), exc.description)
        return exc

    @app.errorhandler(Exception)
    def handle_unexpected(exc: Exception):
        app.logger.exception("Unhandled error on %s %s", request.method, request.path)
        return error_response(500, "server_error", "Something went wrong. Please try again.")
