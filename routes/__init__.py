from flask import Blueprint

from routes.review import review_bp
from .auth import auth_bp
from .chat import chat_bp
from .lot import lot_bp
from .profile import profile_bp
from .purchase import purchase_bp
from .game import game_bp

def register_blueprints(app):
    app.register_blueprint(auth_bp)
    app.register_blueprint(lot_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(purchase_bp)
    app.register_blueprint(game_bp)
    app.register_blueprint(review_bp)
    app.register_blueprint(chat_bp)
