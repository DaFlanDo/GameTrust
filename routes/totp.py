# routes/security.py
import base64
import os
import qrcode
import pyotp
import io
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, send_file
from flask_login import login_required, current_user
from extensions import db
from totp2fa import generate_qr_code, get_backup_codes, generate_backup_codes, verify_totp, generate_totp_secret, \
    decrypt_totp_secret, use_backup_code

security_bp = Blueprint('security', __name__)


@security_bp.route('/2fa/setup', methods=['GET', 'POST'])
@login_required
def setup_2fa():
    # Уже подключена — показываем только статус (без бэкап-кодов)
    if current_user.twofa_secret and current_user.is_2fa_enabled:
        return render_template('auth/2fa.html', setup_complete=True)

    # Генерация секретного ключа при первом заходе
    if not current_user.twofa_secret:
        current_user.twofa_secret = generate_totp_secret()
        db.session.commit()

    # Генерация QR-кода
    decrypted_secret = decrypt_totp_secret(current_user.twofa_secret)
    totp = pyotp.TOTP(decrypted_secret)
    otp_auth_url = totp.provisioning_uri(name=current_user.email, issuer_name="GameTrust")
    qr_code = generate_qr_code(otp_auth_url)

    # Обработка формы
    if request.method == 'POST':
        code = request.form.get('code')
        if totp.verify(code):
            current_user.is_2fa_enabled = True

            # 1. генерируем и СРАЗУ сохраняем ЗАШИФРОВАННЫЙ список
            current_user.twofa_backup_codes = generate_backup_codes()
            db.session.commit()

            # 2. а пользователю отдаём уже расшифрованный список
            flash("2FA успешно активирована!", "success")
            return render_template(
                "auth/2fa.html",
                qr_code=None,
                backup_codes=get_backup_codes(current_user),  # ← читаемые коды
                setup_complete=False
            )
        else:
            flash("Неверный код. Попробуйте ещё раз.", "danger")

    return render_template('auth/2fa.html', qr_code=qr_code, setup_complete=False)


@security_bp.route('/2fa/qr.png')
@login_required
def get_2fa_qr():
    if '2fa_secret' not in session:
        return "QR-код не найден", 404
    totp = pyotp.TOTP(session['2fa_secret'])
    otp_auth_url = totp.provisioning_uri(name=current_user.email, issuer_name="GameTrust")
    img = qrcode.make(otp_auth_url)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png')

@security_bp.route('/2fa/disable', methods=['POST'])
@login_required
def disable_2fa():
    totp_code = request.form.get("totp_code")
    backup_code = request.form.get("backup_code")

    if totp_code and verify_totp(current_user, totp_code):
        pass
    elif backup_code and use_backup_code(current_user, backup_code):
        pass
    else:
        flash("Неверный код. Попробуйте снова.", "danger")
        return redirect(url_for('security.setup_2fa'))

    current_user.is_2fa_enabled = False
    current_user.twofa_secret = None
    current_user.twofa_backup_codes = None
    db.session.commit()
    flash("2FA успешно отключена.", "success")
    return redirect(url_for('profile.user_profile', user_id=current_user.id))
