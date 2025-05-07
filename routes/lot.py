import json
import uuid
from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, abort
from flask_login import login_required, current_user
from sqlalchemy import func
from werkzeug.utils import secure_filename
from sqlalchemy.orm import joinedload
import os
from extensions import db, fernet, limiter
from models import Lot, Game, Review, User, Purchase

lot_bp = Blueprint('lot', __name__)

# Главная страница
@lot_bp.route('/')
def home():
    popular_lots = Lot.query.filter_by(is_active=True).order_by(Lot.price.desc()).limit(9).all()
    recent_orders = Purchase.query.order_by(Purchase.created_at.desc()).limit(8).all()
    top_games = Game.query.order_by(Game.name).limit(8).all()
    gallery_images = [url_for('static', filename=f'img/demo/{n}.jpg') for n in range(1, 8)]

    return render_template("index.html",
                           lots=popular_lots,
                           recent_orders=recent_orders,
                           top_games=top_games,
                           gallery_images=gallery_images)

# Подробная страница лота
@lot_bp.route('/lot/<string:public_id>')
def lot(public_id):
    lot = Lot.query.filter_by(public_id=public_id).first_or_404()
    seller = User.query.get_or_404(lot.user_id)

    # Пример: сколько у продавца продаж
    seller_sales = Purchase.query.filter_by(seller_id=seller.id).count()
    years_on_site = max((datetime.utcnow() - seller.created_at).days // 365, 1)

    return render_template(
        'lots/product.html',
        lot=lot,
        user=seller,
        sales=seller_sales,
        years=years_on_site
    )
# Добавление лота - get
@lot_bp.route('/add-lot')
@login_required
def add_lot():
    if not current_user.is_confirmed:
        flash("Для выставления лотов необходимо подтвердить email.", "warning")
        return redirect(url_for('lot.home'))
    games = Game.query.order_by(Game.name).all()
    return render_template('lots/add_lot.html', games=games)






ALLOWED_EXT = {"png", "jpg", "jpeg", "webp", "gif",'heic'}

def is_allowed(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT
# Добавление лота - POST
@lot_bp.route("/submit-lot", methods=["POST"])
@limiter.limit("3 per minute", methods=["POST"])
@login_required
def submit_lot():
    if not current_user.is_confirmed:
        flash("Для выставления лотов необходимо подтвердить email.", "warning")
        return redirect(url_for('auth.unconfirmed'))

        # ───── 1. Собираем поля формы ─────
    title       = request.form["title"]
    category    = request.form["category"]
    platform    = request.form["platform"]
    game_id     = request.form.get("game_id")
    description = request.form.get("description")
    price       = request.form["price"]
    quantity    = int(request.form.get("quantity", 1))
    autodeliv   = "autodelivery" in request.form
    autodata    = request.form.get("autodelivery_data", "")

    # ───── 2. Валидируем автодоставку ─────
    if autodeliv:
        lines = [l.strip() for l in autodata.splitlines() if l.strip()]
        if len(lines) != quantity:
            flash(f"Строк данных ({len(lines)}) ≠ количеству товара ({quantity})", "danger")
            return redirect(url_for("lot.add_lot"))
        plaintext   = "\n".join(lines)
        autodata_enc= fernet.encrypt(plaintext.encode()).decode()
    else:
        autodata_enc = None

    # ───── 3. Сохраняем изображения ─────
    saved_files = []
    for file in request.files.getlist("images[]"):   # ← имя с []!
        if file and file.filename and is_allowed(file.filename):
            ext       = file.filename.rsplit(".", 1)[1].lower()
            unique    = f"{uuid.uuid4().hex}.{ext}"
            filename  = secure_filename(unique)
            path      = os.path.join(current_app.static_folder, "uploads", filename)
            file.save(path)
            saved_files.append(filename)

    # ───── 4. Создаём лот ─────
    new_lot = Lot(
        title             = title,
        category          = category,
        platform          = platform,
        description       = description,
        price             = price,
        quantity          = quantity,
        autodelivery      = autodeliv,
        autodelivery_data = autodata_enc,
        image_filenames   = json.dumps(saved_files),   # ← JSON‑строка
        user_id           = current_user.id,
        game_id           = game_id
    )
    db.session.add(new_lot)
    db.session.commit()

    flash("Лот успешно добавлен!", "success")
    return redirect(url_for("lot.lots_by_game", category=category, game_id=game_id))

# Все лоты по категории
@lot_bp.route('/lots/<category>/<int:game_id>')
def lots(category, game_id):
    game = Game.query.get_or_404(game_id)
    distinct_categories = {g.category for g in Game.query.with_entities(Game.category).distinct()}
    if category not in distinct_categories:
        return render_template('errors/404.html'), 404

    # Читаем GET-параметры
    platform = request.args.get('platform')
    sort = request.args.get('sort')

    # Базовый запрос
    lots_query = (
        Lot.query.options(db.joinedload(Lot.user), db.joinedload(Lot.game))
        .filter_by(category=category, game_id=game_id, is_active=True)
    )
    # Получаем параметры из URL
    platform = request.args.get('platform')
    sort = request.args.get('sort')
    auto = request.args.get('auto') == '1'

    # Базовый запрос
    lots_query = (
        Lot.query.options(db.joinedload(Lot.user), db.joinedload(Lot.game))
        .filter_by(category=category, game_id=game_id, is_active=True)
    )

    # 🔎 Фильтрация по платформе
    if platform in ['PC', 'PlayStation', 'Xbox']:
        lots_query = lots_query.filter(Lot.platform == platform)

    # ⚡ Фильтрация по автодоставке
    if auto:
        lots_query = lots_query.filter(Lot.autodelivery == True)

    # 🔃 Сортировка
    if sort == 'price_asc':
        lots_query = lots_query.order_by(Lot.price.asc())
    elif sort == 'price_desc':
        lots_query = lots_query.order_by(Lot.price.desc())
    elif sort == 'new':
        lots_query = lots_query.order_by(Lot.created_at.desc())
    else:
        lots_query = lots_query.order_by(Lot.id.desc())  # По умолчанию — последние

    page = request.args.get("page", 1, type=int)
    per_page = 20
    pagination = lots_query.paginate(page=page, per_page=per_page, error_out=False)
    lots = pagination.items

    # Все шаги как у тебя
    user_ids = {lot.user_id for lot in lots if lot.user_id is not None}
    rating_data = (
        db.session.query(Review.seller_id, func.avg(Review.rating))
        .filter(Review.seller_id.in_(user_ids))
        .group_by(Review.seller_id)
        .all()
    )
    user_avg_ratings = {
        seller_id: round(avg_rating, 1) for seller_id, avg_rating in rating_data
    }

    users = User.query.filter(User.id.in_(user_ids)).all()
    users_dict = {u.id: u for u in users}

    def years_on_site(user):
        if not user or not user.created_at:
            return 0
        delta_days = (datetime.utcnow() - user.created_at).days
        return delta_days // 365

    enriched_lots = []
    for lot in lots:
        user_obj = users_dict.get(lot.user_id)
        rating = user_avg_ratings.get(lot.user_id, 0.0)
        years = years_on_site(user_obj)
        rating_int = int(rating) if rating <= 5 else 5
        short_desc = lot.description[:80] + '...' if lot.description and len(lot.description) > 80 else lot.description
        avatar_url = url_for('static',
                             filename=f'uploads/avatars/{user_obj.avatar}') if user_obj and user_obj.avatar else url_for(
            'static', filename='avatars/default.png')

        enriched_lots.append({
            'id': lot.id,
            'title': lot.title,
            'public_id': lot.public_id,
            'platform': lot.platform,
            'description': short_desc,
            'autodelivery': lot.autodelivery,
            'price': lot.price,
            'seller': user_obj.username if user_obj else 'Без имени',
            'rating': rating,
            'rating_int': rating_int,
            'game': lot.game,
            'on_site': human_time_since(user_obj.created_at) if user_obj else 'неизвестно',
            'avatar_url': avatar_url,
        })


    return render_template(
        'auth/../templates/lots.html',
        lots=enriched_lots,
        category=category,
        game=game,
        user_avg_ratings=user_avg_ratings,
        users_dict=users_dict,
        platform=platform,
        sort=sort,
        auto=auto,
        has_more=pagination.has_next,
        page=page
    )

# Удаление лота
@lot_bp.route('/lot/<string:public_id>/delete', methods=['POST'])
@login_required
def delete_lot(public_id):
    lot = Lot.query.filter_by(public_id=public_id).first_or_404()
    if lot.user_id != current_user.id:
        abort(403)
    db.session.delete(lot)
    db.session.commit()
    flash("Лот удалён", "success")
    return redirect(url_for('profile.user_profile',user_id=current_user.id))

@lot_bp.route('/lots/<category>/<int:game_id>')
def lots_by_game(category, game_id):


    game = Game.query.get_or_404(game_id)

    lots = (
        Lot.query
        .options(joinedload(Lot.user), joinedload(Lot.game))  # загружаем связанные объекты
        .filter_by(category=category, game_id=game.id, is_active=True)
        .order_by(Lot.id.desc())
        .all()
    )

    enriched_lots = []
    for lot in lots:
        enriched_lots.append({
            'id': lot.id,
            'title': lot.title,
            'platform': lot.platform,
            'description': lot.description[:80] + '...' if lot.description and len(lot.description) > 80 else lot.description,
            'autodelivery': lot.autodelivery,
            'price': lot.price,
            'seller': lot.user.username if lot.user else 'Без имени',
            'rating': "4.8",
            'years': "2",
            'game': lot.game  # добавляем игру в словарь
        })
    print(category,game_id)
    return render_template('auth/../templates/lots.html', lots=enriched_lots, category=category, game=game)
@lot_bp.route('/edit-lot/<string:public_id>', methods=['GET', 'POST'])
@login_required
def edit_lot(public_id):
    lot = Lot.query.filter_by(public_id=public_id).first_or_404()
    if lot.user_id != current_user.id:
        flash("Вы не можете редактировать этот лот", "danger")
        return redirect(url_for('profile.user_profile',user_id=current_user.id))

    if request.method == 'POST':
        lot.title = request.form['title']
        lot.description = request.form['description']
        lot.price = int(request.form['price'])
        lot.quantity = int(request.form['quantity'])

        # ✅ Проверка чекбокса (очень важно: не используем bool(...)!)
        lot.is_active = 'is_active' in request.form
        quantity = int(request.form.get('quantity', 1))
        if quantity < 1:
            flash("Количество должно быть не меньше 1", "danger")
            return redirect(url_for('lot.edit_lot', public_id=lot.public_id))

        db.session.commit()
        return redirect(url_for('profile.user_profile',user_id=current_user.id))

    return render_template('lots/edit_lot.html', lot=lot)
def human_time_since(registration_date):
    from datetime import datetime

    delta = datetime.utcnow() - registration_date
    days = delta.days
    if days < 30:
        return f"{days} дн." if days > 0 else "менее дня"
    elif days < 365:
        months = days // 30
        return f"{months} мес."
    else:
        years = days // 365
        months = (days % 365) // 30
        if months == 0:
            return f"{years} {plural_year(years)}"
        return f"{years} {plural_year(years)} {months} мес."

def plural_year(years):
    if years % 10 == 1 and years % 100 != 11:
        return "год"
    elif 2 <= years % 10 <= 4 and not 12 <= years % 100 <= 14:
        return "года"
    else:
        return "лет"


@lot_bp.route('/my-sales')
@login_required
def my_sales():
    from models import Purchase, Review, User

    purchases = (
        Purchase.query
        .filter(
            Purchase.seller_id == current_user.id,
            Purchase.status != "pending"  # 👈 убираем неоплаченные
        )
        .order_by(Purchase.created_at.desc())
        .all()
    )

    buyer_ids = {p.user_id for p in purchases}
    buyers = User.query.filter(User.id.in_(buyer_ids)).all()
    users_dict = {u.id: u for u in buyers}

    purchase_ids = [p.id for p in purchases]
    reviews = Review.query.filter(Review.purchase_id.in_(purchase_ids)).all()
    reviews_by_purchase = {r.purchase_id: r for r in reviews}

    return render_template(
        "user/my_sales.html",
        purchases=purchases,
        users_dict=users_dict,
        reviews=reviews_by_purchase
    )