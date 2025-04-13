from flask import Blueprint, redirect, url_for, render_template, flash, current_app, request, abort
from flask_login import login_required, current_user
from threading import Timer
from extensions import db, fernet
from models import Lot, Purchase, Review, Message, User
from datetime import datetime


purchase_bp = Blueprint('purchase', __name__)

@purchase_bp.route('/buy/<int:lot_id>', methods=['POST'])
@login_required
def start_purchase(lot_id):
    lot = Lot.query.get_or_404(lot_id)

    if not lot.is_active or lot.quantity <= 0:
        flash("Товар недоступен для покупки", "danger")
        return redirect(url_for('lot.lot', lot_id=lot.id))

    delivery_data = None
    if lot.autodelivery and lot.autodelivery_data:
        decrypted = fernet.decrypt(lot.autodelivery_data.encode()).decode().splitlines()
        if decrypted:
            delivery_data = decrypted[0]
            remaining = "\n".join(decrypted[1:])
            lot.autodelivery_data = fernet.encrypt(remaining.encode()).decode()

    lot.quantity -= 1
    if lot.quantity <= 0:
        lot.is_active = False

    db.session.commit()

    purchase = Purchase(
        user_id=current_user.id,
        lot_id=lot.id,
        lot_title=lot.title,
        lot_description=lot.description,
        lot_category=lot.category,
        lot_platform=lot.platform,
        lot_price=lot.price,
        seller_username=lot.user.username if lot.user else 'Неизвестно',
        delivery_data=delivery_data,
        seller_id=lot.user_id
    )
    db.session.add(purchase)
    db.session.commit()

    Timer(5, mark_purchase_paid, args=[purchase.id, current_app._get_current_object()]).start()

    return redirect(url_for('purchase.checkout', purchase_id=purchase.id))


def mark_purchase_paid(purchase_id, app):
    with app.app_context():
        purchase = Purchase.query.get(purchase_id)
        if purchase and purchase.status != 'paid':
            purchase.status = 'paid'

            # 💸 Только теперь переводим деньги в холд продавца
            seller = User.query.get(purchase.seller_id)
            if seller:
                seller.hold_balance += purchase.lot_price

            db.session.commit()

            link = url_for('purchase.order', purchase_id=purchase.id, _external=True).replace("localhost", "127.0.0.1")

            system_msg = Message(
                sender_id=purchase.seller_id,
                receiver_id=purchase.user_id,
                content=(
                    f"<b>✅ Покупка завершена!</b><br>"
                    f"<b>🎮 Товар:</b> {purchase.lot_title}<br>"
                    f"<b>📂 Категория:</b> {purchase.lot_category} • {purchase.lot_platform}<br>"
                    f"<b>💰 Цена:</b> {purchase.lot_price} ₽<br>"
                    f"<b>🕒 Время:</b> {purchase.created_at.strftime('%d.%m.%Y %H:%M')}<br>"
                    f"<a href='{link}' style='color:#90cdf4;text-decoration:underline;'>🔗 Перейти к заказу</a>"
                ),
                created_at=datetime.utcnow(),
                is_system=True
            )
            db.session.add(system_msg)
            db.session.commit()

            room = get_room_name(purchase.seller_id, purchase.user_id)
            socketio.emit('receive_message', {
                'sender_id': purchase.seller_id,
                'content': system_msg.content,
                'timestamp': system_msg.created_at.strftime('%d.%m.%Y %H:%M'),
                'is_system': True
            }, room=room)
@purchase_bp.route('/checkout/<int:purchase_id>')
@login_required
def checkout(purchase_id):
    purchase = Purchase.query.get_or_404(purchase_id)
    lot = Lot.query.get(purchase.lot_id)
    if purchase.user_id != current_user.id:
        flash("Это не ваш заказ!", "danger")
        return redirect(url_for('lot.home'))
    return render_template("checkout.html", lot=lot, purchase=purchase)


@purchase_bp.route('/order/<int:purchase_id>')
@login_required
def order(purchase_id):
    purchase = Purchase.query.get_or_404(purchase_id)
    review = Review.query.filter_by(purchase_id=purchase.id).first()
    if purchase.user_id != current_user.id and purchase.seller_id!= current_user.id:
        flash("Это не ваш заказ!", "danger")
        return redirect(url_for('lot.home'))
    lot = Lot.query.get(purchase.lot_id)
    return render_template("order.html", purchase=purchase, lot=lot, review=review)


@purchase_bp.route('/my-orders')
@login_required
def my_orders():
    orders = Purchase.query.filter_by(user_id=current_user.id).order_by(Purchase.created_at.desc()).all()
    return render_template('my_orders.html', orders=orders)


@purchase_bp.route('/confirm-receipt/<int:purchase_id>', methods=['POST'])
@login_required
def confirm_receipt(purchase_id):
    purchase = Purchase.query.get_or_404(purchase_id)

    if purchase.user_id != current_user.id:
        abort(403)

    purchase.status = 'completed'
    db.session.commit()
    link = url_for('purchase.order', purchase_id=purchase.id, _external=True).replace("localhost", "127.0.0.1")

    # ✅ Создаём системное сообщение
    msg = Message(
        sender_id=purchase.user_id,
        receiver_id=purchase.seller_id,
        content=f"✅ Покупатель подтвердил выполнение заказа «{purchase.id}» <br>."
        f"<a href='{link}' "
        f"style='color:#90cdf4;text-decoration:underline;'>🔗 Перейти к заказу</a>",
        is_system=True
    )
    seller = User.query.get(purchase.seller_id)
    if seller and seller.hold_balance >= purchase.lot_price:
        seller.hold_balance -= purchase.lot_price
        seller.balance += purchase.lot_price
    else:
        flash("Ошибка: недостаточно средств в холде для перевода продавцу!", "danger")
        return redirect(url_for('purchase.order', purchase_id=purchase.id))

    db.session.add(msg)
    db.session.commit()

    # 📡 Отправка в WebSocket
    room = get_room_name(purchase.user_id, purchase.seller_id)
    socketio.emit('receive_message', {
        'sender_id': purchase.user_id,
        'content': msg.content,
        'timestamp': msg.created_at.strftime('%d.%m.%Y %H:%M'),
        'is_system': True
    }, room=room)

    flash("Вы подтвердили получение товара!", "success")
    return redirect(url_for('purchase.order', purchase_id=purchase.id))


@purchase_bp.route('/review/<int:purchase_id>', methods=['GET', 'POST'])
@login_required
def leave_review(purchase_id):
    purchase = Purchase.query.get_or_404(purchase_id)
    if purchase.user_id != current_user.id:
        flash("Вы не можете оставить отзыв к этому заказу", "danger")
        return redirect(url_for('purchase.my_orders'))

    if purchase.status != 'completed':
        flash("Вы можете оставить отзыв только после подтверждения получения", "warning")
        return redirect(url_for('purchase.order', purchase_id=purchase.id))

    if request.method == 'POST':
        rating = int(request.form['rating'])
        comment = request.form.get('comment')
        review = Review(
            purchase_id=purchase.id,
            reviewer_id=current_user.id,
            seller_id=purchase.seller_id,
            rating=rating,
            comment=comment
        )
        db.session.add(review)
        db.session.commit()
        flash("Отзыв успешно добавлен!", "success")
        return redirect(url_for('profile.user_profile', user_id=purchase.seller_id))

    return render_template('leave_review.html', purchase=purchase)