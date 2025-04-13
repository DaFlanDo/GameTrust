import os
import logging

from cryptography.fernet import Fernet
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

db = SQLAlchemy()
login_manager = LoginManager()
limiter = Limiter(get_remote_address)
fernet = Fernet(os.getenv("FERNET_SECRET_KEY"))
migrate = Migrate()