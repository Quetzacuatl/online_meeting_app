from flask import Flask
from config import Config
from models import db
from flask_login import LoginManager
from flask_mail import Mail
from flask_migrate import Migrate

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(Config)
mail = Mail(app) # Initialize Flask-Mail
migrate = Migrate(app, db)


# Initialize database
db.init_app(app)

# Set up Flask-Login
login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    from models import User
    return User.query.get(int(user_id))  # Load the user from the database

# Import routes (after app and db are initialized)
with app.app_context():
    from routes import *
    db.create_all()  # Ensure database tables are created

if __name__ == "__main__":
    app.run(debug=True)
