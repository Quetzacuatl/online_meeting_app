from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_mail import Mail
from flask_login import LoginManager
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()
app = Flask(__name__)

# Define the base directory of the project
basedir = os.path.abspath(os.path.dirname(__file__))

# Initialize extensions
db = SQLAlchemy()
migrate = Migrate()
mail = Mail()
login_manager = LoginManager()

# Load configuration from environment variables
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default_secret_key')
app.config['FLASK_ENV'] = os.getenv('FLASK_ENV', 'dev')

# Database Configuration
if app.config['FLASK_ENV'] == 'dev':
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DEV_DATABASE_URL')
else:
    # Database Configuration
    database_url = os.getenv('DATABASE_URL')
        # Fix for Heroku database URL
    if database_url and database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url or os.getenv('PROD_DATABASE_URL')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Mail Configuration
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'True').lower() == 'true'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER', 'noreply@demo.com')

# Initialize extensions with the app
db.init_app(app)
migrate.init_app(app, db)
mail.init_app(app)
login_manager.init_app(app)
login_manager.login_view = 'login'

# Define user loader for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    from .models import User
    return User.query.get(int(user_id))

# Register routes or blueprints
with app.app_context():
    
    if app.config['FLASK_ENV'] == 'dev':
        from .routes import * # Import routes after app is fully initialized
        db.create_all()  # For development purposes only
    else:
        import routes # Import routes after app is fully initialized



if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))  # Heroku provides the PORT, locally defaults to 5000
    app.run(debug=True, host="0.0.0.0", port=port)
