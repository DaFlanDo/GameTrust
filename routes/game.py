import pickle

from flask import Blueprint, render_template, jsonify, request
from models import Game
from extensions import db, get_cache, set_cache

game_bp = Blueprint('game', __name__)

@game_bp.route('/category/<string:category>')
def show_games(category):
    cache_key = f"games:category:{category}"

    cached_data = get_cache(cache_key)
    if cached_data:
        print('Кэш сработал')
        games = pickle.loads(cached_data)
    else:
        games = Game.query.filter_by(category=category).all()
        set_cache(cache_key, pickle.dumps(games), ttl=600)  # 10 минут

    return render_template('lots/games.html', category=category, games=games)
@game_bp.route('/api/games')
def get_games_by_category():
    category = request.args.get('category')
    if not category:
        return jsonify([])

    games = Game.query.filter_by(category=category).all()
    print(category)
    return jsonify([{'id': game.id, 'name': game.name} for game in games])


