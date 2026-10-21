"""Помощники для шаблонов: картинки с заглушками из static/img, подписи, склонения."""
from flask import url_for


def avatar_url(user):
    if user is not None and user.avatar and user.avatar != 'default.png':
        return url_for('static', filename=f'uploads/avatars/{user.avatar}')
    return url_for('static', filename='img/default_avatar.png')


def game_image_url(game):
    if game is not None and game.image and game.image != 'default_game.png':
        return url_for('static', filename=f'uploads/games/{game.image}')
    return url_for('static', filename='img/default_game.png')


CATEGORY_LABELS = {'Accounts': 'Аккаунты', 'Keys': 'Ключи', 'Currency': 'Валюта', 'Services': 'Услуги'}


def category_label(category):
    return CATEGORY_LABELS.get(category, category)


def plural(n, one, few, many):
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many
