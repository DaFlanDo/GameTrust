import os
import uuid
from collections import defaultdict
from datetime import datetime

from flask import Blueprint, render_template, url_for, redirect, current_app, request, flash, abort
from flask_login import current_user
from sqlalchemy import func

from extensions import db
from models import User, Lot, Review
from routes.lot import is_allowed

profile_bp = Blueprint('profile', __name__)



@profile_bp.route('/user/<int:user_id>', methods=['GET', 'POST'])
def user_profile(user_id):
    user = db.get_or_404(User, user_id)
    if request.method == 'POST':
        if not current_user.is_authenticated or user.id != current_user.id:
            abort(403)

        new_username = (request.form.get('username') or '').strip()
        if new_username and new_username != user.username:
            if not 3 <= len(new_username) <= 30:
                flash('Имя должно быть от 3 до 30 символов', 'danger')
            elif User.query.filter_by(username=new_username).first():
                flash('Это имя уже занято', 'danger')
            else:
                user.username = new_username

        # Аватар: только картинки и под случайным именем — иначе можно загрузить
        # .html и получить XSS с нашего же домена
        avatar_file = request.files.get('avatar')
        if avatar_file and avatar_file.filename:
            if not is_allowed(avatar_file.filename):
                flash('Аватар должен быть картинкой (png, jpg, webp, gif)', 'danger')
            else:
                ext = avatar_file.filename.rsplit('.', 1)[1].lower()
                filename = f"{uuid.uuid4().hex}.{ext}"
                upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'avatars')
                os.makedirs(upload_dir, exist_ok=True)
                avatar_file.save(os.path.join(upload_dir, filename))
                user.avatar = filename

        db.session.commit()
        return redirect(url_for('profile.user_profile', user_id=user.id))

    # Общая информация
    sales_count = Lot.query.filter_by(user_id=user.id).count()
    years = max((datetime.utcnow() - user.created_at).days // 365, 1)

    lots_by_game = defaultdict(list)
    lots = (
        db.session.query(Lot)
        .filter_by(user_id=user.id)
        .join(Lot.game)
        .options(db.contains_eager(Lot.game))
        .all()
    )

    for lot in lots:
        game_name = lot.game.name if lot.game else 'Без названия'
        lots_by_game[game_name].append(lot)

    reviews = (
        Review.query.filter_by(seller_id=user.id)
        .order_by(Review.created_at.desc())
        .limit(20)
        .all()
    )
    avg_rating = db.session.query(func.avg(Review.rating)).filter(Review.seller_id == user.id).scalar()
    avg_rating = round(avg_rating, 1) if avg_rating else 0.0

    return render_template(
        'user/profile.html',
        user=user,
        years=years,
        sales=sales_count,
        lots_by_game=lots_by_game,
        reviews=reviews,
        avg_rating=avg_rating
    )

