"""Application configuration, loaded from environment variables / .env."""
import os
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

    # Dates such as "today" and "overdue" are worked out in this timezone, never in UTC.
    TIMEZONE = os.getenv("TIMEZONE", "Asia/Kolkata")

    DEFAULT_PAGE_SIZE = 25
    MAX_PAGE_SIZE = 200

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


CONFIGS = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestConfig,
}


def get_config(name: str | None = None):
    return CONFIGS[name or os.getenv("FLASK_ENV", "development")]
