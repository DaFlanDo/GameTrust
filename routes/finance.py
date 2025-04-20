from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_required, current_user
from extensions import db
from models import Transaction, Lot
from datetime import datetime

finance_bp = Blueprint('finance', __name__, url_prefix='/finance')

# ───────── 1. Дашборд ─────────
@finance_bp.route('/')
@login_required
def dashboard():
    transactions = (Transaction.query
                    .filter_by(user_id=current_user.id)
                    .order_by(Transaction.created_at.desc())
                    .all())
    return render_template('finance.html', transactions=transactions)

# ───────── 2. Пополнение (быстрый вариант, сразу зачисляем) ─────────
@finance_bp.route('/topup', methods=['GET', 'POST'])
@login_required
def topup_page():
    if request.method == 'POST':
        amount = int(request.form.get('amount', 0))
        if amount >= 10:
            current_user.balance += amount
            db.session.add(Transaction(
                user_id=current_user.id,
                amount=amount,
                type='deposit',
                description='Пополнение баланса',
                status='completed',
                created_at=datetime.utcnow()
            ))
            db.session.commit()
            flash('Баланс успешно пополнен!', 'success')
            return redirect(url_for('finance.dashboard'))
        flash('Минимальная сумма пополнения — 10 ₽', 'danger')

    return render_template('finance.html', block='topup')

# ───────── 3. Пополнение через «фейковую» оплату ─────────
@finance_bp.route('/topup/init', methods=['POST'])
@login_required
def init_topup():
    try:
        amount = int(request.form['amount'])
        method = request.form.get('method', 'unknown')
        if amount < 10:
            flash('Минимальная сумма пополнения — 10 ₽', 'error')
            return redirect(url_for('finance.dashboard'))
    except (ValueError, KeyError):
        flash('Некорректные данные', 'error')
        return redirect(url_for('finance.dashboard'))

    tx = Transaction(
        user_id=current_user.id,
        amount=amount,
        type='topup',
        description=f'Пополнение через {method}',
        status='pending'
    )
    db.session.add(tx)
    db.session.commit()

    # Теперь endpoint существует ↓
    return redirect(url_for('finance.fake_payment', transaction_id=tx.id))


# ───────── 4. Запрос на вывод ─────────
@finance_bp.route('/withdraw', methods=['POST'])
@login_required
def withdraw_page():
    try:
        amount = int(request.form['amount'])
    except (ValueError, KeyError):
        flash('Некорректная сумма', 'error')
        return redirect(url_for('finance.dashboard'))

    if amount > current_user.balance:
        flash('Недостаточно средств для вывода', 'error')
        return redirect(url_for('finance.dashboard'))

    details = request.form.get('details', '').strip()

    current_user.balance -= amount
    current_user.hold_balance += amount
    db.session.add(Transaction(
        user_id=current_user.id,
        amount=-amount,
        type='withdrawal',
        description=f'Запрос вывода на {details}',
        status='pending'
    ))
    db.session.commit()

    flash('Запрос на вывод отправлен', 'success')
    return redirect(url_for('finance.dashboard'))

# ───────── 5. Отмена вывода ─────────
@finance_bp.route('/withdraw/cancel/<int:transaction_id>', methods=['POST'])
@login_required
def cancel_withdraw(transaction_id):
    tx = Transaction.query.filter_by(
        id=transaction_id,
        user_id=current_user.id,
        type='withdrawal',
        status='pending'
    ).first()

    if not tx:
        flash('Невозможно отменить эту операцию', 'error')
        return redirect(url_for('finance.dashboard'))

    current_user.balance += abs(tx.amount)
    current_user.hold_balance -= abs(tx.amount)
    tx.status = 'cancelled'
    db.session.commit()

    flash('Запрос на вывод отменён, средства возвращены на баланс', 'success')
    return redirect(url_for('finance.dashboard'))

# ───────── Имитация оплаты ─────────

@finance_bp.route('/topup/pay/<int:transaction_id>')
@login_required
def fake_payment(transaction_id):
    """Страница «Имитация оплаты»."""
    tx = (Transaction.query.filter_by(
            id=transaction_id,
            user_id=current_user.id,
            type='topup')
          .first_or_404())

    # Разрешаем открыть страницу только если платёж ещё не обработан
    if tx.status != 'pending':
        flash('Эта транзакция уже закрыта', 'info')
        return redirect(url_for('finance.dashboard'))

    return render_template('payment.html', transaction=tx)



@finance_bp.route('/topup/pay/<int:transaction_id>/cancel', methods=['POST'])
@login_required
def cancel_payment(transaction_id):
    """Кнопка «❌ Отменить»."""
    tx = Transaction.query.filter_by(
        id=transaction_id,
        user_id=current_user.id,
        type='topup',
        status='pending'
    ).first_or_404()

    tx.status = 'cancelled'
    db.session.commit()

    flash('Платёж отменён', 'info')
    return redirect(url_for('finance.dashboard'))


@finance_bp.route("/topup/shortage")
@login_required
def topup_shortage():
    amount = max(int(request.args.get("amount", 0)), 10)

    # 1. узнаём, какой лот ждёт оплаты
    lot_id = session.get("pending_lot_id")
    lot = Lot.query.get(lot_id) if lot_id else None
    description = (
        f"Оплата лота «{lot.title} »" if lot else "Пополнение для покупки"
    )

    # 2. создаём транзакцию с понятным описанием
    tx = Transaction(
        user_id=current_user.id,
        amount=amount,
        type="topup",     # или 'topup', если так решил
        description=description,       # ← вот оно!
        status="pending",
    )
    db.session.add(tx)
    db.session.commit()

    # 3. на страницу имитации оплаты
    return redirect(url_for("finance.fake_payment", transaction_id=tx.id))


@finance_bp.route('/topup/pay/<int:transaction_id>/confirm', methods=['POST'])
@login_required
def confirm_payment(transaction_id):
    tx = Transaction.query.filter_by(
        id=transaction_id, user_id=current_user.id, status='pending'
    ).first_or_404()

    # зачисляем деньги
    current_user.balance += tx.amount
    tx.status = 'completed'
    db.session.commit()

    # была ли отложенная покупка?
    pending = session.pop('pending_lot_id', None)
    if pending:
        # нужен POST — имитируем через запрос к тому же эндпоинту
        return redirect(url_for('purchase.start_purchase', lot_id=pending))

    flash('Баланс пополнен!', 'success')
    return redirect(url_for('finance.dashboard'))