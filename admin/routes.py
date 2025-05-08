from collections import defaultdict
from datetime import datetime, timedelta
from functools import wraps

from flask import render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload

from . import admin_bp


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            return redirect(url_for('lot.home'))  # или 'main.index', если используешь main_bp
        return f(*args, **kwargs)
    return decorated_function

from flask import render_template
from flask_login import login_required
from . import admin_bp
from models import User, Lot, Purchase, Review, Message, Transaction
from extensions import db, delete_cache
from sqlalchemy import func


@admin_bp.route('/admin')
@login_required
@admin_required
def dashboard():
    user_count = User.query.count()
    lot_count = Lot.query.count()
    purchase_count = Purchase.query.count()
    review_count = Review.query.count()
    message_count = Message.query.filter_by(is_read=False).count()
    total_balance = db.session.query(db.func.sum(User.balance)).scalar() or 0

    # Сбор статистики по дням
    last_days = [(datetime.utcnow() - timedelta(days=i)).date() for i in reversed(range(7))]
    day_strs = [d.strftime('%d.%m') for d in last_days]

    daily_users = defaultdict(int)
    users = User.query.filter(User.created_at >= datetime.utcnow() - timedelta(days=7)).all()
    for user in users:
        date_key = user.created_at.date()
        daily_users[date_key] += 1

    chart_labels = day_strs
    chart_data = [daily_users.get(day, 0) for day in last_days]
    # Добавь в dashboard() перед return:

    chart_labels = [d.strftime('%d.%m') for d in last_days]

    users_per_day = [User.query.filter(db.func.date(User.created_at) == day).count() for day in last_days]
    lots_per_day = [Lot.query.filter(db.func.date(Lot.created_at) == day).count() for day in last_days]
    purchases_per_day = [Purchase.query.filter(db.func.date(Purchase.created_at) == day).count() for day in last_days]

    # Пример: доход = сумма lot_price по дням
    income_per_day = [
        db.session.query(db.func.sum(Purchase.lot_price))
        .filter(db.func.date(Purchase.created_at) == day)
        .scalar() or 0 for day in last_days
    ]

    messages_per_day = [Message.query.filter(db.func.date(Message.created_at) == day).count() for day in last_days]

    # Добавь в render_template:

    return render_template('admin/dashboard.html',
                           user_count=user_count,
                           lot_count=lot_count,
                           purchase_count=purchase_count,
                           review_count=review_count,
                           message_count=message_count,
                           total_balance=total_balance,
                           chart_labels=chart_labels,
                           users_per_day=users_per_day,
                           lots_per_day=lots_per_day,
                           purchases_per_day=purchases_per_day,
                           income_per_day=income_per_day,
                           messages_per_day=messages_per_day
                           )

@admin_bp.route('/admin/users')
@login_required
@admin_required
def users():
    query = request.args.get('q', '')
    users_query = User.query

    if query:
        users_query = users_query.filter(
            db.or_(
                User.username.ilike(f'%{query}%'),
                User.email.ilike(f'%{query}%')
            )
        )

    users = users_query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=users, search=query)

# Просмотр и редактирование пользователя
@admin_bp.route('/admin/users/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)

    action = request.args.get('action')

    # 💡 ВАЖНО: если есть action — обработать и выйти
    if action == 'toggle_block':
        user.is_blocked = not user.is_blocked
        if user.is_blocked:
            user.block_reason = request.form.get('block_reason', 'Не указана')
        else:
            user.block_reason = None
        db.session.commit()
        flash(f"Пользователь {'заблокирован' if user.is_blocked else 'разблокирован'}", 'info')
        return redirect(url_for('admin.edit_user', user_id=user.id))

    if action == 'delete':
        db.session.delete(user)
        db.session.commit()
        flash('Пользователь удалён', 'success')
        return redirect(url_for('admin.users'))

    # POST-запрос (обновление баланса)
    if request.method == 'POST':
        user.balance = int(request.form.get('balance', user.balance))
        user.hold_balance = int(request.form.get('hold_balance', user.hold_balance))
        db.session.commit()
        flash('Баланс обновлён', 'success')
        return redirect(url_for('admin.edit_user', user_id=user.id))

    # Отображение
    purchases = Purchase.query.filter_by(user_id=user.id).all()
    lots = Lot.query.filter_by(user_id=user.id).all()
    transactions = Transaction.query.filter_by(user_id=user.id).all()
    sales = Purchase.query.filter_by(seller_id=user.id).all()
    sales_by_lot = {
        lot.id: Purchase.query.filter_by(lot_id=lot.id).count() for lot in lots
    }

    return render_template('admin/user_edit.html',
                           user=user,
                           purchases=purchases,
                           lots=lots,
                           transactions=transactions,
                           sales=sales,
                           sales_by_lot=sales_by_lot)


@admin_bp.route('/admin/lots')
@login_required
@admin_required
def manage_lots():
    query = request.args.get('q', '')
    lots_query = Lot.query

    if query:
        lots_query = lots_query.filter(Lot.title.ilike(f'%{query}%'))

    lots = lots_query.order_by(Lot.created_at.desc()).all()

    return render_template('admin/lots.html', lots=lots, search=query)

@admin_bp.route('/admin/lots/<int:lot_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_lot(lot_id):
    lot = Lot.query.get_or_404(lot_id)
    lot.is_active = not lot.is_active
    db.session.commit()
    flash(f"Лот {'включен' if lot.is_active else 'отключён'}", 'info')
    return redirect(url_for('admin.manage_lots'))

@admin_bp.route('/admin/lots/<int:lot_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_lot(lot_id):
    lot = Lot.query.get_or_404(lot_id)
    db.session.delete(lot)
    db.session.commit()
    flash('Лот удалён', 'success')
    return redirect(url_for('admin.manage_lots'))

@admin_bp.route('/admin/games', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_games():
    from models import Game

    categories = ['Аккаунт', 'Ключ', 'Валюта', 'Услуги']

    if request.method == 'POST':
        name = request.form.get('name')
        # Отображение для интерфейса
        category_map = {
            "Аккаунт": "Accounts",
            "Ключ": "Keys",
            "Валюта": "Currency",
            "Услуги": "Services"
        }

        # Получаем из формы и переводим
        category_ui = request.form.get('category')
        category = category_map.get(category_ui)
        if name and category:
            game = Game(name=name, category=category)
            db.session.add(game)
            db.session.commit()
            delete_cache(f"games:category:{category}", "games:list")

            flash('Игра добавлена', 'success')
            return redirect(url_for('admin.manage_games'))

    games = Game.query.order_by(Game.category, Game.name).all()
    return render_template('admin/games.html', games=games, categories=categories)

@admin_bp.route('/admin/games/<int:game_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_game(game_id):
    from models import Game

    game = Game.query.get_or_404(game_id)
    db.session.delete(game)
    db.session.commit()
    flash('Игра удалена', 'success')
    return redirect(url_for('admin.manage_games'))


@admin_bp.route('/admin/chats')
@login_required
@admin_required
def chat_list():
    from models import Message, User

    # Получим все уникальные пары sender/receiver (без дублей в обе стороны)
    messages = Message.query.all()
    chat_pairs = set()

    for msg in messages:
        pair = tuple(sorted([msg.sender_id, msg.receiver_id]))
        chat_pairs.add(pair)

    chats = []
    for uid1, uid2 in chat_pairs:
        user1 = User.query.get(uid1)
        user2 = User.query.get(uid2)
        if user1 and user2:
            chats.append((user1, user2))
    return render_template('admin/chat_list.html', chats=chats)

@admin_bp.route('/admin/chats/<int:user1_id>/<int:user2_id>')
@login_required
@admin_required
def view_chat(user1_id, user2_id):
    from models import Message, User

    messages = Message.query.filter(
        db.or_(
            db.and_(Message.sender_id == user1_id, Message.receiver_id == user2_id),
            db.and_(Message.sender_id == user2_id, Message.receiver_id == user1_id)
        )
    ).order_by(Message.created_at).all()

    user1 = User.query.get_or_404(user1_id)
    user2 = User.query.get_or_404(user2_id)

    return render_template('admin/chat_view.html', messages=messages, user1=user1, user2=user2)

@admin_bp.route('/admin/orders')
@login_required
@admin_required
def manage_orders():
    from models import Purchase, User

    purchases = Purchase.query.order_by(Purchase.created_at.desc()).all()
    return render_template('admin/orders.html', purchases=purchases)
@admin_bp.route('/admin/orders/<int:order_id>/confirm', methods=['POST'])
@login_required
@admin_required
def confirm_order(order_id):
    order = Purchase.query.get_or_404(order_id)

    if not order.is_confirmed:
        order.is_confirmed = True
        order.status = 'completed'
        # перевести деньги продавцу
        seller = User.query.get(order.seller_id)
        if seller:
            seller.balance += order.lot_price
        db.session.commit()

    flash('Заказ подтверждён и оплачен продавцу.', 'success')
    return redirect(url_for('admin.manage_orders'))

@admin_bp.route('/admin/orders/<int:order_id>/refund', methods=['POST'])
@login_required
@admin_required
def refund_order(order_id):
    order = Purchase.query.get_or_404(order_id)

    if order.status == 'refunded':
        flash('Заказ уже был возвращён.', 'warning')
        return redirect(url_for('admin.manage_orders'))

    # Изменяем статус заказа
    order.status = 'refunded'
    order.is_confirmed = False

    # Получаем пользователя и продавца
    user = User.query.get(order.user_id)
    seller = User.query.get(order.seller_id)

    # Возвращаем деньги покупателю
    if user:
        user.balance += order.lot_price
        db.session.add(Transaction(
            user_id=user.id,
            amount=order.lot_price,
            type='refund',
            status='completed',
            description=f'Возврат за заказ #{order.id}'
        ))

    # Вычитаем деньги у продавца (если заказ уже был подтверждён)
    if order.is_confirmed and seller:
        seller.balance -= order.lot_price
        db.session.add(Transaction(
            user_id=seller.id,
            amount=-order.lot_price,
            type='refund',
            status='completed',
            description=f'Возврат покупателю за заказ #{order.id}'
        ))

    db.session.commit()
    flash('Средства возвращены покупателю, транзакции добавлены.', 'success')
    return redirect(url_for('admin.manage_orders'))

@admin_bp.route('/admin/reviews/<int:review_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_review(review_id):
    from models import Review, Purchase

    review = Review.query.get_or_404(review_id)

    # Сбросить флаг у заказа
    if review.purchase:
        review.purchase.is_reviewed = False

    db.session.delete(review)
    db.session.commit()
    flash('Отзыв удалён.', 'warning')
    return redirect(url_for('admin.manage_orders'))

@admin_bp.route('/admin/lots/<int:lot_id>')
@login_required
@admin_required
def view_lot(lot_id):
    lot = Lot.query.get_or_404(lot_id)

    # Покупки по лоту
    purchases = Purchase.query.filter_by(lot_id=lot.id).order_by(Purchase.created_at.desc()).all()

    # Отзывы (через покупку)
    reviews = Review.query.join(Purchase).filter(Purchase.lot_id == lot.id).order_by(Review.created_at.desc()).all()

    return render_template(
        'admin/view_lot.html',
        lot=lot,
        purchases=purchases,
        reviews=reviews
    )

@admin_bp.route('/admin/orders/<int:order_id>')
@login_required
@admin_required
def view_order(order_id):
    order  = Purchase.query.get_or_404(order_id)
    buyer  = order.user
    seller = User.query.get(order.seller_id) if order.seller_id else None   # <--

    messages = Message.query.filter(
        db.or_(
            db.and_(Message.sender_id == buyer.id,  Message.receiver_id == seller.id),
            db.and_(Message.sender_id == seller.id, Message.receiver_id == buyer.id)
        )
    ).order_by(Message.created_at).all() if seller else []

    return render_template('admin/order_view.html',
                           order=order, buyer=buyer, seller=seller,
                           messages=messages)