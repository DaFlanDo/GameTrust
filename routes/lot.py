import json
import os
import uuid
from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, abort, session
from flask_login import login_required, current_user
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from werkzeug.utils import secure_filename

from extensions import db, fernet, limiter, get_cache, set_cache
from media import avatar_url
from models import Lot, Game, Review, User, Purchase

lot_bp = Blueprint('lot', __name__)

CACHE_TTL = 300  # 5 минут
PAGE_KEY = 'home:html'
CATEGORIES = {'Accounts', 'Keys', 'Currency', 'Services'}
PLATFORMS = {'PC', 'PlayStation', 'Xbox', 'Nintendo', 'Mobile'}
MAX_PRICE = 1_000_000
MAX_QUANTITY = 1000
ALLOWED_EXT = {"png", "jpg", "jpeg", "webp", "gif"}


def _positive_int(raw, maximum):
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if 1 <= value <= maximum else None


def is_allowed(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


# Главная страница
@lot_bp.route('/')
def home():
    # В шапке страницы имя и баланс пользователя, поэтому готовый HTML кэшируем
    # только для гостей и только если для них нет флеш-сообщений
    cacheable = (not current_app.debug and not current_user.is_authenticated
                 and not session.get('_flashes'))
    if cacheable:
        cached_html = get_cache(PAGE_KEY)
        if cached_html is not None:
            return cached_html.decode()

    popular_lots = (Lot.query.options(joinedload(Lot.user), joinedload(Lot.game))
                    .filter_by(is_active=True)
                    .order_by(Lot.price.desc())
                    .limit(9).all())
    recent_orders = Purchase.query.order_by(Purchase.created_at.desc()).limit(8).all()
    top_games = Game.query.order_by(Game.name).limit(8).all()

    html = render_template("index.html", lots=popular_lots,
                           recent_orders=recent_orders, top_games=top_games)
    if cacheable:
        set_cache(PAGE_KEY, html.encode(), ttl=CACHE_TTL)
    return html


# Подробная страница лота
@lot_bp.route('/lot/<string:public_id>')
def lot(public_id):
    lot = Lot.query.filter_by(public_id=public_id).first_or_404()
    seller = db.get_or_404(User, lot.user_id)

    seller_sales = Purchase.query.filter_by(seller_id=seller.id).count()
    years_on_site = max((datetime.utcnow() - seller.created_at).days // 365, 1)
    review_count, avg_rating = (db.session.query(func.count(Review.id), func.avg(Review.rating))
                                .filter(Review.seller_id == seller.id).one())

    return render_template('lots/product.html', lot=lot, user=seller,
                           sales=seller_sales, years=years_on_site,
                           review_count=review_count, rating=round(avg_rating or 0, 1))


# Добавление лота - GET
@lot_bp.route('/add-lot')
@login_required
def add_lot():
    if not current_user.is_confirmed:
        flash("Для выставления лотов необходимо подтвердить email.", "warning")
        return redirect(url_for('lot.home'))
    games = Game.query.order_by(Game.name).all()
    return render_template('lots/add_lot.html', games=games)


# Добавление лота - POST
@lot_bp.route("/submit-lot", methods=["POST"])
@limiter.limit("3 per minute", methods=["POST"])
@login_required
def submit_lot():
    if not current_user.is_confirmed:
        flash("Для выставления лотов необходимо подтвердить email.", "warning")
        return redirect(url_for('lot.home'))

    # ───── 1. Собираем и проверяем поля формы ─────
    title = request.form.get("title", "").strip()[:150]
    category = request.form.get("category")
    platform = request.form.get("platform")
    description = request.form.get("description")
    price = _positive_int(request.form.get("price"), MAX_PRICE)
    quantity = _positive_int(request.form.get("quantity", 1), MAX_QUANTITY)
    game = db.session.get(Game, _positive_int(request.form.get("game_id"), 2**31 - 1) or 0)
    autodeliv = "autodelivery" in request.form
    autodata = request.form.get("autodelivery_data", "")

    errors = []
    if not title:
        errors.append("Укажите название")
    if category not in CATEGORIES:
        errors.append("Выберите категорию")
    if platform not in PLATFORMS:
        errors.append("Выберите платформу")
    if game is None:
        errors.append("Выберите игру")
    if price is None:
        errors.append(f"Цена — целое число от 1 до {MAX_PRICE} ₽")
    if quantity is None:
        errors.append(f"Количество — от 1 до {MAX_QUANTITY}")
    if errors:
        for e in errors:
            flash(e, "danger")
        return redirect(url_for("lot.add_lot"))

    # ───── 2. Валидируем автовыдачу ─────
    if autodeliv:
        lines = [l.strip() for l in autodata.splitlines() if l.strip()]
        if len(lines) != quantity:
            flash(f"Строк данных ({len(lines)}) ≠ количеству товара ({quantity})", "danger")
            return redirect(url_for("lot.add_lot"))
        autodata_enc = fernet.encrypt("\n".join(lines).encode()).decode()
    else:
        autodata_enc = None

    # ───── 3. Сохраняем изображения ─────
    saved_files = []
    for file in request.files.getlist("images[]"):
        if file and file.filename and is_allowed(file.filename):
            ext = file.filename.rsplit(".", 1)[1].lower()
            filename = secure_filename(f"{uuid.uuid4().hex}.{ext}")
            file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
            saved_files.append(filename)

    # ───── 4. Создаём лот ─────
    new_lot = Lot(
        title=title,
        category=category,
        platform=platform,
        description=description,
        price=price,
        quantity=quantity,
        autodelivery=autodeliv,
        autodelivery_data=autodata_enc,
        image_filenames=json.dumps(saved_files),
        user_id=current_user.id,
        game_id=game.id,
    )
    db.session.add(new_lot)
    db.session.commit()

    flash("Лот успешно добавлен!", "success")
    return redirect(url_for("lot.lots", category=category, game_id=game.id))


# Лоты игры: все или по категории
@lot_bp.route('/lots/<category>/<int:game_id>')
def lots(category, game_id):
    game = db.get_or_404(Game, game_id)

    all_categories = [
        ('Accounts', 'Аккаунты'),
        ('Keys', 'Ключи'),
        ('Currency', 'Валюта'),
        ('Services', 'Услуги')
    ]

    lots_query = (Lot.query.options(db.joinedload(Lot.user), db.joinedload(Lot.game))
                  .filter_by(game_id=game_id, is_active=True))
    if category != 'all':
        lots_query = lots_query.filter_by(category=category)

    platform = request.args.get('platform')
    sort = request.args.get('sort')
    auto = request.args.get('auto') == '1'

    if platform in PLATFORMS:
        lots_query = lots_query.filter(Lot.platform == platform)
    if auto:
        lots_query = lots_query.filter(Lot.autodelivery == True)

    if sort == 'price_asc':
        lots_query = lots_query.order_by(Lot.price.asc())
    elif sort == 'price_desc':
        lots_query = lots_query.order_by(Lot.price.desc())
    elif sort == 'new':
        lots_query = lots_query.order_by(Lot.created_at.desc())
    else:
        lots_query = lots_query.order_by(Lot.id.desc())

    page = request.args.get("page", 1, type=int)
    pagination = lots_query.paginate(page=page, per_page=20, error_out=False)
    lots = pagination.items

    # Рейтинги продавцов одним запросом
    user_ids = {lot.user_id for lot in lots if lot.user_id is not None}
    rating_data = (
        db.session.query(Review.seller_id, func.avg(Review.rating))
        .filter(Review.seller_id.in_(user_ids))
        .group_by(Review.seller_id)
        .all()
    )
    user_avg_ratings = {seller_id: round(avg_rating, 1) for seller_id, avg_rating in rating_data}
    users_dict = {lot.user.id: lot.user for lot in lots if lot.user}

    enriched_lots = []
    for lot in lots:
        user_obj = lot.user
        rating = user_avg_ratings.get(lot.user_id, 0.0)
        short_desc = lot.description[:80] + '...' if lot.description and len(lot.description) > 80 else lot.description

        enriched_lots.append({
            'id': lot.id,
            'title': lot.title,
            'public_id': lot.public_id,
            'platform': lot.platform,
            'category': lot.category,
            'description': short_desc,
            'autodelivery': lot.autodelivery,
            'price': lot.price,
            'seller': user_obj.username if user_obj else 'Без имени',
            'rating': rating,
            'rating_int': min(int(rating), 5),
            'game': lot.game,
            'on_site': human_time_since(user_obj.created_at) if user_obj else 'неизвестно',
            'avatar_url': avatar_url(user_obj),
        })

    return render_template(
        'lots/lots.html',
        lots=enriched_lots,
        category=category,
        game=game,
        user_avg_ratings=user_avg_ratings,
        users_dict=users_dict,
        platform=platform,
        sort=sort,
        auto=auto,
        page=page,
        all_categories=all_categories
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
    return redirect(url_for('profile.user_profile', user_id=current_user.id))


@lot_bp.route('/edit-lot/<string:public_id>', methods=['GET', 'POST'])
@login_required
def edit_lot(public_id):
    lot = Lot.query.filter_by(public_id=public_id).first_or_404()
    if lot.user_id != current_user.id:
        abort(403)

    # Расшифровываем текущие данные автовыдачи для формы
    current_autodata = ""
    if lot.autodelivery and lot.autodelivery_data:
        try:
            current_autodata = fernet.decrypt(lot.autodelivery_data.encode()).decode()
        except Exception:
            current_autodata = "ОШИБКА ДЕШИФРОВАНИЯ"

    if request.method == 'POST':
        autodata_form = request.form.get("autodelivery_data", "").strip()
        price = _positive_int(request.form.get('price'), MAX_PRICE)
        if price is None:
            flash(f"Цена — целое число от 1 до {MAX_PRICE} ₽", "danger")
            return render_template('lots/edit_lot.html', lot=lot, current_autodata=autodata_form)

        lot.title = request.form.get('title', '').strip()[:150] or lot.title
        lot.description = request.form.get('description', '')
        lot.price = price
        lot.autodelivery = "autodelivery" in request.form
        lot.is_active = "is_active" in request.form

        if lot.autodelivery:
            lines = [l.strip() for l in autodata_form.splitlines() if l.strip()]
            if not lines:
                db.session.rollback()
                flash("Автовыдача не может быть включена без данных.", "danger")
                return render_template('lots/edit_lot.html', lot=lot, current_autodata=autodata_form)
            lot.quantity = len(lines)
            lot.autodelivery_data = fernet.encrypt("\n".join(lines).encode()).decode()
        else:
            lot.quantity = _positive_int(request.form.get('quantity', 1), MAX_QUANTITY) or 1
            lot.autodelivery_data = None

        db.session.commit()
        flash("Изменения успешно сохранены", "success")
        return redirect(url_for('profile.user_profile', user_id=current_user.id))

    return render_template('lots/edit_lot.html', lot=lot, current_autodata=current_autodata)


def human_time_since(registration_date):
    days = (datetime.utcnow() - registration_date).days
    if days < 30:
        return f"{days} дн." if days > 0 else "менее дня"
    elif days < 365:
        return f"{days // 30} мес."
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
    return "лет"


@lot_bp.route('/my-sales')
@login_required
def my_sales():
    purchases = (
        Purchase.query
        .filter(Purchase.seller_id == current_user.id, Purchase.status != "pending")
        .order_by(Purchase.created_at.desc())
        .all()
    )

    buyer_ids = {p.user_id for p in purchases}
    users_dict = {u.id: u for u in User.query.filter(User.id.in_(buyer_ids)).all()}

    purchase_ids = [p.id for p in purchases]
    reviews = Review.query.filter(Review.purchase_id.in_(purchase_ids)).all()
    reviews_by_purchase = {r.purchase_id: r for r in reviews}

    return render_template(
        "user/my_sales.html",
        purchases=purchases,
        users_dict=users_dict,
        reviews=reviews_by_purchase
    )
