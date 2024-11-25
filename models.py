from flask_sqlalchemy import SQLAlchemy 
from flask_login import UserMixin
from datetime import date
from sqlalchemy import Boolean, String, Text, Integer, DateTime, Date, ForeignKey
from sqlalchemy.sql import expression
from sqlalchemy.orm import relationship
from .app import db

# User model
class User(db.Model, UserMixin):
    id = db.Column(Integer, primary_key=True)
    username = db.Column(String(20), unique=True, nullable=False)
    email = db.Column(String(120), unique=True, nullable=False)
    password = db.Column(String(250), nullable=False)
    birthdate = db.Column(Date, nullable=False)
    iban = db.Column(String(250), nullable=False, default='', server_default='')
    payment_email_title = db.Column(String(250), nullable=False, default='', server_default='')
    payment_email_body = db.Column(Text, nullable=False, default='', server_default='')
    confirmation_email_title = db.Column(String(250), nullable=False, default='', server_default='')
    confirmation_email_body = db.Column(Text, nullable=False, default='', server_default='')

    # Events created by the user
    created_events = relationship("Event", backref="organizer", lazy=True)

    @property
    def age(self):
        today = date.today()
        return today.year - self.birthdate.year - (
            (today.month, today.day) < (self.birthdate.month, self.birthdate.day)
        )

# Event model
class Event(db.Model):
    id = db.Column(Integer, primary_key=True)
    title = db.Column(String(250), nullable=False)
    description = db.Column(Text, nullable=False)
    date = db.Column(DateTime, nullable=False)
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
