from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_required, current_user

import escrow
from extensions import db
from models import Transaction, Lot

finance_bp = Blueprint('finance', __name__, url_prefix='/finance')


# ───────── Дашборд ─────────
@finance_bp.route('/')
@login_required
def dashboard():
    transactions = (Transaction.query
                    .filter_by(user_id=current_user.id)
                    .order_by(Transaction.created_at.desc())
                    .all())
    return render_template('finance/finance.html', transactions=transactions)


def _create_topup(amount, description):
    tx = Transaction(user_id=current_user.id, amount=amount, type='topup',
                     description=description, status='pending')
    db.session.add(tx)
    db.session.commit()
    return redirect(url_for('finance.fake_payment', transaction_id=tx.id))


# ───────── Пополнение через имитацию оплаты ─────────
@finance_bp.route('/topup/init', methods=['POST'])
@login_required
def init_topup():
    try:
        amount = escrow.parse_amount(request.form.get('amount'))
    except escrow.EscrowError as e:
        flash(str(e), 'error')
        return redirect(url_for('finance.dashboard'))
    method = request.form.get('method', 'карту')[:30]
    return _create_topup(amount, f'Пополнение через {method}')


@finance_bp.route("/topup/shortage")
@login_required
def topup_shortage():
    """Пополнение ровно на недостающую сумму, после оплаты покупка завершится сама."""
    try:
        amount = max(escrow.parse_amount(request.args.get("amount"), minimum=1), escrow.MIN_AMOUNT)
    except escrow.EscrowError as e:
        flash(str(e), 'error')
        return redirect(url_for('finance.dashboard'))

    lot_public_id = session.get("pending_lot_public_id")
    lot = Lot.query.filter_by(public_id=lot_public_id).first() if lot_public_id else None
    description = f"Пополнение для покупки «{lot.title}»" if lot else "Пополнение для покупки"
    return _create_topup(amount, description)


# ───────── Вывод ─────────
@finance_bp.route('/withdraw', methods=['POST'])
@login_required
def withdraw_page():
    details = request.form.get('details', '').strip()[:100]
    try:
        escrow.request_withdrawal(current_user, request.form.get('amount'), details)
    except escrow.EscrowError as e:
        flash(str(e), 'error')
        return redirect(url_for('finance.dashboard'))

    flash('Запрос на вывод отправлен', 'success')
    return redirect(url_for('finance.dashboard'))


@finance_bp.route('/withdraw/cancel/<int:transaction_id>', methods=['POST'])
@login_required
def cancel_withdraw(transaction_id):
    try:
        escrow.cancel_withdrawal(current_user, transaction_id)
    except escrow.EscrowError as e:
        flash(str(e), 'error')
        return redirect(url_for('finance.dashboard'))

    flash('Запрос на вывод отменён, средства возвращены на баланс', 'success')
    return redirect(url_for('finance.dashboard'))


# ───────── Имитация оплаты ─────────
@finance_bp.route('/topup/pay/<int:transaction_id>')
@login_required
def fake_payment(transaction_id):
    tx = Transaction.query.filter_by(id=transaction_id, user_id=current_user.id, type='topup').first_or_404()
    if tx.status != 'pending':
        flash('Эта транзакция уже закрыта', 'info')
        return redirect(url_for('finance.dashboard'))
    return render_template('finance/payment.html', transaction=tx)


@finance_bp.route('/topup/pay/<int:transaction_id>/cancel', methods=['POST'])
@login_required
def cancel_payment(transaction_id):
    tx = Transaction.query.filter_by(id=transaction_id, user_id=current_user.id,
                                     type='topup', status='pending').first_or_404()
    tx.status = 'cancelled'
    db.session.commit()
    session.pop('pending_lot_public_id', None)
    flash('Платёж отменён', 'info')
    return redirect(url_for('finance.dashboard'))


@finance_bp.route('/topup/pay/<int:transaction_id>/confirm', methods=['POST'])
@login_required
def confirm_payment(transaction_id):
    try:
        escrow.confirm_topup(current_user, transaction_id)
    except escrow.EscrowError:
        flash('Платёж не найден или уже обработан', 'error')
        return redirect(url_for('finance.dashboard'))

    # Если пополняли ради покупки — сразу её завершаем
    lot_public_id = session.pop('pending_lot_public_id', None)
    if lot_public_id:
        try:
            purchase = escrow.buy_lot(current_user, lot_public_id)
        except escrow.EscrowError as e:
            flash(f'Баланс пополнен, но покупка не прошла: {e}', 'warning')
            return redirect(url_for('finance.dashboard'))
        flash('Баланс пополнен, покупка оформлена!', 'success')
        return redirect(url_for('purchase.checkout', public_id=purchase.public_id))

    flash('Баланс пополнен!', 'success')
    return redirect(url_for('finance.dashboard'))
