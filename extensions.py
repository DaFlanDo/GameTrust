import logging
import secrets
import smtplib
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

from cryptography.fernet import Fernet
from flask import current_app, render_template
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from itsdangerous import URLSafeTimedSerializer
from redis import Redis

from config import Config

logger = logging.getLogger(__name__)

db = SQLAlchemy()
login_manager = LoginManager()
limiter = Limiter(get_remote_address)
csrf = CSRFProtect()
migrate = Migrate()
fernet = Fernet(Config.FERNET_SECRET_KEY)
redis_client = Redis.from_url(Config.REDIS_URL, decode_responses=False,
                              socket_connect_timeout=0.5, socket_timeout=0.5)


def get_serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])


# Кэш не обязателен: если Redis недоступен, страницы просто собираются заново
def get_cache(key):
    try:
        return redis_client.get(key)
    except Exception:
        return None


def set_cache(key, value, ttl=300):
    try:
        redis_client.setex(key, ttl, value)
    except Exception:
        pass


def delete_cache(*keys):
    try:
        redis_client.delete(*keys)
    except Exception:
        pass


def generate_short_id(length=6):
    return secrets.token_hex(length // 2)


def send_confirmation_email(to_email, confirm_url):
    cfg = current_app.config
    if not cfg['SMTP_USER']:
        logger.warning("SMTP не настроен, ссылка подтверждения для %s: %s", to_email, confirm_url)
        return

    html_body = render_template('mail/email.html', confirm_url=confirm_url)
    msg = MIMEMultipart('alternative')
    msg['Subject'] = Header('Подтвердите вашу почту — GameTrust', 'utf-8')
    msg['From'] = formataddr((str(Header('GameTrust', 'utf-8')), cfg['SMTP_USER']))
    msg['To'] = to_email
    msg.attach(MIMEText(html_body.encode('utf-8'), 'html', 'utf-8'))

    try:
        with smtplib.SMTP_SSL(cfg['SMTP_SERVER'], cfg['SMTP_PORT']) as server:
            server.login(cfg['SMTP_USER'], cfg['SMTP_PASSWORD'])
            server.sendmail(cfg['SMTP_USER'], [to_email], msg.as_bytes())
    except Exception:
        logger.exception("Не удалось отправить письмо на %s", to_email)
