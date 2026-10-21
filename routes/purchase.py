from flask import Blueprint, current_app, flash, redirect, render_template, session, url_for, abort
from flask_login import login_required, current_user

import escrow
from extensions import db, fernet
from models import Lot, Purchase, Review

purchase_bp = Blueprint("purchase", __name__, url_prefix="/purchase")


@purchase_bp.route("/buy/<string:public_id>", methods=["POST"])
@login_required
def start_purchase(public_id):
    """Либо покупаем сразу, либо отправляем пополнить баланс на недостающую сумму."""
    try:
        purchase = escrow.buy_lot(current_user, public_id)
    except escrow.InsufficientFunds as e:
        session["pending_lot_public_id"] = public_id
        flash(f"Не хватает {e.shortage} ₽. Пополните баланс — покупка завершится автоматически.", "warning")
        return redirect(url_for("finance.topup_shortage", amount=e.shortage))
    except escrow.EscrowError as e:
        flash(str(e), "danger")
        return redirect(url_for("lot.lot", public_id=public_id))

    flash("Покупка успешно оформлена!", "success")
    return redirect(url_for("purchase.checkout", public_id=purchase.public_id))


@purchase_bp.route("/checkout/<string:public_id>")
@login_required
def checkout(public_id):
    purchase = Purchase.query.filter_by(public_id=public_id).first_or_404()
    if purchase.user_id != current_user.id:
        abort(403)
    lot = db.session.get(Lot, purchase.lot_id) if purchase.lot_id else None
    return render_template("finance/checkout.html", lot=lot, purchase=purchase)


@purchase_bp.route("/order/<string:public_id>")
@login_required
def order(public_id):
    purchase = Purchase.query.filter_by(public_id=public_id).first_or_404()
    if current_user.id not in (purchase.user_id, purchase.seller_id):
        abort(403)

    lot = db.session.get(Lot, purchase.lot_id) if purchase.lot_id else None
    review = Review.query.filter_by(purchase_id=purchase.id).first()

    # Выданный товар видит только покупатель
    delivery_text = None
    if purchase.delivery_data and current_user.id == purchase.user_id:
        try:
            delivery_text = fernet.decrypt(purchase.delivery_data.encode()).decode()
        except Exception:
            current_app.logger.warning("Не удалось расшифровать delivery_data заказа %s", purchase.id)

    return render_template("finance/order.html", purchase=purchase, lot=lot,
                           review=review, delivery_text=delivery_text)


@purchase_bp.route("/my-orders")
@login_required
def my_orders():
    orders = (Purchase.query.filter_by(user_id=current_user.id)
              .order_by(Purchase.created_at.desc()).all())
    return render_template("user/my_orders.html", orders=orders)


@purchase_bp.route("/confirm/<string:public_id>", methods=["POST"])
@login_required
def confirm_receipt(public_id):
    """Покупатель подтверждает получение — деньги из удержания уходят продавцу."""
    purchase = Purchase.query.filter_by(public_id=public_id).first_or_404()
    if purchase.user_id != current_user.id:
        abort(403)

    try:
        escrow.complete_purchase(purchase)
    except escrow.EscrowError as e:
        flash(str(e), "warning")
        return redirect(url_for("purchase.order", public_id=purchase.public_id))

    flash("Заказ подтверждён, средства переведены продавцу!", "success")
    return redirect(url_for("purchase.order", public_id=purchase.public_id))
