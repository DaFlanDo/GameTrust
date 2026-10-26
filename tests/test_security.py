"""XSS, CSRF, кэш главной, загрузки, отзывы и валидация лотов."""
import io

import escrow
from conftest import login, reload
from models import Lot, Message, Review

XSS = '<img src=x onerror="alert(1)">'


def test_chat_message_is_escaped(client, make_user):
    alice, bob = make_user(), make_user()
    login(client, alice)
    resp = client.post("/api/messages/send", json={"receiver_id": bob.id, "content": XSS})
    assert resp.status_code == 200

    login(client, bob)
    page = client.get(f"/messages/{alice.id}").get_data(as_text=True)
    assert XSS not in page
    assert "&lt;img" in page
    # Новые сообщения подставляются скриптом через textContent, а не innerHTML
    assert "textContent = msg.content" in page


def test_system_message_escapes_lot_title(app, make_user, make_lot):
    seller, buyer = make_user(), make_user(balance=100)
    lot = make_lot(seller, price=100, title=XSS)
    escrow.buy_lot(buyer, lot.public_id)
    system = Message.query.filter_by(is_system=True).one()
    assert XSS not in system.content and "&lt;img" in system.content


def test_chat_rejects_unknown_receiver_and_self(client, make_user):
    alice = make_user()
    login(client, alice)
    assert client.post("/api/messages/send", json={"receiver_id": 999, "content": "hi"}).status_code == 404
    assert client.post("/api/messages/send", json={"receiver_id": alice.id, "content": "hi"}).status_code == 404
    assert client.post("/api/messages/send", json={"receiver_id": "1", "content": "hi"}).status_code == 404
    assert Message.query.count() == 0


def test_csrf_required_for_money_operations(make_app, make_user):
    app = make_app(WTF_CSRF_ENABLED=True)
    with app.app_context():
        user = make_user(balance=100)
        client = app.test_client()
        login(client, user)
        resp = client.post("/finance/withdraw", data={"amount": "50", "details": "карта"})
        assert resp.status_code == 400
        assert reload(user).balance == 100


def test_home_cache_does_not_leak_logged_in_user(make_app, make_user, monkeypatch):
    import routes.lot as lot_routes
    store = {}
    monkeypatch.setattr(lot_routes, "get_cache", store.get)
    monkeypatch.setattr(lot_routes, "set_cache", lambda k, v, ttl=0: store.__setitem__(k, v))

    app = make_app()
    with app.app_context():
        user = make_user(username="secret_alice", balance=777)
        client = app.test_client()
        login(client, user)
        assert "secret_alice" in client.get("/").get_data(as_text=True)
        assert store == {}  # страницу залогиненного пользователя не кэшируем

        guest = app.test_client()
        assert "secret_alice" not in guest.get("/").get_data(as_text=True)
        assert lot_routes.PAGE_KEY in store


def test_avatar_must_be_an_image(client, make_user):
    user = make_user()
    login(client, user)
    client.post(f"/user/{user.id}", data={"avatar": (io.BytesIO(b"<script>alert(1)</script>"), "evil.html")},
                content_type="multipart/form-data")
    assert reload(user).avatar == "default.png"


def test_profile_post_requires_owner(client, make_user):
    alice, bob = make_user(), make_user()
    assert client.post(f"/user/{alice.id}", data={"username": "hacked"}).status_code == 403
    login(client, bob)
    assert client.post(f"/user/{alice.id}", data={"username": "hacked"}).status_code == 403
    assert reload(alice).username != "hacked"


def test_review_only_once_and_in_range(client, make_user, make_lot):
    seller, buyer = make_user(), make_user(balance=100)
    purchase = escrow.buy_lot(buyer, make_lot(seller, price=100).public_id)
    escrow.complete_purchase(purchase)
    login(client, buyer)

    client.post(f"/submit-review/{purchase.public_id}", data={"rating": "1000"})
    assert Review.query.count() == 0
    client.post(f"/submit-review/{purchase.public_id}", data={"rating": "5", "comment": "ok"})
    client.post(f"/submit-review/{purchase.public_id}", data={"rating": "5", "comment": "ещё раз"})
    assert Review.query.count() == 1
    # Старый маршрут, который обходил эти проверки, удалён
    assert client.post(f"/purchase/review/{purchase.public_id}", data={"rating": "1000"}).status_code == 404


def test_lot_price_must_be_positive(client, make_user, game):
    seller = make_user()
    login(client, seller)
    form = {"title": "Ключ", "category": "Keys", "platform": "PC", "game_id": str(game.id), "quantity": "1"}
    for bad in ["-100", "0", "abc"]:
        client.post("/submit-lot", data={**form, "price": bad})
    assert Lot.query.count() == 0
    client.post("/submit-lot", data={**form, "price": "150"})
    assert Lot.query.one().price == 150


def test_all_category_lists_every_lot(client, make_user, make_lot, game):
    seller = make_user()
    make_lot(seller, title="Ключ CS2")
    make_lot(seller, title="Аккаунт CS2 Prime", category="Accounts")

    page = client.get(f"/lots/all/{game.id}").get_data(as_text=True)
    assert "Ключ CS2" in page and "Аккаунт CS2 Prime" in page


def test_seed_builds_consistent_demo(app):
    """Демо-данные проходят через те же функции, что и сайт, и балансы сходятся."""
    from seed import seed
    from models import Purchase, User
    seed()
    assert Purchase.query.filter_by(status="paid").count() == 1
    assert Review.query.count() == 5
    total_in = 4 * 30000
    total = sum(u.balance + u.hold_balance for u in User.query.all())
    assert total == total_in


def test_admin_dashboard_charts(client, make_user, make_lot):
    admin, seller, buyer = make_user(is_admin=True), make_user(), make_user(balance=300)
    escrow.buy_lot(buyer, make_lot(seller, price=300).public_id)
    login(client, admin)
    page = client.get("/admin").get_data(as_text=True)
    assert "[0, 0, 0, 0, 0, 0, 300]" in page  # доход за сегодня
    login(client, buyer)
    assert "Панель администратора" not in client.get("/admin", follow_redirects=True).get_data(as_text=True)


def test_dialog_preview_shows_system_message_as_text(client, make_user, make_lot):
    seller, buyer = make_user(), make_user(balance=100)
    escrow.buy_lot(buyer, make_lot(seller, price=100, title="Ключ & бонус").public_id)
    login(client, buyer)
    page = client.get("/messages").get_data(as_text=True)
    assert "Покупка оформлена!" in page
    # Ни тегов, ни двойного экранирования в превью
    assert "&lt;b&gt;" not in page and "&amp;amp;" not in page
    assert "Ключ &amp; бонус" in page
