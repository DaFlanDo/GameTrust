import logging
import os

from flask import Flask, send_from_directory, render_template, url_for, redirect, request
from flask_login import current_user, login_required
from werkzeug.middleware.proxy_fix import ProxyFix

from admin import admin_bp
from config import Config
from extensions import db, login_manager, limiter, migrate, csrf
from media import avatar_url, game_image_url, category_label, plural
from models import User
from routes import register_blueprints
from seed import seed_command
from demo import demo_bp, demo_context, reset_demo_command


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)
    if app.config['TRUST_PROXY']:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    logging.basicConfig(level=logging.INFO)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    limiter.init_app(app)
    csrf.init_app(app)

    app.add_template_global(avatar_url)
    app.add_template_global(game_image_url)
    app.add_template_filter(category_label)
    app.add_template_filter(plural)

    app.register_blueprint(admin_bp)
    register_blueprints(app)
    app.register_blueprint(demo_bp)
    app.context_processor(demo_context)
    app.cli.add_command(seed_command)
    app.cli.add_command(reset_demo_command)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

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
            if request.endpoint not in ('auth.logout', 'blocked', 'static'):
                return redirect(url_for('blocked'))

    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(429)
    def ratelimit_handler(e):
        return render_template("errors/429.html"), 429

    return app


if __name__ == '__main__':
    create_app().run(debug=True, port=5000)
