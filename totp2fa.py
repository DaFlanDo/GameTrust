import secrets

import pyotp
import json
import qrcode
import io
import base64
from extensions import fernet
from flask import url_for


def generate_totp_secret():
    """Создаёт и возвращает зашифрованный TOTP секрет."""
    secret = pyotp.random_base32()
    return fernet.encrypt(secret.encode()).decode()


def generate_backup_codes(count=5):
    """Создаёт зашифрованный список кодов восстановления."""
    codes = [secrets.token_hex(5) for _ in range(count)]  # 10 символов
    return fernet.encrypt(json.dumps(codes).encode()).decode()


def verify_totp(user, submitted_code):
    """Проверяет введённый код TOTP."""
    try:
        decrypted_secret = fernet.decrypt(user.twofa_secret.encode()).decode()
        totp = pyotp.TOTP(decrypted_secret)
        return totp.verify(submitted_code)
    except Exception:
        return False


def get_backup_codes(user):
    """Расшифровывает и возвращает список кодов восстановления."""
    try:
        decrypted = fernet.decrypt(user.twofa_backup_codes.encode()).decode()
        return json.loads(decrypted)
    except Exception:
        return []


def use_backup_code(user, submitted_code):
    """Проверяет и удаляет использованный код восстановления."""
    codes = get_backup_codes(user)
    if submitted_code in codes:
        codes.remove(submitted_code)
        user.twofa_backup_codes = fernet.encrypt(json.dumps(codes).encode()).decode()
        return True
    return False


def generate_qr_code(uri):
    qr = qrcode.make(uri)
    buffer = io.BytesIO()
    qr.save(buffer, format='PNG')
    buffer.seek(0)
    img_base64 = base64.b64encode(buffer.read()).decode('utf-8')
    return img_base64


def decrypt_totp_secret(encrypted):
    return fernet.decrypt(encrypted.encode()).decode()
