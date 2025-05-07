# app/blueprints/purchase.py
from __future__ import annotations

import os
from datetime import datetime
from threading import Timer

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
    abort,
)
from flask_login import login_required, current_user

from extensions import db, fernet, limiter
from models import Lot, Purchase, Review, Message, Transaction, User

purchase_bp = Blueprint("purchase", __name__, url_prefix="/purchase")


# ────────────────────────── helpers ──────────────────────────


def create_purchase_and_schedule(lot: Lot) -> Purchase:
    delivery_text = None

    if lot.autodelivery and lot.autodelivery_data:
        lines = fernet.decrypt(lot.autodelivery_data.encode()).decode().splitlines()
        delivery_text = lines.pop(0)                                   # открытый ключ
        lot.autodelivery_data = fernet.encrypt("\n".join(lines).encode()).decode()

    lot.quantity -= 1
    if lot.quantity <= 0:
        lot.is_active = False

    purchase = Purchase(
        user_id          = current_user.id,
        lot_id           = lot.id,
        lot_title        = lot.title,
        lot_description  = lot.description,
        lot_category     = lot.category,
        lot_platform     = lot.platform,
        lot_price        = lot.price,
        seller_username  = lot.user.username if lot.user else "Неизвестно",
        seller_id        = lot.user_id,
        # ↙︎  кладём ЗАШИФРОВАННО
        delivery_data    = fernet.encrypt(delivery_text.encode()).decode()
                           if delivery_text else None
    )
    db.session.add(purchase)
    db.session.flush()
    Timer(5, mark_purchase_paid, args=[purchase.id, current_app._get_current_object()]).start()
    return purchase


def mark_purchase_paid(purchase_id: int, app):
    """Через 5 сек переводит деньги в холд и шлёт системное сообщение."""
    with app.app_context():
        purchase: Purchase | None = Purchase.query.get(purchase_id)
        if not purchase or purchase.status == "paid":
            return

        purchase.status = "paid"

        seller = User.query.get(purchase.seller_id)
        if seller:
            seller.hold_balance += purchase.lot_price

        db.session.commit()

        link = (
            url_for("purchase.order", purchase_id=purchase.id, _external=True)
            .replace("localhost", "127.0.0.1")
        )
        system_msg = Message(
            sender_id=purchase.seller_id,
            receiver_id=purchase.user_id,
            is_system=True,
            content=(
                "<b>✅ Покупка завершена!</b><br>"
                f"<b>🎮 Товар:</b> {purchase.lot_title}<br>"
                f"<b>📂 Категория:</b> {purchase.lot_category} • {purchase.lot_platform}<br>"
                f"<b>💰 Цена:</b> {purchase.lot_price} ₽<br>"
                f"<b>🕒 Время:</b> {purchase.created_at.strftime('%d.%m.%Y %H:%M')}<br>"
                f"<a href='{link}' style='color:#90cdf4;text-decoration:underline;'>🔗 Перейти к заказу</a>"
            ),
        )
        db.session.add(system_msg)
        db.session.commit()


# ────────────────────────── routes ──────────────────────────


@purchase_bp.route("/buy/<string:public_id>", methods=["POST"])
@login_required
def start_purchase(public_id: int):
    """Единая точка: либо покупаем сразу, либо редиректим на пополнение."""
    lot = Lot.query.filter_by(public_id=public_id).first_or_404()

    if not lot.is_active or lot.quantity <= 0:
        flash("Товар недоступен для покупки", "danger")
        return redirect(url_for("lot.lot", public_id = lot.public_id))

    # денег не хватает
    if current_user.balance < lot.price:
        shortage = lot.price - current_user.balance
        session["pending_lot_public_id"] = lot.public_id
        flash(
            f"Не хватает {shortage} ₽. Пополните баланс — покупка завершится автоматически.",
            "warning",
        )
        return redirect(url_for("finance.topup_shortage", amount=shortage))

    # хватает → списываем баланс и создаём покупку
    current_user.balance -= lot.price
    db.session.add(current_user)
    purchase = create_purchase_and_schedule(lot)
    db.session.commit()

    flash("Покупка успешно оформлена!", "success")
    return redirect(url_for("purchase.checkout", public_id=purchase.public_id))


# ────────────────────────── Checkout & Order ──────────────────────────


@purchase_bp.route("/checkout/<string:public_id>")
@login_required
def checkout(public_id:str):
    purchase = Purchase.query.filter_by(public_id=public_id).first_or_404()
    if purchase.user_id != current_user.id:
        flash("Это не ваш заказ!", "danger")
        return redirect(url_for("lot.home"))
    lot = Lot.query.get(purchase.lot_id)
    return render_template("finance/checkout.html", lot=lot, purchase=purchase)


@purchase_bp.route("/order/<string:public_id>")
@login_required
def order(public_id: str):
    purchase = Purchase.query.filter_by(public_id=public_id).first_or_404()

    # проверка доступа
    if purchase.user_id != current_user.id and purchase.seller_id != current_user.id:
        flash("Это не ваш заказ!", "danger")
        return redirect(url_for("lot.home"))

    lot    = Lot.query.get(purchase.lot_id)
    review = Review.query.filter_by(purchase_id=purchase.id).first()

    # ───── расшифруем автодоставку (если есть) ─────
    delivery_text = None
    if purchase.delivery_data:                     # в БД – шифротекст
        try:
            delivery_text = fernet.decrypt(
                purchase.delivery_data.encode()
            ).decode()
        except Exception:
            current_app.logger.warning(
                "Не удалось расшифровать delivery_data заказа %s", purchase.id
            )

    return render_template(
        "finance/order.html",
        purchase=purchase,
        lot=lot,
        review=review,
        delivery_text=delivery_text     # ← передаём в шаблон
    )


# ────────────────────────── Список заказов ──────────────────────────


@purchase_bp.route("/my-orders")
@login_required
def my_orders():
    orders = (
        Purchase.query.filter_by(user_id=current_user.id)
        .order_by(Purchase.created_at.desc())
        .all()
    )
    return render_template("user/my_orders.html", orders=orders)


# ────────────────────────── Отзыв ──────────────────────────


@purchase_bp.route("/review/<string:public_id>", methods=["GET", "POST"])
@login_required
def leave_review(public_id: int):
    purchase = Purchase.query.filter_by(public_id=public_id).first_or_404()
    if purchase.user_id != current_user.id:
        flash("Вы не можете оставить отзыв к этому заказу", "danger")
        return redirect(url_for("purchase.my_orders"))

    if purchase.status != "completed":
        flash("Отзыв доступен только после подтверждения получения", "warning")
        return redirect(url_for("purchase.order", purchase_id=purchase.id))

    if request.method == "POST":
        rating = int(request.form["rating"])
        comment = request.form.get("comment", "")
        review = Review(
            purchase_id=purchase.id,
            reviewer_id=current_user.id,
            seller_id=purchase.seller_id,
            rating=rating,
            comment=comment,
        )
        db.session.add(review)
        db.session.commit()
        flash("Отзыв успешно добавлен!", "success")
        return redirect(url_for("profile.user_profile", user_id=purchase.seller_id))

    return render_template("leave_review.html", purchase=purchase)


@purchase_bp.route("/confirm/<string:public_id>", methods=["POST"])
@login_required
def confirm_receipt(public_id: int):
    """
    Покупатель подтверждает, что получил товар.
    Деньги переходят из hold_balance на баланс продавца.
    """
    purchase = Purchase.query.filter_by(public_id=public_id).first_or_404()

    # Разрешаем только покупателю подтверждать
    if purchase.user_id != current_user.id:
        abort(403)

    if purchase.status != "paid":
        flash("Этот заказ ещё нельзя подтвердить.", "warning")
        return redirect(url_for("purchase.order", public_id=purchase.public_id))

    purchase.status = "completed"
    purchase.is_confirmed = True

    # переводим деньги продавцу
    seller = User.query.get(purchase.seller_id)
    if seller:
        seller.hold_balance -= purchase.lot_price
        seller.balance += purchase.lot_price

    db.session.commit()
    flash("Заказ подтверждён, средства переведены продавцу!", "success")
    return redirect(url_for("purchase.order", public_id=purchase.public_id))