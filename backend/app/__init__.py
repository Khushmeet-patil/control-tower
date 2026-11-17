"""Flask application factory."""
import hmac
import logging

from flask import Flask, g, request, send_from_directory

from app.config import FRONTEND_DIR, get_config
from app.core.audit import current_correlation_id
from app.core.errors import Unauthorized, ValidationFailed, register_error_handlers
from app.extensions import db, login_manager, migrate

MUTATING = {"POST", "PUT", "PATCH", "DELETE"}
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
       "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; "
       "frame-ancestors 'self'")


def create_app(config_name: str | None = None) -> Flask:
    app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")
    app.config.from_object(get_config(config_name))
    _check_secret_key(app)
    app.json.sort_keys = False  # keep response fields in schema order

    _configure_logging(app)
    db.init_app(app)
    migrate.init_app(app, db, render_as_batch=True)  # batch mode lets migrations also run on SQLite
    _configure_sqlite(app)
    _configure_login(app)
    register_error_handlers(app)
    _register_request_hooks(app)
    _register_blueprints(app)
    _register_cli(app)
    return app


def _configure_logging(app: Flask) -> None:
    class CorrelationFilter(logging.Filter):
        def filter(self, record):
            try:
                record.correlation_id = g.get("correlation_id", "-")
            except RuntimeError:
                record.correlation_id = "-"
            return True

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(correlation_id)s] %(name)s: %(message)s"))
    handler.addFilter(CorrelationFilter())
    app.logger.handlers = [handler]
    app.logger.setLevel(logging.DEBUG if app.debug else logging.INFO)


def _check_secret_key(app: Flask) -> None:
    """Sessions are signed with SECRET_KEY: production must not run on the development default."""
    if app.debug or app.testing:
        return
    key = app.config.get("SECRET_KEY") or ""
    if key in ("dev-only-insecure-key", "change-me-to-a-long-random-string") or len(key) < 32:
        raise RuntimeError("Set SECRET_KEY to a long random value (at least 32 characters), e.g. "
                           "python -c 'import secrets; print(secrets.token_urlsafe(48))'")


def _configure_sqlite(app: Flask) -> None:
    """Make SQLite transactions behave like MySQL's.

    Python's sqlite3 driver (legacy mode) starts transactions lazily and never before a SAVEPOINT, so a
    released savepoint would commit for real and a later rollback could not undo it (imports preview
    by rolling back). Letting SQLAlchemy emit BEGIN itself fixes that. MySQL needs nothing.
    """
    from sqlalchemy import event

    with app.app_context():
        engine = db.engine
    if engine.dialect.name != "sqlite":
        return

    @event.listens_for(engine, "connect")
    def _no_driver_transactions(dbapi_connection, _record):
        dbapi_connection.isolation_level = None

    @event.listens_for(engine, "begin")
    def _begin(connection):
        connection.exec_driver_sql("BEGIN")


def _configure_login(app: Flask) -> None:
    from app.modules.auth.models import User

    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(session_id: str):
        uid, _, token = str(session_id).partition(".")
        if not uid.isdigit():
            return None
        user = db.session.get(User, int(uid))
        if user is None or user.is_deleted or not user.is_active:
            return None
        if not hmac.compare_digest(token, user.session_token()):
            return None  # the password changed since this session started
        return user

    @login_manager.unauthorized_handler
    def unauthorized():
        raise Unauthorized("Please sign in")


def _register_request_hooks(app: Flask) -> None:
    @app.before_request
    def start_request():
        # Access is cached per request only; never carry it over from a previous request.
        g.pop("_access_cache", None)
        g.pop("_scope_cache", None)
        g.pop("_settings_cache", None)
        g.pop("_health_cache", None)
        g.pop("_login_user", None)  # load the signed-in user afresh (a password change ends other sessions)
        _api_token_sign_in()
        incoming = request.headers.get("X-Correlation-ID", "")
        if incoming.isalnum() and len(incoming) <= 64:
            g.correlation_id = incoming
        else:
            current_correlation_id()
        # JSON-only writes: browsers cannot send cross-site JSON without CORS, which blocks CSRF.
        if request.path.startswith("/api/") and request.method in MUTATING and not request.is_json:
            raise ValidationFailed("Requests must send JSON (Content-Type: application/json)")

    def _api_token_sign_in():
        """API tokens ("Authorization: Bearer ct_…") act as their owner for this request only.
        A "read" token may only read; "write" may also change records (through the same services, audited
        with source "api"). Tokens cannot sign in, change passwords or make more tokens."""
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer ") or not request.path.startswith("/api/"):
            return
        from app.modules.integrations.service import user_for_token

        user, token = user_for_token(header[7:].strip())
        if user is None or not ({"read", "write"} & set(token.scopes)):
            raise Unauthorized("The API token is not valid, has expired or was revoked")
        if request.method in MUTATING and "write" not in token.scopes:
            raise Unauthorized("This API token can only read. Make a token with the write scope to change records.")
        if request.path.startswith(("/api/v1/auth/", "/api/v1/api-tokens", "/api/v1/calendar/link")):
            raise Unauthorized("Sign in on the screen for this; API tokens cannot be used here")
        g._login_user = user
        g.api_token_id = token.id

    @app.after_request
    def finish_request(response):
        response.headers["X-Correlation-ID"] = g.get("correlation_id", "")
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "same-origin"
        # Only this server's own scripts run; no plugins; the app cannot be framed by other sites.
        response.headers["Content-Security-Policy"] = CSP
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        if app.config.get("SESSION_COOKIE_SECURE"):  # production, over HTTPS
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if request.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response


def _register_blueprints(app: Flask) -> None:
    from app.modules.access.routes import bp as access_bp
    from app.modules.audit.routes import bp as audit_bp
    from app.modules.auth.routes import bp as auth_bp
    from app.modules.config.routes import bp as config_bp
    from app.modules.lookups.routes import bp as lookups_bp
    from app.modules.organisation.routes import bp as organisation_bp
    from app.modules.people.routes import bp as people_bp
    from app.modules.work.routes import bp as work_bp
    from app.modules.rules.routes import bp as rules_bp
    from app.modules.views.routes import bp as views_bp
    from app.modules.workflows.routes import bp as workflows_bp
    from app.modules.dashboards.routes import bp as dashboards_bp
    from app.modules.capacity.routes import bp as capacity_bp
    from app.modules.demand.routes import bp as demand_bp
    from app.modules.tools.routes import bp as tools_bp
    from app.modules.snapshots.routes import bp as snapshots_bp, exports_bp
    from app.modules.presentations.routes import bp as presentations_bp
    from app.modules.imports.routes import bp as imports_bp
    from app.modules.backups.routes import bp as backups_bp
    from app.modules.notifications.routes import bp as notifications_bp
    from app.modules.integrations.routes import bp as integrations_bp
    from app.modules.scenarios.routes import bp as scenarios_bp
    from app.modules.templates.routes import bp as templates_bp

    for bp in (auth_bp, audit_bp, organisation_bp, people_bp, access_bp, lookups_bp, config_bp, work_bp, workflows_bp,
               rules_bp, views_bp, dashboards_bp, capacity_bp, demand_bp, tools_bp, snapshots_bp, exports_bp, presentations_bp,
               imports_bp, backups_bp, notifications_bp, integrations_bp, scenarios_bp, templates_bp):
        app.register_blueprint(bp)

    @app.get("/api/v1/health")
    def health():
        db.session.execute(db.text("SELECT 1"))
        return {"status": "ok"}

    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")


def _register_cli(app: Flask) -> None:
    from app.core.schema_export import schema_export_command
    from seed.cli import seed_command

    app.cli.add_command(seed_command)
    app.cli.add_command(schema_export_command)
    from app.modules.snapshots.cli import snapshot_command

    app.cli.add_command(snapshot_command)
    from app.modules.backups.cli import backup_command, restore_command

    app.cli.add_command(backup_command)
    app.cli.add_command(restore_command)
    from app.modules.notifications.cli import notify_command

    app.cli.add_command(notify_command)


# Import models so Alembic autogenerate sees every table.
from app.core import audit as _audit_models  # noqa: E402,F401
from app.modules.access import models as _access_models  # noqa: E402,F401
from app.modules.auth import models as _auth_models  # noqa: E402,F401
from app.modules.config import models as _config_models  # noqa: E402,F401
from app.modules.lookups import models as _lookup_models  # noqa: E402,F401
from app.modules.organisation import models as _org_models  # noqa: E402,F401
from app.modules.work import models as _work_models  # noqa: E402,F401
from app.modules.workflows import models as _workflow_models  # noqa: E402,F401
from app.modules.rules import models as _rule_models  # noqa: E402,F401
from app.modules.views import models as _view_models  # noqa: E402,F401
from app.modules.dashboards import models as _dashboard_models  # noqa: E402,F401
from app.modules.capacity import models as _capacity_models  # noqa: E402,F401
from app.modules.demand import models as _demand_models  # noqa: E402,F401
from app.modules.tools import models as _tool_models  # noqa: E402,F401
from app.modules.snapshots import models as _snapshot_models  # noqa: E402,F401
from app.modules.presentations import models as _presentation_models  # noqa: E402,F401
from app.modules.imports import models as _import_models  # noqa: E402,F401
from app.modules.notifications import models as _notification_models  # noqa: E402,F401
from app.modules.integrations import models as _integration_models  # noqa: E402,F401
from app.modules.scenarios import models as _scenario_models  # noqa: E402,F401
from app.modules.templates import models as _template_models  # noqa: E402,F401
