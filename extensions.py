import os
import smtplib
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from flask_mail import Mail
from cryptography.fernet import Fernet
from flask import current_app, render_template
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import secrets
from itsdangerous import URLSafeTimedSerializer
from redis import Redis

from config import Config

mail = Mail()
def get_serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])

db = SQLAlchemy()
login_manager = LoginManager()
limiter = Limiter(get_remote_address)
fernet = Fernet(os.getenv("FERNET_SECRET_KEY"))
migrate = Migrate()
redis_client = Redis.from_url(os.environ.get("REDIS_URL"), decode_responses=False)

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

# Отмена давних транзакций
def cancel_expired_transactions(app,minutes=1):
    with app.app_context():
        from models import Transaction  # импорт внутри функции
        from datetime import datetime, timedelta
        expiration_time = datetime.utcnow() - timedelta(minutes=minutes)
        expired = (
            Transaction.query
            .filter(Transaction.status == 'pending')
            .filter(Transaction.type=='topup')
            .filter(Transaction.created_at < expiration_time)
            .all()
        )

        for tx in expired:
            tx.status = 'cancelled'

        if expired:
            db.session.commit()

def generate_short_id(length=6):
    return secrets.token_hex(length // 2)


SMTP_SERVER = Config.SMTP_SERVER
SMTP_PORT = Config.SMTP_PORT
SMTP_USER = Config.SMPT_USER
SMTP_PASSWORD = Config.SMTP_PASSWORD


# Отправка письма
def send_confirmation_email(to_email, confirm_url):
    # Рендерим HTML
    html_body = render_template('mail/email.html', confirm_url=confirm_url)

    # Создаём письмо
    msg = MIMEMultipart('alternative')
    msg['Subject'] = Header('Подтвердите вашу почту — GameTrust', 'utf-8')
    msg['From'] = formataddr((str(Header('GameTrust', 'utf-8')), SMTP_USER))
    msg['To'] = to_email

    # Тело письма
    html_part = MIMEText(html_body.encode('utf-8'), 'html', 'utf-8')
    msg.attach(html_part)

    # Отправка
    try:
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, [to_email], msg.as_bytes())
            print("✅ Письмо успешно отправлено.")
    except Exception as e:
        print("❌ Ошибка отправки письма:", e)