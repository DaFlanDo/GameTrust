from flask_limiter import Limiter
from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_limiter.util import get_remote_address
from flask_login import login_user, logout_user, current_user, login_required
from werkzeug.security import check_password_hash, generate_password_hash
from extensions import db, limiter, get_serializer, send_confirmation_email
from models import User
from forms import LoginForm, RegisterForm
from totp2fa import verify_totp, use_backup_code

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('lot.home'))

    form = LoginForm()
    show_2fa_modal = False
    user = None

    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()

        # Первый этап — проверка пароля
        if user and check_password_hash(user.password, form.password.data):
            if user.is_2fa_enabled:
                # Проверка, был ли введён TOTP или резервный код
                totp_code = request.form.get("totp_code")
                backup_code = request.form.get("backup_code")
                print("TOTP submitted:", totp_code)
                print("Backup code submitted:", backup_code)

                if totp_code and verify_totp(user, totp_code):
                    print("✅ TOTP verification passed")
                    login_user(user)
                    return redirect(url_for('lot.home'))
                elif backup_code and use_backup_code(user, backup_code):
                    print("✅ Backup code verification passed")
                    db.session.commit()
                    login_user(user)
                    return redirect(url_for('lot.home'))
                else:
                    show_2fa_modal = True
                    flash("Введите корректный TOTP-код или резервный код.", "danger")
            else:
                login_user(user)
                return redirect(url_for('lot.home'))
        else:
            flash("Неверный email или пароль.", "danger")

    return render_template('auth/login.html', form=form, show_2fa_modal=show_2fa_modal)



@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('lot.home'))

    form = RegisterForm()
    if form.validate_on_submit():
        if User.query.filter_by(email=form.email.data).first():
            flash('Email уже зарегистрирован!', 'danger')
            return redirect(url_for('auth.register'))
        if User.query.filter_by(username=form.username.data).first():
            flash('Имя уже занято!', 'danger')
            return redirect(url_for('auth.register'))

        hashed_pw = generate_password_hash(form.password.data)
        new_user = User(
            username=form.username.data,
            email=form.email.data,
            password=hashed_pw,
            is_confirmed=False
        )
        db.session.add(new_user)
        db.session.commit()

        flash('Регистрация прошла успешно. Теперь вы можете войти.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html', form=form)
@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('lot.home'))


# Подтверждение почты
@auth_bp.route('/confirm/<token>')
def confirm_email(token):
    s = get_serializer()
    from itsdangerous import SignatureExpired, BadSignature
    try:
        email = s.loads(token, salt='email-confirm', max_age=3600)
    except SignatureExpired:
        flash("⏰ Срок действия ссылки истёк. Запросите новую.", "danger")
        return redirect(url_for('auth.login'))
    except BadSignature:
        flash("Неверная или повреждённая ссылка.", "danger")
        return redirect(url_for('auth.login'))

    user = User.query.filter_by(email=email).first_or_404()

    if user.is_confirmed:
        flash("Email уже подтверждён!", "info")
    else:
        user.is_confirmed = True
        db.session.commit()
        flash("✅ Email успешно подтверждён!", "success")

    return redirect(url_for('auth.login'))


# Отправка письма для подтверждения почты
@auth_bp.route('/send_confirmation', methods=['POST'])
@login_required
def send_confirmation():
    if current_user.is_confirmed:
        flash("Email уже подтверждён.", "info")
        return redirect(url_for('lot.home'))

    s = get_serializer()
    token = s.dumps(current_user.email, salt='email-confirm')
    confirm_url = url_for('auth.confirm_email', token=token, _external=True)
    send_confirmation_email(current_user.email, confirm_url)

    flash("📧 Письмо с подтверждением повторно отправлено!", "info")
    return redirect(url_for('auth.login'))