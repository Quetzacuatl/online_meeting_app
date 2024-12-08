from flask_sqlalchemy import SQLAlchemy 
from flask_login import UserMixin
from datetime import date
from sqlalchemy import Boolean, String, Text, Integer, DateTime, Date, ForeignKey
from sqlalchemy.sql import expression
from sqlalchemy.orm import relationship
from app import db
from pytz import timezone
from sqlalchemy.types import TIMESTAMP
from itsdangerous import URLSafeTimedSerializer
from flask import current_app




# User model
class User(db.Model, UserMixin):
    id = db.Column(Integer, primary_key=True)
    username = db.Column(String(50), unique=True, nullable=False)
    email = db.Column(String(120), unique=True, nullable=False)
    password = db.Column(String(250), nullable=False)
    birthdate = db.Column(Date, nullable=False)
    iban = db.Column(String(250), nullable=False, default='', server_default='')
    payment_email_title = db.Column(String(250), nullable=False, default='', server_default='')
    payment_email_body = db.Column(Text, nullable=False, default='', server_default='')
    confirmation_email_title = db.Column(String(250), nullable=False, default='', server_default='')
    confirmation_email_body = db.Column(Text, nullable=False, default='', server_default='')
    preferred_timezone = db.Column(db.String(50), nullable=False, server_default='UTC') 
    preferred_language = db.Column(db.String(10), nullable=False, server_default="en")  # Default to English

    # New fields for rating
    total_rating = db.Column(Integer, default=0, nullable=False, server_default="0")  # Sum of all ratings
    total_voters = db.Column(Integer, default=0, nullable=False, server_default="0")  # Count of voters

    @property
    def average_rating(self):
        return round(self.total_rating / self.total_voters, 2) if self.total_voters > 0 else 0


    # Events created by the user
    created_events = relationship("Event", backref="organizer", lazy=True)

    @property
    def age(self):
        today = date.today()
        return today.year - self.birthdate.year - (
            (today.month, today.day) < (self.birthdate.month, self.birthdate.day)
        )
    
    def get_reset_token(self, expires_in=3600):
        s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
        return s.dumps({'user_id': self.id})

    @staticmethod
    def verify_reset_token(token):
        s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
        try:
            user_id = s.loads(token, max_age=3600)['user_id']
        except Exception:
            return None
        return User.query.get(user_id)

# Event model
class Event(db.Model):
    id = db.Column(Integer, primary_key=True)
    title = db.Column(String(250), nullable=False)
    description = db.Column(Text, nullable=False)
    date = db.Column(TIMESTAMP(timezone=True), nullable=False)  # Use timezone-aware DateTime
    tz_name = db.Column(String(50), nullable=False, server_default='UTC') # Timezone, e.g., "Europe/Brussels"
    duration = db.Column(db.Integer, nullable=False, default=60)  # Duration in minutes
    price = db.Column(Integer, nullable=False)
    currency = db.Column(String(10), nullable=False)
    event_language = db.Column(String(50), nullable=False)  # New field for language
    paymentaddress = db.Column(Text, nullable=False)
    max_attendees = db.Column(Integer, nullable=False)
    user_id = db.Column(Integer, ForeignKey("user.id"), nullable=False)
    payment_email_title = db.Column(String(250), nullable=False)
    payment_email_body = db.Column(Text, nullable=False)
    confirmation_email_title = db.Column(String(250), nullable=False)
    confirmation_email_body = db.Column(Text, nullable=False)
    event_meeting_link = db.Column(String(250), nullable=True)
    is_closed = db.Column(Boolean, server_default=expression.false())  # Use SQLAlchemy expression for default value
    dont_send_confirmation = db.Column(Boolean, nullable=False, server_default=expression.false())  # New field

    # Relationship to Attendee
    attendees = relationship("Attendee", backref="registered_event", lazy=True, cascade="all, delete-orphan")
    

# Attendee model
class Attendee(db.Model):
    id = db.Column(Integer, primary_key=True)
    user_id = db.Column(Integer, ForeignKey('user.id'), nullable=False)
    event_id = db.Column(Integer, ForeignKey('event.id'), nullable=False)
    attending = db.Column(Boolean, server_default=expression.false())  # Use SQLAlchemy expression for default value

    # Relationship to User
    user = relationship("User", backref="attending_events")

    # Relationship to Event
    event = relationship("Event", backref="attendee_list")


class Vote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # The voter
    host_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # The host being rated
    rating = db.Column(db.Integer, nullable=False)  # Rating value

    # Relationships
    user = db.relationship('User', foreign_keys=[user_id], backref='votes_cast')  # Votes cast by the user
    host = db.relationship('User', foreign_keys=[host_id], backref='received_votes')  # Votes received by the host

