from flask import Blueprint, request, redirect, url_for, flash
from flask_login import login_required, current_user
from extensions import db
from models import Purchase, Review, User

review_bp = Blueprint('review', __name__)

@review_bp.route('/submit-review/<int:purchase_id>', methods=['POST'])
@login_required
def submit_review(purchase_id):
    purchase = Purchase.query.get_or_404(purchase_id)

    # Проверка: это заказ текущего пользователя и он подтверждён
    if purchase.user_id != current_user.id or purchase.status != 'completed':
        flash("Вы не можете оставить отзыв к этому заказу.", "danger")
        return redirect(url_for('purchase.order', purchase_id=purchase.id))

    # Проверка: отзыв уже оставлен
    if purchase.is_reviewed:
        flash("Отзыв уже был оставлен.", "warning")
        return redirect(url_for('purchase.order', purchase_id=purchase.id))

    rating = int(request.form.get('rating', 0))
    comment = request.form.get('comment', '').strip()

    if not (1 <= rating <= 5):
        flash("Оценка должна быть от 1 до 5.", "danger")
        return redirect(url_for('purchase.order', purchase_id=purchase.id))

    # Создание отзыва
    review = Review(
        purchase_id=purchase.id,
        reviewer_id=current_user.id,
        seller_id=purchase.seller_id,
        rating=rating,
        comment=comment
    )
    db.session.add(review)

    # Помечаем покупку как "с отзывом"
    purchase.is_reviewed = True
    db.session.commit()

    flash("Спасибо за ваш отзыв!", "success")
    return redirect(url_for('purchase.order', purchase_id=purchase.id))
@review_bp.route('/edit-review/<int:review_id>', methods=['POST'])
@login_required
def edit_review(review_id):
    review = Review.query.get_or_404(review_id)

    if review.reviewer_id != current_user.id:
        flash("Вы не можете редактировать этот отзыв.", "danger")
        return redirect(url_for('main.index'))

    rating = int(request.form.get('rating', 0))
    comment = request.form.get('comment', '').strip()

    if not (1 <= rating <= 5):
        flash("Оценка должна быть от 1 до 5.", "danger")
        return redirect(url_for('purchase.order', purchase_id=review.purchase_id, edit=1))

    review.rating = rating
    review.comment = comment
    db.session.commit()

    flash("Отзыв обновлён!", "success")
    return redirect(url_for('purchase.order', purchase_id=review.purchase_id))