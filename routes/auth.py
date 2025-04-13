from flask_limiter import Limiter
from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_limiter.util import get_remote_address
from flask_login import login_user, logout_user, current_user, login_required
from werkzeug.security import check_password_hash, generate_password_hash
from extensions import db, limiter
from models import User
from forms import LoginForm, RegisterForm
auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('lot.home'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and check_password_hash(user.password, form.password.data):
            login_user(user)
            next_page = request.args.get('next')
            if not next_page or not next_page.startswith('/'):
                next_page = url_for('lot.home')
            return redirect(next_page)
        flash('Неверный email или пароль', 'danger')
        return render_template('login.html', form=form), 401  # 👈
    return render_template('login.html', form=form)

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
        new_user = User(username=form.username.data, email=form.email.data, password=hashed_pw)
        db.session.add(new_user)
        db.session.commit()
        flash('Регистрация прошла успешно. Теперь войдите!', 'success')
        return redirect(url_for('auth.login'))

    return render_template('register.html', form=form)

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('lot.home'))

