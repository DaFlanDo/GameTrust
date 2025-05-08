import os
from dotenv import load_dotenv


load_dotenv()

class Config:

    SECRET_KEY = os.getenv("SECRET_KEY")
    SQLALCHEMY_ECHO = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('SQLALCHEMY_DATABASE_URI')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static/uploads')
    FERNET_SECRET_KEY = os.getenv("FERNET_SECRET_KEY")
    RATELIMIT_ENABLED = False
    SMTP_SERVER = os.getenv('SMTP_SERVER') # или другой SMTP
    SMTP_PORT = os.getenv("SMTP_PORT")
    SMPT_USER = os.getenv("SMPT_USER")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
