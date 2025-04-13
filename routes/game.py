from flask import Blueprint, render_template, jsonify, request
from models import Game
from extensions import db

game_bp = Blueprint('game', __name__)

@game_bp.route('/category/<string:category>')
def show_games(category):
    games = Game.query.filter_by(category=category).all()
    return render_template('games.html', category=category, games=games)

@game_bp.route('/api/games')
def get_games_by_category():
    category = request.args.get('category')
    if not category:
        return jsonify([])

    games = Game.query.filter_by(category=category).all()
    print(category)
    return jsonify([{'id': game.id, 'name': game.name} for game in games])


