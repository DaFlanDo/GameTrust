# 🧠 САМЫЙ ВЕРХ
from apscheduler.schedulers.background import BackgroundScheduler

from flask import Flask, send_from_directory, render_template, url_for, redirect, request
import os
from cryptography.fernet import Fernet
from flask_login import current_user, login_required

from admin import admin_bp
from config import Config
from extensions import db, login_manager, fernet, limiter, migrate, cancel_expired_transactions, mail
from routes import register_blueprints
from models import User

app = Flask(__name__)
app.config.from_object(Config)
app.app_context().push()
app.register_blueprint(admin_bp)
# Создаём папку для загрузок
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Инициализация расширений
db.init_app(app)
migrate.init_app(app, db)  # ✨ Initialize migrations
login_manager.init_app(app)
login_manager.login_view = 'auth.login'
fernet = Fernet(app.config['FERNET_SECRET_KEY'])
mail.init_app(app)

# 🔥 Create tables automatically if they don't exist
with app.app_context():
    db.create_all()
    # Очистка кэша при старте (если в debug), чтобы не мучаться с F5
    if app.debug:
        from extensions import redis_client
        try:
            redis_client.delete('home:html', 'home:data')
            print("🧹 Cache cleared on startup")
        except:
            print("⚠️ Redis not available for cache clearing")
# Загрузка текущего пользователя
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Регистрация всех маршрутов (из routes/)
register_blueprints(app)

# Раздача загруженных файлов
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/blocked')
@login_required
def blocked():
    if not current_user.is_blocked:
        return redirect(url_for('lot.home'))
    return render_template('errors/blocked.html', reason=current_user.block_reason)

@app.before_request
def check_if_blocked():
    if current_user.is_authenticated and current_user.is_blocked:
        if (
                request.endpoint not in ('auth.logout', 'blocked', 'static')):
            return redirect(url_for('blocked'))
# Обработчики ошибок
@app.errorhandler(404)
def page_not_found(e):
    return render_template('errors/404.html'), 404

@app.errorhandler(403)
def forbidden(e):
    return render_template("errors/403.html"), 403

@app.errorhandler(429)
def ratelimit_handler(e):
    return render_template("errors/429.html"), 429

@app.route('/test-error')
def test_error():
    raise Exception("🧨 Проверка ошибки 500")

#scheduler = BackgroundScheduler()
#scheduler.add_job(cancel_expired_transactions, 'interval', minutes=1, args=[app])
#scheduler.start()
# Запуск через socketio
if __name__ == '__main__':
    app.run(debug=True, use_reloader=True, port=5000)