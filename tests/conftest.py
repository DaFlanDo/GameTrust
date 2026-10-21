import os
import sys

from cryptography.fernet import Fernet

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("FERNET_SECRET_KEY", Fernet.generate_key().decode())
os.environ["REDIS_URL"] = "redis://127.0.0.1:1/0"  # недоступный Redis: кэш должен молча отключаться
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from flask import g
from flask.testing import FlaskClient
from werkzeug.security import generate_password_hash

from app import create_app
from config import Config
from extensions import db, fernet
from models import Game, Lot, User


class Client(FlaskClient):
    """Тесты держат один контекст приложения, а Flask-Login кэширует пользователя в g.
    Сбрасываем кэш перед каждым запросом, как будто это новый запрос."""
    def open(self, *args, **kwargs):
        g.pop("_login_user", None)
        return super().open(*args, **kwargs)


@pytest.fixture
def make_app(tmp_path):
    def factory(**overrides):
        class TestConfig(Config):
            TESTING = True
            SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'test.db'}"
            UPLOAD_FOLDER = str(tmp_path / "uploads")
            WTF_CSRF_ENABLED = False
            RATELIMIT_ENABLED = False
        for key, value in overrides.items():
            setattr(TestConfig, key, value)
        app = create_app(TestConfig)
        app.test_client_class = Client
        with app.app_context():
            db.create_all()
        return app
    return factory


@pytest.fixture
def app(make_app):
    app = make_app()
    with app.app_context():
        yield app
        db.session.remove()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def make_user(app):
    counter = {"n": 0}

    def factory(balance=0, is_admin=False, username=None):
        counter["n"] += 1
        name = username or f"user{counter['n']}"
        user = User(username=name, email=f"{name}@example.com",
                    password=generate_password_hash("password123"),
                    balance=balance, is_admin=is_admin, is_confirmed=True)
        db.session.add(user)
        db.session.commit()
        return user
    return factory


@pytest.fixture
def game(app):
    g = Game(name="Counter-Strike 2", category="Keys")
    db.session.add(g)
    db.session.commit()
    return g


@pytest.fixture
def make_lot(app, game):
    def factory(seller, price=100, quantity=1, keys=None, **kwargs):
        lot = Lot(title=kwargs.pop("title", "Ключ CS2 Prime"), category=kwargs.pop("category", "Keys"), platform="PC",
                  description="Ключ активации", price=price, quantity=quantity,
                  autodelivery=bool(keys), user_id=seller.id, game_id=game.id,
                  autodelivery_data=fernet.encrypt("\n".join(keys).encode()).decode() if keys else None,
                  **kwargs)
        db.session.add(lot)
        db.session.commit()
        return lot
    return factory


def login(client, user):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True


def reload(obj):
    db.session.refresh(obj)
    return obj
