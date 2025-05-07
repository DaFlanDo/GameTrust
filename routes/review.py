from flask import Blueprint, request, redirect, url_for, flash
from flask_login import login_required, current_user
from extensions import db
from models import Purchase, Review, User

review_bp = Blueprint('review', __name__)

@review_bp.route('/submit-review/<string:public_id>', methods=['POST'])
@login_required
def submit_review(public_id):
    purchase = Purchase.query.filter_by(public_id=public_id).first_or_404()

    # Проверка: это заказ текущего пользователя и он подтверждён
    if purchase.user_id != current_user.id or purchase.status != 'completed':
        flash("Вы не можете оставить отзыв к этому заказу.", "danger")
        return redirect(url_for('purchase.order', public_id=purchase.public_id))

    # Проверка: отзыв уже оставлен
    if purchase.is_reviewed:
        flash("Отзыв уже был оставлен.", "warning")
        return redirect(url_for('purchase.order', public_id=purchase.public_id))

    rating = int(request.form.get('rating', 0))
    comment = request.form.get('comment', '').strip()

    if not (1 <= rating <= 5):
        flash("Оценка должна быть от 1 до 5.", "danger")
        return redirect(url_for('purchase.order', public_id=purchase.public_id))

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
    return redirect(url_for('purchase.order', public_id=purchase.public_id))
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
        return redirect(url_for('purchase.order', public_id=review.purchase.public_id))
    review.rating = rating
    review.comment = comment
    db.session.commit()

    flash("Отзыв обновлён!", "success")
    return redirect(url_for('purchase.order', public_id=review.purchase.public_id))