"""Движение денег: покупка, удержание у продавца, подтверждение, возврат, вывод.

Баланс меняется только через UPDATE ... WHERE balance >= сумма: две одновременные
покупки не уведут баланс в минус, даже если обе прочитали его до списания.
"""
from markupsafe import escape
from sqlalchemy import select, update

from extensions import db, fernet
from media import category_label
from models import Lot, Message, Purchase, Transaction, User

MIN_AMOUNT = 10
MAX_AMOUNT = 1_000_000


class EscrowError(Exception):
    pass


class InsufficientFunds(EscrowError):
    def __init__(self, shortage):
        super().__init__(f"Не хватает {shortage} ₽")
        self.shortage = shortage


def parse_amount(raw, minimum=MIN_AMOUNT):
    """Сумма из формы: целое число в разумных пределах, иначе EscrowError."""
    try:
        amount = int(raw)
    except (TypeError, ValueError):
        raise EscrowError("Некорректная сумма")
    if not minimum <= amount <= MAX_AMOUNT:
        raise EscrowError(f"Сумма должна быть от {minimum} до {MAX_AMOUNT} ₽")
    return amount


def _change_balance(user_id, delta, field="balance"):
    """Атомарно меняет баланс. Списание с balance не проходит, если денег меньше, чем нужно."""
    column = getattr(User, field)
    stmt = update(User).where(User.id == user_id).values({field: column + delta})
    if delta < 0 and field == "balance":
        stmt = stmt.where(column >= -delta)
    return db.session.execute(stmt.execution_options(synchronize_session=False)).rowcount == 1


def _refresh(*users):
    for user in users:
        if user is not None and user in db.session:
            db.session.refresh(user)


def _take_delivery_item(lot):
    """Забирает первую строку из зашифрованных данных автовыдачи."""
    if not (lot.autodelivery and lot.autodelivery_data):
        return None
    try:
        lines = [l.strip() for l in fernet.decrypt(lot.autodelivery_data.encode()).decode().splitlines() if l.strip()]
    except Exception:
        lot.autodelivery = False
        return None
    if not lines:
        lot.autodelivery = False
        return None
    item = lines.pop(0)
    lot.autodelivery_data = fernet.encrypt("\n".join(lines).encode()).decode()
    return item


def buy_lot(buyer, lot_public_id):
    """Списывает деньги у покупателя и держит их у продавца до подтверждения получения."""
    lot = Lot.query.filter_by(public_id=lot_public_id).with_for_update().first()
    if lot is None or not lot.is_active or lot.quantity <= 0:
        raise EscrowError("Товар недоступен для покупки")
    if lot.user_id == buyer.id:
        raise EscrowError("Нельзя купить собственный лот")

    if not _change_balance(buyer.id, -lot.price):
        db.session.rollback()
        balance = db.session.scalar(select(User.balance).where(User.id == buyer.id))
        raise InsufficientFunds(lot.price - balance)
    _change_balance(lot.user_id, lot.price, field="hold_balance")

    delivery_text = _take_delivery_item(lot)
    lot.quantity -= 1
    if lot.quantity <= 0:
        lot.is_active = False

    purchase = Purchase(
        user_id=buyer.id,
        lot_id=lot.id,
        lot_title=lot.title,
        lot_description=lot.description,
        lot_category=lot.category,
        lot_platform=lot.platform,
        lot_price=lot.price,
        seller_username=lot.user.username if lot.user else "Неизвестно",
        seller_id=lot.user_id,
        delivery_data=fernet.encrypt(delivery_text.encode()).decode() if delivery_text else None,
        status="paid",
    )
    db.session.add(purchase)
    db.session.flush()

    db.session.add(Transaction(user_id=buyer.id, amount=-lot.price, type="purchase", status="completed",
                               description=f"Покупка «{lot.title}» (заказ {purchase.public_id})"))
    db.session.add(Message(
        sender_id=lot.user_id,
        receiver_id=buyer.id,
        is_system=True,
        # В системном сообщении разрешён HTML, поэтому всё, что ввёл пользователь, экранируем
        content=(
            "<b>✅ Покупка оформлена!</b><br>"
            f"<b>🎮 Товар:</b> {escape(lot.title)}<br>"
            f"<b>📂 Категория:</b> {escape(category_label(lot.category))} • {escape(lot.platform)}<br>"
            f"<b>💰 Цена:</b> {lot.price} ₽<br>"
            f"<a href='/purchase/order/{purchase.public_id}' "
            "style='color:#90cdf4;text-decoration:underline;'>🔗 Перейти к заказу</a>"
        ),
    ))
    db.session.commit()
    _refresh(buyer)
    return purchase


def complete_purchase(purchase):
    """Покупатель (или админ) подтвердил получение: деньги из удержания переходят продавцу."""
    if purchase.status != "paid":
        raise EscrowError("Этот заказ нельзя подтвердить")
    _change_balance(purchase.seller_id, -purchase.lot_price, field="hold_balance")
    _change_balance(purchase.seller_id, purchase.lot_price)
    purchase.status = "completed"
    purchase.is_confirmed = True
    db.session.add(Transaction(user_id=purchase.seller_id, amount=purchase.lot_price, type="sale",
                               status="completed", description=f"Продажа «{purchase.lot_title}» (заказ {purchase.public_id})"))
    db.session.commit()


def refund_purchase(purchase):
    """Возврат покупателю. Деньги забираются из удержания или с баланса продавца."""
    if purchase.status == "paid":
        _change_balance(purchase.seller_id, -purchase.lot_price, field="hold_balance")
    elif purchase.status == "completed":
        # Продавец мог уже вывести деньги — тогда баланс уходит в минус, это видно в админке
        db.session.execute(update(User).where(User.id == purchase.seller_id)
                           .values(balance=User.balance - purchase.lot_price))
        db.session.add(Transaction(user_id=purchase.seller_id, amount=-purchase.lot_price, type="refund",
                                   status="completed", description=f"Возврат покупателю, заказ {purchase.public_id}"))
    else:
        raise EscrowError("Этот заказ нельзя вернуть")

    _change_balance(purchase.user_id, purchase.lot_price)
    db.session.add(Transaction(user_id=purchase.user_id, amount=purchase.lot_price, type="refund",
                               status="completed", description=f"Возврат за заказ {purchase.public_id}"))
    purchase.status = "refunded"
    purchase.is_confirmed = False
    db.session.commit()


def request_withdrawal(user, raw_amount, details):
    amount = parse_amount(raw_amount, minimum=1)
    if not _change_balance(user.id, -amount):
        db.session.rollback()
        raise EscrowError("Недостаточно средств для вывода")
    _change_balance(user.id, amount, field="hold_balance")
    db.session.add(Transaction(user_id=user.id, amount=-amount, type="withdrawal", status="pending",
                               description=f"Запрос вывода на {details}"))
    db.session.commit()
    _refresh(user)


def cancel_withdrawal(user, transaction_id):
    tx = Transaction.query.filter_by(id=transaction_id, user_id=user.id, type="withdrawal",
                                     status="pending").with_for_update().first()
    if tx is None:
        raise EscrowError("Невозможно отменить эту операцию")
    _change_balance(user.id, -abs(tx.amount), field="hold_balance")
    _change_balance(user.id, abs(tx.amount))
    tx.status = "cancelled"
    db.session.commit()
    _refresh(user)


def confirm_topup(user, transaction_id):
    """Имитация успешной оплаты: зачисляет только ожидающее пополнение этого пользователя."""
    tx = Transaction.query.filter_by(id=transaction_id, user_id=user.id, type="topup",
                                     status="pending").with_for_update().first()
    if tx is None:
        raise EscrowError("Платёж не найден или уже обработан")
    _change_balance(user.id, tx.amount)
    tx.status = "completed"
    db.session.commit()
    _refresh(user)
    return tx
