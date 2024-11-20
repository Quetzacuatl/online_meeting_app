import os

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "your_secret_key"
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(basedir, 'instance', 'site.db')}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    MAIL_SERVER = 'smtp.gmail.com'  # Update to your email provider's SMTP server
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = 'vbogaert.pieter@gmail.com'
    MAIL_PASSWORD = 'psnm yjhm sqru vmiz'  # Use app-specific passwords if 2FA is enabled
    MAIL_DEFAULT_SENDER = 'your_email@gmail.com'


