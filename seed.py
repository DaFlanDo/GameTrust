"""Демо-данные: игры, продавцы, лоты, заказы, отзывы и переписка.

Запуск: `flask seed`. Если в базе уже есть пользователи, ничего не делает.
"""
import os
import random
import shutil
from datetime import datetime, timedelta

import click
from flask import current_app
from werkzeug.security import generate_password_hash

import escrow
from extensions import db, fernet
from models import Game, Lot, Message, Review, Transaction, User

DEMO_DIR = os.path.join(os.path.dirname(__file__), "demo")
DEMO_PASSWORD = "demo12345"

GAMES = [
    ("cs2", "Counter-Strike 2"), ("dota2", "Dota 2"), ("genshin", "Genshin Impact"),
    ("valorant", "Valorant"), ("minecraft", "Minecraft"), ("gta5", "GTA V"),
    ("fortnite", "Fortnite"), ("rust", "Rust"),
]

SELLERS = ["NightMarket", "KeyForge", "ProBoost", "PixelTrader"]

# (игра, категория, платформа, название, цена, количество, автовыдача)
LOTS = [
    ("cs2", "Keys", "PC", "Ключ CS2 Prime Status Upgrade", 1290, 5, True),
    ("cs2", "Accounts", "PC", "Аккаунт CS2 Prime, 1200 часов, медаль 2023", 3400, 1, False),
    ("cs2", "Services", "PC", "Калибровка Premier до 15 000 рейтинга", 2500, 3, False),
    ("dota2", "Accounts", "PC", "Аккаунт Dota 2, 4500 MMR, без банов", 4200, 1, False),
    ("dota2", "Services", "PC", "Буст MMR +500 за 3 дня", 1800, 4, False),
    ("dota2", "Currency", "PC", "Battle Pass уровень 100", 2100, 2, False),
    ("genshin", "Currency", "Mobile", "6480 Кристаллов сотворения", 7490, 10, False),
    ("genshin", "Accounts", "PC", "AR 58, 6 персонажей 5★, Райдэн C2", 5600, 1, False),
    ("genshin", "Currency", "Mobile", "Благословение полой луны, 30 дней", 390, 20, True),
    ("valorant", "Currency", "PC", "Valorant Points 1000 VP", 790, 15, True),
    ("valorant", "Accounts", "PC", "Аккаунт Immortal 2, 12 скинов ножей", 9900, 1, False),
    ("valorant", "Services", "PC", "Тренировка аима с тренером, 2 часа", 1500, 5, False),
    ("minecraft", "Keys", "PC", "Minecraft Java & Bedrock Edition, ключ", 1990, 8, True),
    ("minecraft", "Services", "PC", "Постройка замка на вашем сервере", 3000, 2, False),
    ("gta5", "Keys", "PC", "GTA V Premium Edition (Rockstar Games)", 1490, 6, True),
    ("gta5", "Currency", "PC", "GTA Online: $50 000 000 + 120 уровень", 2700, 3, False),
    ("gta5", "Keys", "PlayStation", "GTA V для PS5, цифровой код", 2290, 4, True),
    ("fortnite", "Currency", "PC", "2800 V-Bucks", 1590, 12, True),
    ("fortnite", "Accounts", "Xbox", "Аккаунт с 80 скинами, Чёрный рыцарь", 6500, 1, False),
    ("rust", "Keys", "PC", "Rust, ключ Steam", 1390, 7, True),
    ("rust", "Services", "PC", "Помощь в рейде, 1 вайп", 900, 5, False),
]

REVIEWS = [
    (5, "Ключ пришёл сразу, активировал без проблем."),
    (5, "Быстро и вежливо, рекомендую продавца."),
    (4, "Всё ок, но ответил не сразу."),
    (5, "Уже третья покупка у этого продавца, всё чётко."),
    (5, "Аккаунт как в описании, почту сменил за минуту."),
]


def _fake_key():
    return "-".join("".join(random.choices("ABCDEFGHJKLMNPQRSTUVWXYZ23456789", k=5)) for _ in range(3))


def _copy_demo_images():
    upload = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(os.path.join(upload, "games"), exist_ok=True)
    for slug, _ in GAMES:
        shutil.copy(os.path.join(DEMO_DIR, "games", f"{slug}.jpg"), os.path.join(upload, "games", f"{slug}.jpg"))
        shutil.copy(os.path.join(DEMO_DIR, "lots", f"{slug}.jpg"), os.path.join(upload, f"demo_{slug}.jpg"))


def _user(username, email, days_ago, is_admin=False):
    user = User(username=username, email=email, password=generate_password_hash(DEMO_PASSWORD),
                is_admin=is_admin, is_confirmed=True, balance=0, hold_balance=0,
                created_at=datetime.utcnow() - timedelta(days=days_ago))
    db.session.add(user)
    return user


def _deposit(user, amount):
    user.balance += amount
    db.session.add(Transaction(user_id=user.id, amount=amount, type="deposit", status="completed",
                               description="Пополнение баланса картой"))


def seed():
    random.seed(42)
    _copy_demo_images()

    admin = _user("admin", "admin@example.com", 400, is_admin=True)
    demo = _user("demo", "demo@example.com", 5)
    sellers = [_user(name, f"{name.lower()}@example.com", days)
               for name, days in zip(SELLERS, [900, 640, 410, 75])]
    buyers = [_user(name, f"{name.lower()}@example.com", days)
              for name, days in [("Artem_K", 6), ("frostbyte", 4), ("lina.play", 2)]]
    db.session.flush()

    games = {}
    for slug, name in GAMES:
        games[slug] = Game(name=name, category="Keys", image=f"{slug}.jpg")
        db.session.add(games[slug])
    db.session.flush()

    lots = []
    for i, (slug, category, platform, title, price, quantity, auto) in enumerate(LOTS):
        keys = [_fake_key() for _ in range(quantity)] if auto else None
        lot = Lot(title=title, category=category, platform=platform, price=price, quantity=quantity,
                  description=f"{title}. Передача через чат сделки, гарантия до подтверждения получения.",
                  autodelivery=auto,
                  autodelivery_data=fernet.encrypt("\n".join(keys).encode()).decode() if keys else None,
                  image_filenames=f'["demo_{slug}.jpg"]', user_id=sellers[i % len(sellers)].id,
                  game_id=games[slug].id, created_at=datetime.utcnow() - timedelta(days=i % 7, hours=i))
        db.session.add(lot)
        lots.append(lot)

    for user in [demo, *buyers]:
        _deposit(user, 30000)
    db.session.commit()

    # Завершённые сделки с отзывами — у продавцов появляется рейтинг
    for n, (buyer, lot_index) in enumerate([(buyers[0], 0), (buyers[1], 9), (buyers[2], 17),
                                            (buyers[0], 14), (demo, 12)]):
        purchase = escrow.buy_lot(buyer, lots[lot_index].public_id)
        escrow.complete_purchase(purchase)
        rating, comment = REVIEWS[n]
        db.session.add(Review(purchase_id=purchase.id, reviewer_id=buyer.id, seller_id=purchase.seller_id,
                              rating=rating, comment=comment))
        purchase.is_reviewed = True
        # Сделки разнесены по неделе, чтобы на графиках админки было что показать
        purchase.created_at = datetime.utcnow() - timedelta(days=5 - n)
        db.session.commit()

    # Заказ demo, который ждёт подтверждения: деньги у продавца на удержании
    pending = escrow.buy_lot(demo, lots[9].public_id)
    seller = db.session.get(User, pending.seller_id)
    for sender, receiver, text in [
        (demo, seller, "Привет! Код пришёл, но пишет, что регион не тот. Можно проверить?"),
        (seller, demo, "Привет, сейчас гляну. Какой регион стоит в аккаунте?"),
        (demo, seller, "Европа"),
        (seller, demo, "Да, этот код как раз для Европы. Попробуй активировать через сайт, а не клиент."),
    ]:
        db.session.add(Message(sender_id=sender.id, receiver_id=receiver.id, content=text, is_read=True))
    db.session.commit()
    return admin


@click.command("seed")
def seed_command():
    """Заполнить пустую базу демо-данными."""
    if User.query.first() is not None:
        click.echo("В базе уже есть пользователи, демо-данные не добавлены.")
        return
    seed()
    click.echo(f"Готово. Вход: demo@example.com / {DEMO_PASSWORD}, "
               f"админ: admin@example.com / {DEMO_PASSWORD}")
