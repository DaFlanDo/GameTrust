"""Демо-стенд: вход без пароля по ролям, плашка, защита общих аккаунтов."""
import pytest
from flask_login import current_user

from demo import DEMO_ROLES
from extensions import db
from models import Purchase, User
from seed import seed


@pytest.fixture
def demo_app(make_app):
    app = make_app(DEMO_MODE=True)
    with app.app_context():
        seed()
        yield app
        db.session.remove()


@pytest.fixture
def demo_client(demo_app):
    return demo_app.test_client()


def test_demo_routes_hidden_without_demo_mode(client):
    assert client.get("/demo/buyer").status_code == 404
    assert "Демо без регистрации" not in client.get("/login").get_data(as_text=True)


@pytest.mark.parametrize("role", list(DEMO_ROLES))
def test_demo_login_for_each_role(demo_client, role):
    email, _, endpoint = DEMO_ROLES[role]
    resp = demo_client.get(f"/demo/{role}")
    assert resp.status_code == 302
    with demo_client:
        page = demo_client.get(resp.headers["Location"])
        assert page.status_code == 200
        assert current_user.email == email


def test_unknown_role_is_404(demo_client):
    assert demo_client.get("/demo/root").status_code == 404


def test_login_page_and_home_show_demo_entry(demo_client):
    assert "Демо без регистрации" in demo_client.get("/login").get_data(as_text=True)
    assert "/demo/seller" in demo_client.get("/").get_data(as_text=True)


def test_seed_gives_each_role_something_to_see(demo_app):
    buyer = User.query.filter_by(email=DEMO_ROLES["buyer"][0]).one()
    seller = User.query.filter_by(email=DEMO_ROLES["seller"][0]).one()
    # Сделка между демо-покупателем и демо-продавцом ждёт подтверждения
    assert Purchase.query.filter_by(user_id=buyer.id, seller_id=seller.id, status="paid").count() == 1


def test_demo_account_cannot_enable_2fa(demo_client):
    demo_client.get("/demo/buyer")
    resp = demo_client.get("/2fa/setup")
    assert resp.status_code == 302
    assert User.query.filter_by(email=DEMO_ROLES["buyer"][0]).one().twofa_secret is None


def test_admin_cannot_block_or_delete_demo_accounts(demo_client):
    seller = User.query.filter_by(email=DEMO_ROLES["seller"][0]).one()
    demo_client.get("/demo/admin")
    demo_client.post(f"/admin/users/{seller.id}?action=toggle_block")
    demo_client.post(f"/admin/users/{seller.id}?action=delete")
    db.session.expire_all()
    seller = db.session.get(User, seller.id)
    assert seller is not None and not seller.is_blocked


def test_admin_can_still_block_regular_users(demo_client):
    regular = User.query.filter_by(email="nightmarket@example.com").one()
    demo_client.get("/demo/admin")
    demo_client.post(f"/admin/users/{regular.id}?action=toggle_block")
    db.session.expire_all()
    assert db.session.get(User, regular.id).is_blocked


def test_seller_revenue_counts_completed_sales(demo_client):
    demo_client.get("/demo/seller")
    page = demo_client.get("/my-sales").get_data(as_text=True)
    seller = User.query.filter_by(email=DEMO_ROLES["seller"][0]).one()
    completed = sum(p.lot_price for p in Purchase.query.filter_by(seller_id=seller.id, status="completed"))
    assert completed > 0 and f"{completed} ₽" in page
