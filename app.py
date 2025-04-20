import eventlet
# 🧠 САМЫЙ ВЕРХ
from apscheduler.schedulers.background import BackgroundScheduler

from flask import Flask, send_from_directory, render_template
import os
from cryptography.fernet import Fernet
from config import Config
from extensions import db, login_manager, fernet, limiter, migrate, cancel_expired_transactions
from routes import register_blueprints
from models import User

app = Flask(__name__)
app.config.from_object(Config)
app.app_context().push()

# Создаём папку для загрузок
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Инициализация расширений
db.init_app(app)
login_manager.init_app(app)
login_manager.login_view = 'auth.login'
fernet = Fernet(app.config['FERNET_SECRET_KEY'])

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

# Обработчики ошибок
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(429)
def ratelimit_handler(e):
    return render_template("429.html"), 429

@app.route('/test-error')
def test_error():
    raise Exception("🧨 Проверка ошибки 500")

# ⬇️⬇️⬇️ Только теперь импортируй хендлеры
scheduler = BackgroundScheduler()
scheduler.add_job(cancel_expired_transactions, 'interval', minutes=1, args=[app])
scheduler.start()
# Запуск через socketio
if __name__ == '__main__':
    app.run( debug=True,reload=True, port=5000)