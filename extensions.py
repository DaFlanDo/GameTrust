import os
import logging

from cryptography.fernet import Fernet
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


db = SQLAlchemy()
login_manager = LoginManager()
limiter = Limiter(get_remote_address)
fernet = Fernet(os.getenv("FERNET_SECRET_KEY"))
migrate = Migrate()

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
            print(f"[CLEANUP] Отменено {len(expired)} просроченных транзакций.")
        else:
            print("[CLEANUP] Нет просроченных транзакций.")

