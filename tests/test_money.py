"""Деньги: покупка с удержанием, подтверждение, возвраты, вывод, имитация оплаты."""
import pytest

import escrow
from conftest import login, reload
from extensions import db
from models import Purchase, Transaction, User


def test_negative_withdrawal_does_not_create_money(client, make_user):
    user = make_user(balance=100)
    login(client, user)
    client.post("/finance/withdraw", data={"amount": "-1000", "details": "карта"})
    user = reload(user)
    assert user.balance == 100 and user.hold_balance == 0


def test_withdrawal_over_balance_rejected(client, make_user):
    user = make_user(balance=100)
    login(client, user)
    client.post("/finance/withdraw", data={"amount": "101", "details": "карта"})
    assert reload(user).balance == 100


def test_withdrawal_and_cancel(client, make_user):
    user = make_user(balance=100)
    login(client, user)
    client.post("/finance/withdraw", data={"amount": "60", "details": "карта"})
    user = reload(user)
    assert (user.balance, user.hold_balance) == (40, 60)

    tx = Transaction.query.filter_by(user_id=user.id, type="withdrawal").one()
    client.post(f"/finance/withdraw/cancel/{tx.id}")
    user = reload(user)
    assert (user.balance, user.hold_balance) == (100, 0)
    # Повторная отмена ничего не возвращает
    client.post(f"/finance/withdraw/cancel/{tx.id}")
    assert reload(user).balance == 100


def test_purchase_holds_money_until_confirmation(client, make_user, make_lot):
    seller, buyer = make_user(), make_user(balance=500)
    lot = make_lot(seller, price=300, quantity=2, keys=["KEY-1", "KEY-2"])
    login(client, buyer)

    client.post(f"/purchase/buy/{lot.public_id}")
    purchase = Purchase.query.one()
    assert purchase.status == "paid"
    assert reload(buyer).balance == 200
    assert (reload(seller).balance, seller.hold_balance) == (0, 300)
    assert reload(lot).quantity == 1

    # Покупатель видит выданный ключ, продавцу его не показываем
    assert "KEY-1" in client.get(f"/purchase/order/{purchase.public_id}").get_data(as_text=True)
    login(client, seller)
    assert "KEY-1" not in client.get(f"/purchase/order/{purchase.public_id}").get_data(as_text=True)

    login(client, buyer)
    client.post(f"/purchase/confirm/{purchase.public_id}")
    assert (reload(seller).balance, seller.hold_balance) == (300, 0)
    # Второе подтверждение не переводит деньги ещё раз
    client.post(f"/purchase/confirm/{purchase.public_id}")
    assert reload(seller).balance == 300


def test_cannot_buy_own_lot(client, make_user, make_lot):
    seller = make_user(balance=500)
    lot = make_lot(seller, price=100)
    login(client, seller)
    client.post(f"/purchase/buy/{lot.public_id}")
    assert Purchase.query.count() == 0
    assert reload(seller).balance == 500


def test_last_item_cannot_be_sold_twice(app, make_user, make_lot):
    seller, a, b = make_user(), make_user(balance=100), make_user(balance=100)
    lot = make_lot(seller, price=100, quantity=1)
    escrow.buy_lot(a, lot.public_id)
    with pytest.raises(escrow.EscrowError):
        escrow.buy_lot(b, lot.public_id)
    assert reload(b).balance == 100


def test_balance_cannot_go_negative_with_stale_object(app, make_user, make_lot):
    """Второе списание проверяется в самом UPDATE, а не по устаревшему объекту в памяти."""
    seller, buyer = make_user(), make_user(balance=100)
    first, second = make_lot(seller, price=100), make_lot(seller, price=100)
    escrow.buy_lot(buyer, first.public_id)
    db.session.expunge(buyer)
    buyer.balance = 100  # будто второй запрос прочитал баланс до первого списания
    with pytest.raises(escrow.InsufficientFunds):
        escrow.buy_lot(buyer, second.public_id)
    assert db.session.get(User, buyer.id).balance == 0


def test_topup_for_shortage_completes_purchase(client, make_user, make_lot):
    seller, buyer = make_user(), make_user(balance=30)
    lot = make_lot(seller, price=100)
    login(client, buyer)

    resp = client.post(f"/purchase/buy/{lot.public_id}")
    assert "/finance/topup/shortage" in resp.headers["Location"]
    resp = client.get(resp.headers["Location"])
    tx = Transaction.query.filter_by(user_id=buyer.id, type="topup").one()
    assert tx.amount == 70

    resp = client.post(f"/finance/topup/pay/{tx.id}/confirm")
    purchase = Purchase.query.one()
    assert resp.headers["Location"].endswith(f"/purchase/checkout/{purchase.public_id}")
    assert reload(buyer).balance == 0
    assert reload(seller).hold_balance == 100


def test_topup_confirm_only_for_pending_topups(client, make_user):
    user = make_user(balance=100)
    login(client, user)
    client.post("/finance/withdraw", data={"amount": "50", "details": "карта"})
    withdrawal = Transaction.query.filter_by(type="withdrawal").one()

    client.post(f"/finance/topup/pay/{withdrawal.id}/confirm")
    assert reload(withdrawal).status == "pending"
    assert reload(user).balance == 50


def test_topup_amount_is_validated(client, make_user):
    user = make_user()
    login(client, user)
    for bad in ["-500", "abc", "0", "100000000000"]:
        client.post("/finance/topup/init", data={"amount": bad})
    assert Transaction.query.count() == 0


def test_admin_confirm_moves_money_from_hold(client, make_user, make_lot):
    admin, seller, buyer = make_user(is_admin=True), make_user(), make_user(balance=100)
    lot = make_lot(seller, price=100)
    purchase = escrow.buy_lot(buyer, lot.public_id)

    login(client, admin)
    client.post(f"/admin/orders/{purchase.id}/confirm")
    assert (reload(seller).balance, seller.hold_balance) == (100, 0)


def test_admin_refund_of_completed_order_debits_seller(client, make_user, make_lot):
    admin, seller, buyer = make_user(is_admin=True), make_user(), make_user(balance=100)
    lot = make_lot(seller, price=100)
    purchase = escrow.buy_lot(buyer, lot.public_id)
    escrow.complete_purchase(purchase)

    login(client, admin)
    client.post(f"/admin/orders/{purchase.id}/refund")
    assert reload(buyer).balance == 100
    assert reload(seller).balance == 0
    # Повторный возврат не удваивает деньги
    client.post(f"/admin/orders/{purchase.id}/refund")
    assert reload(buyer).balance == 100


def test_admin_refund_of_paid_order_releases_hold(client, make_user, make_lot):
    admin, seller, buyer = make_user(is_admin=True), make_user(), make_user(balance=100)
    purchase = escrow.buy_lot(buyer, make_lot(seller, price=100).public_id)

    login(client, admin)
    client.post(f"/admin/orders/{purchase.id}/refund")
    assert reload(buyer).balance == 100
    assert (reload(seller).balance, seller.hold_balance) == (0, 0)


def test_non_admin_cannot_refund(client, make_user, make_lot):
    seller, buyer = make_user(), make_user(balance=100)
    purchase = escrow.buy_lot(buyer, make_lot(seller, price=100).public_id)
    login(client, buyer)
    client.post(f"/admin/orders/{purchase.id}/refund")
    assert reload(purchase).status == "paid"
