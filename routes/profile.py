import os
from collections import defaultdict

from flask import Blueprint, render_template, url_for, redirect, current_app, request
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from EditProfileForm import EditProfileForm
from extensions import db
from models import User, Lot, Review
from datetime import datetime

profile_bp = Blueprint('profile', __name__)

from collections import defaultdict

from collections import defaultdict
from datetime import datetime
from sqlalchemy import func

@profile_bp.route('/user/<int:user_id>', methods=['GET', 'POST'])
def user_profile(user_id):
    user = User.query.get_or_404(user_id)
    if request.method == 'POST' and user.id == current_user.id:
        # Изменение имени
        new_username = request.form.get('username')
        if new_username and new_username != user.username:
            user.username = new_username.strip()

        # Обработка аватарки
        avatar_file = request.files.get('avatar')
        if avatar_file and avatar_file.filename != '':
            filename = secure_filename(avatar_file.filename)
            avatar_path = os.path.join(current_app.root_path, 'static/uploads/avatars', filename)
            avatar_file.save(avatar_path)
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

