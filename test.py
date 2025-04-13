from werkzeug.security import generate_password_hash
from datetime import datetime
from app import app
from extensions import db
from models import Game, User, Lot

with app.app_context():
    # Очистка базы
    db.drop_all()
    db.create_all()

    # Добавим игры с английскими категориями
    games = [
        Game(name="GTA V", category="Keys"),
        Game(name="CS:GO Prime", category="Accounts"),
        Game(name="FIFA 23 Coins", category="Currency"),
        Game(name="Boosting Valorant", category="Services"),
    ]
    db.session.bulk_save_objects(games)
    db.session.commit()

    # Добавим тестового пользователя
    test_user = User(
        username="testuser",
        email="test@example.com",
        password=generate_password_hash("123456"),
        avatar="default.png",
        created_at=datetime(2022, 1, 1)
    )
    db.session.add(test_user)
    db.session.commit()

    # Добавим лоты от testuser
    lots = [
        Lot(
            title="GTA V Social Club",
            description="Ключ активации GTA V в Social Club",
            price=599,
            platform="PC",
            category="Keys",
            is_active=True,
            autodelivery=True,
            game_id=games[0].id,
            user_id=test_user.id
        ),
        Lot(
            title="CS:GO Prime аккаунт",
            description="Прайм аккаунт, идеально подходит для соревновательных игр",
            price=399,
            platform="PC",
            category="Accounts",
            is_active=True,
            autodelivery=False,
            game_id=games[1].id,
            user_id=test_user.id
        ),
        Lot(
            title="100K FIFA 23 Coins",
            description="Быстрая доставка на платформу PS5",
            price=200,
            platform="PlayStation",
            category="Currency",
            is_active=True,
            autodelivery=True,
            game_id=games[2].id,
            user_id=test_user.id
        ),
        Lot(
            title="Boost до Gold в Valorant",
            description="Поднятие рейтинга до Gold 1 с гарантией!",
            price=1500,
            platform="PC",
            category="Services",
            is_active=True,
            autodelivery=False,
            game_id=games[3].id,
            user_id=test_user.id
        ),
    ]
    db.session.bulk_save_objects(lots)
    db.session.commit()

    print("✅ База данных успешно заполнена!")