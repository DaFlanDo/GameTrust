import time
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, abort, jsonify
from flask_login import login_required, current_user
from sqlalchemy import desc, func, case, and_, or_

from extensions import db
from models import User, Message

chat_bp = Blueprint('chat', __name__)

# Список сообщений
@chat_bp.route('/messages')
@login_required
def message_list():
    # Сложный запрос для получения последнего сообщения в каждом диалоге
    # и подсчета непрочитанных сообщений.
    
    # 1. Находим ID последних сообщений для каждой пары собеседников
    subquery = (
        db.session.query(
            func.max(Message.id).label('last_msg_id'),
            case(
                (Message.sender_id < Message.receiver_id, Message.sender_id),
                else_=Message.receiver_id
            ).label('u1'),
            case(
                (Message.sender_id < Message.receiver_id, Message.receiver_id),
                else_=Message.sender_id
            ).label('u2')
        )
        .filter(
            (Message.sender_id == current_user.id) | (Message.receiver_id == current_user.id)
        )
        .group_by('u1', 'u2')
        .subquery()
    )

    # 2. Получаем сами сообщения
    last_messages = (
        db.session.query(Message)
        .join(subquery, Message.id == subquery.c.last_msg_id)
        .options(db.joinedload(Message.sender), db.joinedload(Message.receiver))
        .order_by(desc(Message.created_at))
        .all()
    )

    # 3. Подсчитываем непрочитанные сообщения для каждого собеседника
    unread_counts_query = (
        db.session.query(Message.sender_id, func.count(Message.id))
        .filter(Message.receiver_id == current_user.id)
        .filter(Message.is_read == False)
        .group_by(Message.sender_id)
        .all()
    )
    unread_counts = {sender_id: count for sender_id, count in unread_counts_query}

    # Формируем список диалогов
    dialogs = []
    for msg in last_messages:
        other_user = msg.receiver if msg.sender_id == current_user.id else msg.sender
        if other_user:
            dialogs.append({
                'user': other_user,
                'last_message': msg,
                'unread_count': unread_counts.get(other_user.id, 0)
            })

    return render_template('user/messages.html', dialogs=dialogs)

# Чат с пользователем
@chat_bp.route('/messages/<int:user_id>')
@login_required
def chat_with_user(user_id):
    other_user = User.query.get_or_404(user_id)

    if other_user.id == current_user.id:
        abort(403)

    # Получаем последние 50 сообщений (можно добавить пагинацию в будущем)
    messages = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.receiver_id == other_user.id)) |
        ((Message.sender_id == other_user.id) & (Message.receiver_id == current_user.id))
    ).order_by(Message.created_at.asc()).all()

    # Помечаем непрочитанные сообщения от другого пользователя как прочитанные
    unread_ids = [msg.id for msg in messages if msg.receiver_id == current_user.id and not msg.is_read]
    if unread_ids:
        Message.query.filter(Message.id.in_(unread_ids)).update({Message.is_read: True}, synchronize_session=False)
        db.session.commit()

    return render_template('user/chat.html', messages=messages, other_user=other_user)

# API для регулярного поллинга или long-poll (здесь улучшенный поллинг)
@chat_bp.route('/api/messages/updates/<int:user_id>')
@login_required
def get_message_updates(user_id):
    last_timestamp_str = request.args.get("after")
    
    if not last_timestamp_str:
        return jsonify({"status": "error", "message": "Missing timestamp"}), 400

    try:
        # Убираем возможную 'Z' в конце и парсим
        if last_timestamp_str.endswith('Z'):
            last_timestamp_str = last_timestamp_str[:-1]
        last_dt = datetime.fromisoformat(last_timestamp_str)
    except ValueError:
        return jsonify({"status": "error", "message": "Invalid timestamp format"}), 400

    # Ищем новые сообщения
    new_messages = Message.query.filter(
        and_(
            or_(
                and_(Message.sender_id == current_user.id, Message.receiver_id == user_id),
                and_(Message.sender_id == user_id, Message.receiver_id == current_user.id)
            ),
            Message.created_at > last_dt
        )
    ).order_by(Message.created_at.asc()).all()

    # Если это сообщения для нас, помечаем их как прочитанные
    unread_ids = [m.id for m in new_messages if m.receiver_id == current_user.id and not m.is_read]
    if unread_ids:
        Message.query.filter(Message.id.in_(unread_ids)).update({Message.is_read: True}, synchronize_session=False)
        db.session.commit()

    return jsonify({
        "status": "success",
        "messages": [
            {
                "id": m.id,
                "sender_id": m.sender_id,
                "content": m.content,
                "timestamp": m.created_at.strftime('%H:%M'),
                "created_at_iso": m.created_at.isoformat(),
                "is_system": m.is_system
            } for m in new_messages
        ]
    })

# Отправка сообщений
@chat_bp.route('/api/messages/send', methods=['POST'])
@login_required
def send_message_api():
    data = request.get_json()
    receiver_id = data.get("receiver_id")
    content = data.get("content")

    if not receiver_id or not content or not content.strip():
        return jsonify({"status": "error", "message": "Введите сообщение"}), 400

    message = Message(
        sender_id=current_user.id,
        receiver_id=receiver_id,
        content=content.strip()
    )
    db.session.add(message)
    db.session.commit()

    return jsonify({
        "status": "success",
        "message": {
            "id": message.id,
            "content": message.content,
            "timestamp": message.created_at.strftime('%H:%M'),
            "created_at_iso": message.created_at.isoformat()
        }
    })

# Чекаем общее количество уведомлений (для хедера)
@chat_bp.route('/api/messages/unread_count')
@login_required
def unread_messages_count():
    count = Message.query.filter_by(receiver_id=current_user.id, is_read=False).count()
    return jsonify({"status": "success", "count": count})