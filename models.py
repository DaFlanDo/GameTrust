import json
from datetime import datetime
from flask_login import UserMixin
from extensions import db, generate_short_id


# ──────────────── Пользователь ────────────────
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False, unique=True)
    email = db.Column(db.String(150), nullable=False, unique=True)
    password = db.Column(db.String(200), nullable=False)
    avatar = db.Column(db.String(120), default='default.png')

    balance = db.Column(db.Integer, default=0)
    hold_balance = db.Column(db.Integer, default=0)

    is_admin = db.Column(db.Boolean, default=False)
    is_blocked = db.Column(db.Boolean, default=False)
    block_reason = db.Column(db.String(255), nullable=True)

    is_confirmed = db.Column(db.Boolean, default=False)
    confirmation_token = db.Column(db.String(100), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    is_2fa_enabled = db.Column(db.Boolean, default=False)
    twofa_secret = db.Column(db.String(255), nullable=True)
    twofa_backup_codes = db.Column(db.Text, nullable=True)




# ──────────────── Лот ────────────────
class Lot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(12), unique=True, nullable=False, default=generate_short_id)

    title = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    platform = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=True)
    price = db.Column(db.Integer, nullable=False)
    quantity = db.Column(db.Integer, default=1)

    autodelivery = db.Column(db.Boolean, default=False)
    autodelivery_data = db.Column(db.Text, nullable=True)

    image_filenames = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user = db.relationship('User', backref=db.backref('lots', lazy=True))

    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=True)
    game = db.relationship('Game', backref='lots')
    __tablename__ = 'lot'
    __table_args__ = (
        db.Index('ix_lot_user_id', 'user_id'),
        )
    @property
    def images(self) -> list[str]:
        """Парсит image_filenames как JSON или CSV."""
        if not self.image_filenames:
            return []

        try:
            data = json.loads(self.image_filenames)
            if isinstance(data, list):
                return data
        except ValueError:
            pass

        return [s.strip() for s in self.image_filenames.split(',') if s.strip()]


# ──────────────── Игра ────────────────
class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False)  # Например: "Аккаунты", "Ключи", "Услуги"


# ──────────────── Покупка ────────────────
class Purchase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(12), unique=True, nullable=False, default=generate_short_id)

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    lot_id = db.Column(db.Integer, nullable=True)
    user = db.relationship('User', foreign_keys=[user_id])

    lot_title = db.Column(db.String(150))
    lot_description = db.Column(db.Text)
    lot_category = db.Column(db.String(50))
    lot_platform = db.Column(db.String(50))
    lot_price = db.Column(db.Integer)
    seller_username = db.Column(db.String(100))

    seller_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    delivery_data = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='pending')
    is_confirmed = db.Column(db.Boolean, default=False)
    is_reviewed = db.Column(db.Boolean, default=False)

    review = db.relationship('Review', backref='purchase', uselist=False, cascade="all, delete-orphan")


# ──────────────── Отзыв ────────────────
class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    purchase_id = db.Column(db.Integer, db.ForeignKey('purchase.id'), nullable=False)
    reviewer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    seller_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    reviewer = db.relationship('User', foreign_keys=[reviewer_id])
    seller = db.relationship('User', foreign_keys=[seller_id])


# ──────────────── Сообщения ────────────────
class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)
    is_system = db.Column(db.Boolean, default=False)

    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_messages')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_messages')

    __table_args__ = (
        db.Index('idx_message_users', 'sender_id', 'receiver_id'),
        db.Index('idx_message_created', 'created_at'),
    )


# ──────────────── Транзакции ────────────────
class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(12), unique=True, nullable=False, default=generate_short_id)

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    type = db.Column(db.String(50), nullable=False)  # 'deposit', 'purchase', 'withdrawal', 'refund'
    status = db.Column(db.String(20), default='pending')  # 'pending', 'completed', 'failed'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    description = db.Column(db.Text, nullable=True)