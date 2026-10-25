import os

from dotenv import load_dotenv

load_dotenv()


def _required(name):
    value = os.getenv(name, "")
    if not value or value.startswith("change-me"):
        raise RuntimeError(f"Не задана переменная окружения {name} (см. .env.example)")
    return value


def _flag(name, default):
    return os.getenv(name, default).lower() in ("1", "true", "yes")


class Config:
    SECRET_KEY = _required("SECRET_KEY")
    FERNET_SECRET_KEY = _required("FERNET_SECRET_KEY")

    # Без DATABASE_URL — SQLite в папке instance/
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///gametrust.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "static", "uploads")
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024

    # Без SMTP_USER письмо не отправляется, а ссылка подтверждения пишется в лог
    SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", 465))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")

    RATELIMIT_ENABLED = _flag("RATELIMIT_ENABLED", "1")
    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")

    # За reverse proxy (Caddy/nginx): брать IP клиента и схему из X-Forwarded-*,
    # иначе лимиты считаются по адресу прокси, а ссылки в письмах уходят с http://
    TRUST_PROXY = _flag("TRUST_PROXY", "0")

    SESSION_COOKIE_SECURE = _flag("COOKIE_SECURE", "0")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
