import os
from dotenv import load_dotenv
load_dotenv()

class Config:
    # Удаляем SERVER_NAME, чтобы Flask автоматически определял хост
    PREFERRED_URL_SCHEME = 'http'
    SECRET_KEY = os.getenv("SECRET_KEY", "your_super_secret_key")
    SQLALCHEMY_DATABASE_URI = 'sqlite:///users.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static/uploads')
    FERNET_SECRET_KEY = os.getenv("FERNET_SECRET_KEY")
    SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", 465))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    RATELIMIT_ENABLED = False
    SESSION_COOKIE_SECURE = False  # Для http
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_SECURE = False  # Для http
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = 'Lax'