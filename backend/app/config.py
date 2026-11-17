"""Application configuration, loaded from environment variables / .env."""
import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent
FRONTEND_DIR = PROJECT_DIR / "frontend"

load_dotenv(BACKEND_DIR / ".env")


def _database_url(raw: str | None) -> str:
    """Relative SQLite paths (sqlite:///file.db) are resolved against backend/."""
    url = raw or "sqlite:///control_tower_dev.db"
    prefix = "sqlite:///"
    if url.startswith(prefix) and not url.startswith(prefix + "/") and url != "sqlite://":
        url = f"{prefix}{BACKEND_DIR / url[len(prefix):]}"
    return url


class BaseConfig:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-insecure-key")
    SQLALCHEMY_DATABASE_URI = _database_url(os.getenv("DATABASE_URL"))
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JSON_SORT_KEYS = False

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_DURATION = timedelta(days=14)  # Flask-Login's default is a year

    # Largest request accepted (imports send files of up to 5 MB, base64-encoded).
    MAX_CONTENT_LENGTH = 12 * 1024 * 1024
    # Sign-in protection: this many failures in a row lock the account for LOGIN_LOCK_MINUTES.
    LOGIN_MAX_FAILURES = int(os.getenv("LOGIN_MAX_FAILURES", "5"))
    LOGIN_LOCK_MINUTES = int(os.getenv("LOGIN_LOCK_MINUTES", "15"))

    # Dates such as "today" and "overdue" are worked out in this timezone, never in UTC.
    TIMEZONE = os.getenv("TIMEZONE", "Asia/Kolkata")

    DEFAULT_PAGE_SIZE = 25
    MAX_PAGE_SIZE = 200

    # Backups (`flask backup`): where they go, how long they are kept, and when admins are reminded.
    BACKUP_DIR = os.getenv("BACKUP_DIR", str(BACKEND_DIR / "backups"))
    BACKUP_KEEP_DAYS = int(os.getenv("BACKUP_KEEP_DAYS", "30"))
    BACKUP_KEEP_MIN = int(os.getenv("BACKUP_KEEP_MIN", "3"))
    BACKUP_REMIND_DAYS = int(os.getenv("BACKUP_REMIND_DAYS", "7"))

    # The address people open Control Tower at (links in emails, Teams messages and calendar feeds).
    APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:5050")

    # Notifications (Phase 10). Email is sent only when MAIL_SERVER is set; `flask notify --deliver` sends it.
    MAIL_SERVER = os.getenv("MAIL_SERVER", "")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
    MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "true").lower() == "true"
    MAIL_USE_SSL = os.getenv("MAIL_USE_SSL", "false").lower() == "true"
    MAIL_FROM = os.getenv("MAIL_FROM", "Control Tower <control-tower@localhost>")
    NOTIFY_DUE_DAYS = int(os.getenv("NOTIFY_DUE_DAYS", "3"))

    # Microsoft Entra ID sign-in (Phase 10); off unless all three are set. See integrations/entra.py.
    ENTRA_TENANT_ID = os.getenv("ENTRA_TENANT_ID", "")
    ENTRA_CLIENT_ID = os.getenv("ENTRA_CLIENT_ID", "")
    ENTRA_CLIENT_SECRET = os.getenv("ENTRA_CLIENT_SECRET", "")
    ENTRA_REDIRECT_URI = os.getenv("ENTRA_REDIRECT_URI", "")
    ENTRA_ALLOW_PASSWORD = os.getenv("ENTRA_ALLOW_PASSWORD", "true").lower() == "true"

    SEED_ADMIN_EMAIL = os.getenv("SEED_ADMIN_EMAIL", "admin@controltower.local")
    SEED_ADMIN_PASSWORD = os.getenv("SEED_ADMIN_PASSWORD", "ChangeMe123!")


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class ProductionConfig(BaseConfig):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True


class TestConfig(BaseConfig):
    TESTING = True
    SECRET_KEY = "test-secret"
    SQLALCHEMY_DATABASE_URI = os.getenv("TEST_DATABASE_URL", "sqlite://")
    SQLALCHEMY_ENGINE_OPTIONS = {}
    PASSWORD_HASH_METHOD = "pbkdf2:sha256:1000"  # fast hashing for tests only
    MAIL_SERVER = ""
    ENTRA_TENANT_ID = ENTRA_CLIENT_ID = ENTRA_CLIENT_SECRET = ""


CONFIGS = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestConfig,
}


def get_config(name: str | None = None):
    return CONFIGS[name or os.getenv("FLASK_ENV", "development")]
