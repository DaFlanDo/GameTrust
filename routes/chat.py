import time
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, abort, jsonify
from flask_login import login_required, current_user
from sqlalchemy import desc, func, case, and_, or_

from extensions import db
from models import User, Message

chat_bp = Blueprint('chat', __name__)


@chat_bp.route('/messages')
@login_required
def message_list():
    # Оптимизированный запрос для получения последних сообщений
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

    # Получаем сообщения с предзагрузкой пользователей
    last_messages = (
        db.session.query(Message)
        .join(subquery, Message.id == subquery.c.last_msg_id)
        .join(User, or_(
            Message.sender_id == User.id,
            Message.receiver_id == User.id
        ))
        .options(db.joinedload(Message.sender), db.joinedload(Message.receiver))
        .order_by(desc(Message.created_at))
        .all()
    )

    # Формируем список диалогов
    dialogs = []
    for msg in last_messages:
        other_user = msg.receiver if msg.sender_id == current_user.id else msg.sender
        dialogs.append({
            'user': other_user,
            'message': msg
        })

    return render_template('messages.html', dialogs=dialogs)


@chat_bp.route('/messages/<int:user_id>')
@login_required
def chat_with_user(user_id):
    other_user = User.query.get_or_404(user_id)

    # Защита от попытки чата с самим собой
    if other_user.id == current_user.id:
        abort(403)

    # Получаем все сообщения между пользователями
    messages = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.receiver_id == other_user.id)) |
        ((Message.sender_id == other_user.id) & (Message.receiver_id == current_user.id))
    ).order_by(Message.created_at.asc()).all()

    # Помечаем непрочитанные сообщения от другого пользователя как прочитанные
    unread = [msg for msg in messages if msg.receiver_id == current_user.id and not msg.is_read]
    for msg in unread:
        msg.is_read = True
    db.session.commit()

    return render_template('chat.html', messages=messages, other_user=other_user)


@chat_bp.route('/api/messages/longpoll/<int:user_id>')
@login_required
def long_poll_messages(user_id):
    last_timestamp = request.args.get("after")

    if not last_timestamp:
        return jsonify({"status": "error", "message": "No timestamp provided"}), 400

    try:
        last_dt = datetime.strptime(last_timestamp, '%Y-%m-%dT%H:%M:%S.%fZ')
    except ValueError:
        return jsonify({"status": "error", "message": "Invalid timestamp"}), 400

    timeout = 30  # Максимальное ожидание 30 сек
    interval = 1  # Проверка каждую секунду
    waited = 0

    while waited < timeout:
        new_messages = Message.query.filter(
            and_(
                or_(
                    and_(Message.sender_id == current_user.id, Message.receiver_id == user_id),
                    and_(Message.sender_id == user_id, Message.receiver_id == current_user.id)
                ),
                Message.created_at > last_dt
            )
        ).order_by(Message.created_at.asc()).all()

        if new_messages:
            return jsonify({
                "status": "success",
                "messages": [
                    {
                        "sender_id": m.sender_id,
                        "content": m.content,
                        "timestamp": m.created_at.strftime('%d.%m.%Y %H:%M'),
                        "created_at_raw": m.created_at.isoformat() + 'Z',
                        "is_system": m.is_system
                    } for m in new_messages
                ]
            })

        time.sleep(interval)
        waited += interval

    return jsonify({"status": "timeout", "messages": []})

@chat_bp.route('/send_message', methods=['POST'])
@login_required
def send_message():
    data = request.get_json()
    receiver_id = data.get("receiver_id")
    content = data.get("content")

    if not receiver_id or not content:
        return jsonify({"status": "error", "message": "Недостаточно данных"}), 400

    message = Message(
        sender_id=current_user.id,
        receiver_id=receiver_id,
        content=content
    )
    db.session.add(message)
    db.session.commit()

    return jsonify({
        "status": "success",
        "timestamp": message.created_at.strftime('%d.%m.%Y %H:%M')
    })