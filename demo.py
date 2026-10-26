"""Демо-стенд (DEMO_MODE=1).

Посетитель входит одной кнопкой под сид-аккаунтом нужной роли (seed.py), без пароля.
Аккаунты общие, поэтому им нельзя включить 2FA, их нельзя заблокировать или удалить,
а `flask reset-demo` раз в сутки возвращает базу к исходным данным.
"""
import os
import shutil

import click
from flask import Blueprint, abort, current_app, flash, redirect, url_for
from flask_login import login_user, logout_user
from flask_migrate import upgrade
from sqlalchemy import text

from extensions import db, delete_cache, redis_client
from models import User

# Роль → (сид-аккаунт, подпись на кнопке, куда вести после входа)
DEMO_ROLES = {
    "buyer": ("demo@example.com", "Покупатель", "purchase.my_orders"),
    # У KeyForge есть сделка с demo в ожидании подтверждения и переписка по ней
    "seller": ("keyforge@example.com", "Продавец", "lot.my_sales"),
    "admin": ("admin@example.com", "Администратор", "admin.dashboard"),
}
DEMO_EMAILS = frozenset(email for email, _, _ in DEMO_ROLES.values())

demo_bp = Blueprint("demo", __name__)


def demo_enabled():
    return current_app.config.get("DEMO_MODE", False)


def is_demo_user(user):
    return demo_enabled() and user is not None and getattr(user, "email", None) in DEMO_EMAILS


def demo_role_of(user):
    if not is_demo_user(user):
        return None
    return next(role for role, (email, _, _) in DEMO_ROLES.items() if email == user.email)


@demo_bp.route("/demo/<role>")
def enter(role):
    """Вход без пароля под ролью — ссылкой из портфолио, README или кнопкой на сайте."""
    if not demo_enabled() or role not in DEMO_ROLES:
        abort(404)
    email, _, endpoint = DEMO_ROLES[role]
    user = User.query.filter_by(email=email).first()
    if user is None:
        flash("Демо-данные ещё загружаются, попробуйте через минуту", "warning")
        return redirect(url_for("lot.home"))
    logout_user()
    login_user(user)
    return redirect(url_for(endpoint))


def demo_context():
    """Переменные для шаблонов: кнопки входа и плашка смены роли."""
    from flask_login import current_user
    if not demo_enabled():
        return {"demo_roles": None}
    return {
        "demo_roles": [(role, title) for role, (_, title, _) in DEMO_ROLES.items()],
        "demo_current_role": demo_role_of(current_user) if current_user.is_authenticated else None,
    }


@click.command("reset-demo")
def reset_demo_command():
    """Вернуть демо-стенд к исходным данным (для cron)."""
    from seed import seed

    if not demo_enabled():
        raise click.ClickException("reset-demo работает только при DEMO_MODE=1")

    # Схему целиком, вместе с alembic_version — миграции прогонятся с нуля
    db.drop_all()
    with db.engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
    upgrade()
    click.echo("✓ База пересоздана")

    upload = current_app.config["UPLOAD_FOLDER"]
    if os.path.isdir(upload):
        for name in os.listdir(upload):
            path = os.path.join(upload, name)
            shutil.rmtree(path) if os.path.isdir(path) else os.remove(path)
    click.echo("✓ Загрузки очищены")

    seed()

    # Кэш главной и списков игр, иначе ещё минут десять показывались бы данные до сброса
    delete_cache("home:html")
    try:
        for key in redis_client.scan_iter("games:*"):
            redis_client.delete(key)
    except Exception:
        pass
    click.echo("✓ Демо-стенд сброшен")
