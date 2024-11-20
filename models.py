from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
import datetime
from datetime import date

# Initialize database instance
db = SQLAlchemy()

# User model
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)
    birthdate = db.Column(db.Date, nullable=False)
    iban = db.Column(db.String(60), nullable=False, default="")
    payment_email_title = db.Column(db.String(250), nullable=False, default="")
    payment_email_body = db.Column(db.Text, nullable=False, default="")
    confirmation_email_title = db.Column(db.String(250), nullable=False, default="")
    confirmation_email_body = db.Column(db.Text, nullable=False, default="")

    # Events created by the user
    created_events = db.relationship("Event", backref="organizer", lazy=True)

    @property
    def age(self):
        today = date.today()
        return today.year - self.birthdate.year - (
            (today.month, today.day) < (self.birthdate.month, self.birthdate.day)
        )

# Event model
class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(250), nullable=False)
    description = db.Column(db.Text, nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    price = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(10), nullable=False)
    paymentaddress = db.Column(db.Text, nullable=False)
    max_attendees = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    payment_email_title = db.Column(db.String(250), nullable=False)
    payment_email_body = db.Column(db.Text, nullable=False)
    confirmation_email_title = db.Column(db.String(250), nullable=False)
    confirmation_email_body = db.Column(db.Text, nullable=False)
    event_meeting_link = db.Column(db.String(250), nullable=True)

    # Relationship to Attendee
    attendees = db.relationship("Attendee", backref="registered_event", lazy=True)

# Attendee model
class Attendee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)

    # Relationship to User
    user = db.relationship("User", backref="attending_events")

    # Relationship to Event
    event = db.relationship("Event", backref="attendee_list")