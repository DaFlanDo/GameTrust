import random
from datetime import datetime
from faker import Faker

from app import app
from extensions import db, fernet
from models import Lot

fake = Faker('ru_RU')

categories = ['Keys', 'Accounts', 'Services']
platforms = ['PC', 'PlayStation', 'Xbox']
games = ['GTA 5', 'FIFA 24', 'CS2', 'Minecraft', 'Fortnite', 'Valorant', 'Rust']

def generate_fake_lot(user_id=1, game_id=1):
    title = f"{random.choice(games)} {random.randint(1, 999)}"
    category = random.choice(categories)
    platform = random.choice(platforms)
    description = fake.paragraph(nb_sentences=3)
    price = random.randint(100, 9999)
    autodelivery = random.choice([True, False])
    quantity = random.randint(1, 10)
    is_active = random.choice([True, True, True, False])

    # Пример зашифрованных данных
    autodelivery_data = fernet.encrypt(fake.text(max_nb_chars=30).encode()).decode() if autodelivery else None

    # Массив изображений (JSON-строка)
    images = [f"{fake.uuid4()[:8]}.jpg" for _ in range(random.randint(0, 3))]
    image_filenames = str(images) if images else None

    return Lot(
        title=title,
        category=category,
        platform=platform,
        description=description,
        price=price,
        quantity=quantity,
        autodelivery=autodelivery,
        autodelivery_data=autodelivery_data,
        image_filenames=image_filenames,
        created_at=datetime.utcnow(),
        user_id=user_id,
        game_id=game_id,
        is_active=is_active
    )


with app.app_context():
    db.create_all()
    fake_lots = [generate_fake_lot(user_id=1, game_id=random.randint(1, 4)) for _ in range(500)]
    db.session.add_all(fake_lots)
    db.session.commit()
    print("✅ Сгенерировано и добавлено 15 лотов.")