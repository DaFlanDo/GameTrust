import json

from flask import Blueprint, render_template, jsonify
from models import Game
from extensions import get_cache, set_cache

game_bp = Blueprint('game', __name__)

@game_bp.route('/all-games')
def all_games():
    # Получаем все уникальные игры
    games = Game.query.all()
    # Группируем их по имени, чтобы избежать дублей (т.к. старая структура могла иметь дубли по категориям)
    unique_games = {}
    for g in games:
        if g.name not in unique_games:
            unique_games[g.name] = g
    
    return render_template('lots/all_games.html', games=unique_games.values())

@game_bp.route('/category/<string:category>')
def show_games(category):
    cache_key = f"games:category:{category}"

    cached_data = get_cache(cache_key)
    if cached_data:
        games = json.loads(cached_data)
    else:
        games = [{'id': g.id, 'name': g.name, 'category': g.category, 'image': g.image}
                 for g in Game.query.filter_by(category=category).all()]
        set_cache(cache_key, json.dumps(games), ttl=600)  # 10 минут

    return render_template('lots/games.html', category=category, games=games)
@game_bp.route('/api/games')
def get_games_by_category():
    # Игра одна на все категории: и ключи, и аккаунты CS2 относятся к одной записи
    games = Game.query.order_by(Game.name).all()
    return jsonify([{'id': game.id, 'name': game.name} for game in games])
