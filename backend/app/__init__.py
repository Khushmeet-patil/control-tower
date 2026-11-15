"""Flask application factory."""
import logging

from flask import Flask, g, request, send_from_directory

from app.config import FRONTEND_DIR, get_config
from app.core.audit import current_correlation_id
from app.core.errors import Unauthorized, ValidationFailed, register_error_handlers
from app.extensions import db, login_manager, migrate

MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


def create_app(config_name: str | None = None) -> Flask:
    app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")
    app.config.from_object(get_config(config_name))
    app.json.sort_keys = False  # keep response fields in schema order

    _configure_logging(app)
    db.init_app(app)
    migrate.init_app(app, db, render_as_batch=True)  # batch mode lets migrations also run on SQLite
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


def _configure_login(app: Flask) -> None:
    from app.modules.auth.models import User

    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id: str):
        user = db.session.get(User, int(user_id))
        if user is None or user.is_deleted or not user.is_active:
            return None
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
        incoming = request.headers.get("X-Correlation-ID", "")
        if incoming.isalnum() and len(incoming) <= 64:
            g.correlation_id = incoming
        else:
            current_correlation_id()
        # JSON-only writes: browsers cannot send cross-site JSON without CORS, which blocks CSRF.
        if request.path.startswith("/api/") and request.method in MUTATING and not request.is_json:
            raise ValidationFailed("Requests must send JSON (Content-Type: application/json)")

    @app.after_request
    def finish_request(response):
        response.headers["X-Correlation-ID"] = g.get("correlation_id", "")
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "same-origin"
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

    for bp in (auth_bp, audit_bp, organisation_bp, people_bp, access_bp, lookups_bp, config_bp, work_bp, workflows_bp,
               rules_bp, views_bp, dashboards_bp):
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
