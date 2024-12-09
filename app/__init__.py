from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_mail import Mail
from flask_login import LoginManager
from dotenv import load_dotenv
from app.models import db, User, Event, Attendee, Vote
import os

# Define the base directory of the project
basedir = os.path.abspath(os.path.dirname(__file__))

# Load environment variables
load_dotenv()
app = Flask(__name__)

# Initialize extensions
# db = SQLAlchemy() 
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
    from app.models import User
    return User.query.get(int(user_id))

# Register routes or blueprints
with app.app_context():
    db.create_all()  # or any operation requiring an app context



from flask import current_app, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_user, current_user, logout_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from app.models import User, Event, Attendee, Vote
import pytz
from pytz import timezone, all_timezones, UTC
from datetime import datetime, timedelta
from flask_mail import Message
from urllib.parse import urlparse
from sqlalchemy import cast, String, func
from sqlalchemy import asc, desc
from dotenv import load_dotenv
import os
from urllib.parse import urlencode

@app.context_processor
def inject_unchecked_confirmations():
    unchecked_confirmations = 0
    if current_user.is_authenticated:
        try:
            unchecked_confirmations = db.session.query(Attendee).join(Event).filter(
                Event.user_id == current_user.id,
                Attendee.attending == False  # Adjust this condition based on your schema
            ).count()
        except Exception as e:
            print(f"Error calculating unchecked confirmations: {e}")  # Log the error for debugging

    return {'unchecked_confirmations': unchecked_confirmations}

@app.context_processor
def inject_timezones():
    from pytz import all_timezones
    from datetime import datetime, timedelta
    return {'timezones': all_timezones, 'timedelta':timedelta}

def is_valid_url(url):
    parsed = urlparse(url)
    return bool(parsed.netloc) and bool(parsed.scheme)

def send_reset_email(user):
    token = user.get_reset_token()
    msg = Message("Password Reset Request",
                  sender=current_app.config['MAIL_DEFAULT_SENDER'],
                  recipients=[user.email])
    msg.body = f"""To reset your password, visit the following link:
{url_for('reset_token', token=token, _external=True)}

If you did not make this request, simply ignore this email and no changes will be made.
"""
    mail.send(msg)



@app.route("/")
def home():
    # Retrieve search and date filter parameters
    query = request.args.get("search", "")
    date_filter = request.args.get("dateFilter", "")  # Check if dateFilter parameter exists
    filter_param = request.args.get("filter", "")  # Get 'filter' parameter
    # Count total registered users
    total_users = User.query.count()

    # Fetch all events as a base query
    events_query = Event.query

    # Adjust event dates to the user's timezone
    events = events_query.order_by(Event.date.asc()).all()
    user_timezone = pytz.timezone(current_user.preferred_timezone if current_user.is_authenticated else "UTC")

    # In your `home` route:
    for event in events:
        # Ensure user_timezone is a pytz timezone object
        if isinstance(user_timezone, str):
            user_tz = timezone(user_timezone)  # User's local timezone
        else:
            user_tz = user_timezone

        # Convert event.date to the user's timezone
        event_tz = timezone(event.tz_name)  # Assuming event.tz_name is "Europe/Brussels"
        event_localized = event.date.astimezone(event_tz)  # Ensure event.date is timezone-aware
        event_user_tz_date = event_localized.astimezone(user_tz)  # Convert to user's timezone

        # Store the converted date in the event for use in the frontend
        event.local_date = event_user_tz_date  # User-localized time
        # Calculate event end time in user's timezone
        event_user_tz_end_date = event_user_tz_date + timedelta(minutes=event.duration)

        # Convert to UTC for calendar URLs
        event_date_utc = event_user_tz_date.astimezone(pytz.UTC)
        event_end_date_utc = event_user_tz_end_date.astimezone(pytz.UTC)

        # Generate Outlook Calendar URL using user's local timezone
        # Generate Outlook Calendar URL
        event.outlook_calendar_url = (
            "https://outlook.live.com/calendar/0/deeplink/compose?" +
            urlencode({
                "path": "/calendar/action/compose",
                "subject": event.title,
                "startdt": event_user_tz_date.isoformat(),  # Localized ISO 8601
                "enddt": event_user_tz_end_date.isoformat(),  # Localized ISO 8601
                "body": f"Meeting Link: {event.event_meeting_link} - {event.description}",
            })
        )

        # Generate Google Calendar URL
        event.google_calendar_url = (
            "https://calendar.google.com/calendar/r/eventedit?" +
            urlencode({
                "text": event.title,
                "dates": f"{event_date_utc.strftime('%Y%m%dT%H%M%SZ')}/{event_end_date_utc.strftime('%Y%m%dT%H%M%SZ')}",
                "details": f"Meeting Link: {event.event_meeting_link} - {event.description}",
                "location": "Online"
            })
        )




    # Mark events as closed if needed
    for event in events_query.all():
        try:
            # Ensure event.date is timezone-aware
            event_date = event.date.astimezone(pytz.timezone(event.tz_name))
            # Compare event date with the current time in the same timezone
            if event_date < datetime.now(pytz.timezone(event.tz_name)) and not event.is_closed:
                event.is_closed = True  # Mark the event as closed
                db.session.add(event)  # Add the updated event to the session
        except Exception as e:
            print(f"Error processing event timestamps for event {event.id}: {e}")

    db.session.commit()

    # Apply filters based on query or date filter
    if query.startswith("host:"):
        host_username = query.split("host:")[1]
        events_query = events_query.join(User).filter(User.username == host_username)
    elif query:
        query_lower = query.lower()  # Convert query to lowercase
        events_query = events_query.join(User).filter(
            func.lower(Event.title).contains(query_lower) |
            func.lower(Event.description).contains(query_lower) |
            func.lower(Event.event_language).contains(query_lower) |
            func.lower(User.username).contains(query_lower) |
            cast(Event.date, String).contains(query)  # Cast Event.date to string
        )
    elif date_filter:
        # Filter by exact date
        try:
            selected_date = datetime.strptime(date_filter, "%Y-%m-%d").date()
            events_query = events_query.filter(
                cast(Event.date, String).like(f"{selected_date}%")
            )
        except ValueError:
            # If dateFilter is invalid, continue without date filtering
            pass

    if filter_param == "attending" and current_user.is_authenticated:
        events_query = events_query.join(Attendee).filter(
            Attendee.user_id == current_user.id,
            Attendee.attending == True
        )

    # Sort events: Open events first by `is_closed`, then by date (ascending)
    events = events_query.order_by(
        asc(Event.is_closed),  # Open events first
        asc(Event.date)        # Earliest dates first for open events
    ).all()



    # Check attendance for the current user
    if current_user.is_authenticated:
        for event in events:
            event.is_attending = any(
                attendee.user_id == current_user.id and attendee.attending
                for attendee in event.attendees
            )
    else:
        for event in events:
            event.is_attending = False


    return render_template(
        "event_list.html",
        events=events,
        query=query,
        datetime=datetime,
        timedelta=timedelta,
        pytz=pytz,
        total_users=total_users,
        user_timezone=user_timezone.zone,
    )



@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = generate_password_hash(request.form["password"])
        birthdate_str = request.form["birthdate"]
        preferred_timezone = request.form["preferred_timezone"]

        # Validate that the username is within the allowed length
        if len(username) > 20:
            flash("Username is too long. Please keep it under 20 characters.", "danger")
            return redirect(url_for('register'))
        
        # Parse the birthdate and validate
        try:
            birthdate = datetime.strptime(birthdate_str, "%Y-%m-%d").date()
        except ValueError:
            flash("Invalid birthdate format. Please use YYYY-MM-DD.", "danger")
            return render_template("register.html")

        # Check if user already exists
        if User.query.filter_by(email=email).first():
            flash("An account with this email already exists.", "danger")
            return render_template("register.html")

        # Create and save new user
        user = User(username=username, email=email, password=password, birthdate=birthdate, preferred_timezone=preferred_timezone) #, iban = "", payment_email_title = "", payment_email_body= "", confirmation_email_title= "", confirmation_email_body= ""
        db.session.add(user)
        db.session.commit()

        flash(f"Account created for {username}! ", "success")  #Your age is {user.age}.
        return redirect(url_for('login'))

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            flash("Login successful!", "success")
            return redirect(url_for("home"))
        flash("Invalid credentials.", "danger")
    return render_template("login.html")



@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out successfully.", "info")
    return redirect(url_for("home"))


@app.route('/reset_request', methods=['GET', 'POST'])
def reset_request():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        email = request.form.get('email')
        user = User.query.filter_by(email=email).first()
        if user:
            send_reset_email(user)  # Sends the email with a reset token
            flash('A password reset email has been sent.', 'info')
        else:
            flash('No account found with that email.', 'danger')
        return redirect(url_for('login'))
    
    return render_template('reset_request.html')  # Form to enter email



@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_token(token):
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    # Verify the token
    user = User.verify_reset_token(token)
    if not user:
        flash('The reset token is invalid or has expired.', 'danger')
        return redirect(url_for('reset_request'))

    # Handle password reset form submission
    if request.method == 'POST':
        new_password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if new_password != confirm_password:
            flash('Passwords do not match.', 'danger')
        else:
            user.password = generate_password_hash(new_password)
            db.session.commit()
            flash('Your password has been reset. You can now log in.', 'success')
            return redirect(url_for('login'))

    return render_template('reset_token.html')  # Form for entering new password



@app.route("/dashboard")
@login_required
def dashboard():
    view = request.args.get("view", "dashboard")
    date_filter = request.args.get("dateFilter", "")  # Ensure date_filter is always initialized

    # Loop through each event to close if date and time are in the past
    # Fetch all events
    events_query = Event.query  # Fetch all events from the database
    for event in events_query.all():
        # Parse the event date
        try:
            # Ensure event.date is timezone-aware
            event_date = event.date.astimezone(pytz.timezone(event.tz_name))
            
            # Compare event date with the current time in the same timezone
            if event_date < datetime.now(pytz.timezone(event.tz_name)) and not event.is_closed:
                event.is_closed = True  # Mark the event as closed
                db.session.add(event)  # Add the updated event to the session
        except Exception as e:
            print(f"Error processing event timestamps /home {event.id}: {e}")


    # Query created events for the current user
    created_events_query = Event.query.filter_by(user_id=current_user.id)
    # Apply date filter
    if date_filter:
        try:
            selected_date = datetime.strptime(date_filter, "%Y-%m-%d").date()
            created_events_query = created_events_query.filter(
                cast(Event.date, String).like(f"{selected_date}%")
            )
        except ValueError:
            flash("Invalid date format.", "danger")

    # Sort events: Open events first by date ascending, closed events by date descending
    created_events = created_events_query.order_by(
        Event.is_closed.asc(),  # Open events first
        Event.date.asc()        # Earliest dates first for open events
    ).all()

    attending_events = Event.query.join(Attendee).filter(Attendee.user_id == current_user.id).all()


    # Pass the list of timezones to the template
    timezones = all_timezones 
    preferred_timezone = current_user.preferred_timezone if current_user.preferred_timezone else 'UTC'
    
    # Filter created_events to only include events that are not closed
    open_events = [event for event in created_events if not event.is_closed]

    # Generate unique event titles with dates for the dropdown
    unique_event_titles = {event.title + " | " + event.date.strftime("%Y-%m-%d %H:%M") for event in open_events}


    # Prepare data for the table
    table_data = []
    for event in created_events:
        for attendee in event.attendees:
            table_data.append({
                "event_id" : event.id,
                "event": event.title,
                "date": event.date.strftime("%Y-%m-%d %H:%M"),
                "meeting_url": event.event_meeting_link,
                "attendee_name": attendee.user.username,
                "attendee_email": attendee.user.email,
                "attendee_age": attendee.user.age,
                "payment_sent": "Yes",
                "payment_amount": event.price,
                "payment_currency": event.currency,
                "payment_adress" : event.paymentaddress,
                "payment_comment": f"Event {event.id} {attendee.user.username}",
                "attendee_id": attendee.id,
                "host_email": current_user.email,
                "confirmation_email_title": current_user.confirmation_email_title,
                "confirmation_email_body": current_user.confirmation_email_body,
                "attending": attendee.attending,
            })


    return render_template(
        "dashboard.html",
        view=view,
        created_events=created_events,
        attending_events=attending_events,
        table_data=table_data,
        timezones=timezones,
        preferred_timezone=preferred_timezone,
        date_filter=date_filter,  # Pass the date filter to the template
        unique_event_titles=unique_event_titles,
    )




@app.route("/edit_profile", methods=["POST"])
@login_required
def edit_profile():
    username = request.form.get("username")
    email = request.form.get("email")
    iban = request.form.get("iban")
    payment_email_title = request.form.get("payment_email_title")
    payment_email_body = request.form.get("payment_email_body")
    confirmation_email_title = request.form.get("confirmation_email_title")
    confirmation_email_body = request.form.get("confirmation_email_body")
    preferred_timezone = request.form.get("preferred_timezone")
    preferred_language = request.form.get("preferred_language")  # Get preferred language
    # Validate the IBAN format (basic validation for demonstration purposes)
    if len(iban) < 3:
        flash("Invalid payment adress format < 3 characters ?.", "danger")
        return redirect(url_for("dashboard"))

    # Update the user's profile
    current_user.username = username
    current_user.email = email
    current_user.iban = iban
    current_user.payment_email_title = payment_email_title
    current_user.payment_email_body = payment_email_body
    current_user.confirmation_email_title = confirmation_email_title
    current_user.confirmation_email_body = confirmation_email_body
    current_user.preferred_timezone = preferred_timezone
    current_user.preferred_language = preferred_language
    # Commit changes to the database
    db.session.commit()
    flash("Profile updated successfully!", "success")
    return redirect(url_for("dashboard", view="create_event"))


@app.route("/create_event", methods=["GET", "POST"])
@login_required
def create_event():
    if request.method == "POST":
        title = request.form.get("title")
        description = request.form.get("description")
        date_str = request.form.get("date")
        hour_str = request.form.get("hour")
        tz_name = request.form.get("timezone")
        duration = request.form.get("duration")
        price = request.form.get("event_price")
        currency = request.form.get("event_currency")
        paymentaddress = request.form.get("event_paymentaddress")
        event_meeting_link = request.form.get("event_meeting_link")  # New Field
        max_attendees = request.form.get("max_attendees")
        payment_email_title = request.form.get("payment_email_title")
        payment_email_body = request.form.get("payment_email_body")
        confirmation_email_title = request.form.get("confirmation_email_title")
        confirmation_email_body = request.form.get("confirmation_email_body")
        event_language = request.form.get("event_language")  # New field
        dont_send_confirmation = request.form.get("dont_send_confirmation", False)  # Checkbox value

        # Validate all fields
        if not title or not description or not date_str or not hour_str or not tz_name or not price or not currency or not paymentaddress or not max_attendees or not event_language:
            flash("All fields are required.", "danger")
            return redirect(url_for("dashboard", view="create_event"))
        
        try:
            duration = int(duration)
            if duration <= 0:
                raise ValueError
        except ValueError:
            flash("Duration must be a positive integer.", "danger")
            return redirect(url_for("dashboard", view="create_event"))
        
        # Combine date and hour into a single datetime object
        try:
            naive_datetime = datetime.strptime(f"{date_str} {hour_str}", "%Y-%m-%d %H:%M")
            event_timezone = timezone(tz_name)
            event_date = event_timezone.localize(naive_datetime, is_dst=None)
            event.date = event_date
        except ValueError:
            flash("Invalid date or time format.", "danger")
            return redirect(url_for("dashboard", view="create_event"))
        except Exception:
            flash("Invalid timezone selected.", "danger")
            return redirect(url_for("dashboard", view="create_event"))

        # Check if the event date is in the past
        if event_date < datetime.now(event_timezone):
            flash("Event date and time cannot be in the past.", "danger")
            return redirect(url_for("dashboard", view="create_event"))
        
        # Validate price and max_attendees as integers
        try:
            price = int(price)
            max_attendees = int(max_attendees)
            if price <= 0 or max_attendees <= 0:
                raise ValueError
        except ValueError:
            flash("Price and Max Attendees must be integers greater than 0.", "danger")
            return redirect(url_for("dashboard", view="create_event"))
        
        # Validate the meeting link
        if not is_valid_url(event_meeting_link):
            flash("Invalid meeting link. Please enter a valid URL.", "danger")
            return redirect(url_for("dashboard", view="create_event"))
        
        # Handle parameters in the payment email if confirmation mail is not sent
        if dont_send_confirmation:
            # Replace confirmation placeholders in payment email
            payment_email_body = payment_email_body.replace("{event_meeting_url}", event_meeting_link)

    
        # Create and save the event
        event = Event(
            title=title,
            description=description,
            date=event_date,
            tz_name=tz_name,     # Store original timezone
            duration=duration, 
            price=price,
            currency=currency,
            event_language=event_language,  # Save language
            paymentaddress=paymentaddress,
            max_attendees=max_attendees,
            event_meeting_link=event_meeting_link,  # Save the meeting link
            payment_email_title=payment_email_title,
            payment_email_body=payment_email_body,
            confirmation_email_title=confirmation_email_title if not dont_send_confirmation else "",
            confirmation_email_body=confirmation_email_body if not dont_send_confirmation else "",
            user_id=current_user.id,
            dont_send_confirmation=bool(dont_send_confirmation)  # Store the value in the database
        )

        db.session.add(event)
        db.session.commit()
        flash("Event created!", "success")
        return redirect(url_for("dashboard", view="created_events"))

    # Prepopulate timezone with the user's preferred timezone
    preferred_timezone = current_user.preferred_timezone if current_user.preferred_timezone else 'UTC'

    return render_template(
        "dashboard.html",
        timezones=all_timezones,  # Pass all timezones to the template
        preferred_timezone=preferred_timezone
    )


@app.route("/edit_event/<int:event_id>", methods=["GET", "POST"])
@login_required
def edit_event(event_id):
    event = Event.query.get_or_404(event_id)
    event_timezone = event.tz_name

    # Ensure only the creator can edit the event
    if event.user_id != current_user.id:
        flash("You are not authorized to edit this event.", "danger")
        return redirect(url_for("dashboard", view="created_events"))

    if request.method == "POST":
        # Update event details
        event.title = request.form.get("title")
        event.description = request.form.get("description")
        date_str = request.form.get("date")
        hour_str = request.form.get("hour")
        tz_name = request.form.get("timezone")
        event.price = request.form.get("event_price")
        event.event_meeting_link = request.form.get("event_meeting_link")
        event.duration = request.form.get("duration")
        event.currency = request.form.get("event_currency")
        event.event_language = request.form.get("event_language")
        event.paymentaddress = request.form.get("event_paymentaddress")
        event.max_attendees = request.form.get("max_attendees")
        event.event_meeting_link = request.form.get("event_meeting_link")
        event.payment_email_title = request.form.get("payment_email_title")
        event.payment_email_body = request.form.get("payment_email_body")
        event.confirmation_email_title = request.form.get("confirmation_email_title")
        event.confirmation_email_body = request.form.get("confirmation_email_body")

        # Combine date and hour into a single datetime object
        try:
            naive_datetime = datetime.strptime(f"{date_str} {hour_str}", "%Y-%m-%d %H:%M")
            event_timezone = timezone(tz_name)
            event_date = event_timezone.localize(naive_datetime, is_dst=None)
            event.date = event_date
        except ValueError:
            flash("Invalid date or time format.", "danger")
            return redirect(url_for("edit_event", event_id=event.id))
        except Exception:
            flash("Invalid timezone selected.", "danger")
            return redirect(url_for("edit_event", event_id=event.id))

        # Validate numeric fields
        try:
            event.price = int(event.price)
            event.max_attendees = int(event.max_attendees)
            if event.price <= 0 or event.max_attendees <= 0:
                raise ValueError
        except ValueError:
            flash("Price and Max Attendees must be positive integers.", "danger")
            return redirect(url_for("edit_event", event_id=event.id))

        # Save changes
        db.session.commit()
        flash("Event updated successfully!", "success")
        return redirect(url_for("dashboard", view="created_events"))

    # Pass event details and timezones for the form
    timezones = all_timezones
    return render_template(
        "edit_event.html",
        event=event,
        timezones=timezones,
        event_timezone=event_timezone
    )




@app.route("/attend_event/<int:event_id>", methods=["GET"])
@login_required
def attend_event(event_id):
    event = Event.query.get_or_404(event_id)

    # Check if the current user is already attending
    if current_user in [attendee.user for attendee in event.attendee_list]:
        flash("You are already subscribed to this event!", "warning")
        return redirect(url_for("home"))


    # Send the email
    host_email = event.organizer.email
    user_email = current_user.email
    payment_email_title = event.payment_email_title
    payment_email_body = event.payment_email_body

    # Replace placeholders in title and body
    placeholders = {
        "{event_title}": event.title,
        "{event_date}": event.date.strftime("%Y-%m-%d %H:%M %Z"),
        "{event_price}": event.price,
        "{event_currency}": event.currency,  # Add currency here
        "{event_meeting_url}" : event.event_meeting_link,
        "{host_iban}": event.paymentaddress,
        "{host_email}": host_email,
        "{event_user}": current_user.username,
        "{host_name}": event.organizer.username, 
        "{comment}": f"Event {event.id} {current_user.username}",  # Add the Comment placeholder
    }

    # Replace placeholders in the email content
    for placeholder, value in placeholders.items():
        payment_email_title = payment_email_title.replace(placeholder, str(value))
        payment_email_body = payment_email_body.replace(placeholder, str(value))

    # Configure the email
    msg = Message(payment_email_title, sender=host_email, recipients=[user_email], cc=[host_email])
    msg.body = payment_email_body

    try:
        mail.send(msg)
        flash("(check SPAM folder : A payment instruction email has been sent to your email address.", "success")
    except Exception as e:
        flash("Failed to send email. Please try again later.", "danger")
        print(f"Email sending failed: {e}")
        return redirect(url_for("home"))

    # Add the user to the event attendees
    attendee = Attendee(user_id=current_user.id, event_id=event.id)
    db.session.add(attendee)
    db.session.commit()

    return redirect(url_for("home"))

@app.route('/send_confirmation_email', methods=['POST'])
@login_required
def send_confirmation_email():
    data = request.get_json()
    event_id = data.get("event_id")
    attendee_email = data.get("attendee_email")
    attendee_name = data.get("attendee_name")
    event_title = data.get("event_title")
    event_date = data.get("event_date")  # Assuming this is in string format
    event_meeting_url = data.get("event_meeting_url")
    host_email = data.get("host_email")
    confirmation_title = data.get("confirmation_title")
    confirmation_body = data.get("confirmation_body")

    from dateutil import parser
    from pytz import timezone

    event = Event.query.get_or_404(event_id)
    try:
        # Ensure the event date is timezone-aware
        selected_timezone = timezone(event.tz_name)
        event_date = event.date.astimezone(selected_timezone)  # Convert to the event's timezone
        event_end_date = event_date + timedelta(hours=1)  # Assume the event lasts 1 hour
    except Exception as e:
        print(f"Error parsing event date: {e}")
        return jsonify({"success": False, "message": "Invalid event date format"}), 400


    from urllib.parse import urlencode
    # Format the dates to include timezone offset (RFC 5545 format)
    event_date_str = event_date.strftime('%Y%m%dT%H%M%S%z')  # e.g., 20231203T150000+0100
    event_end_date_str = event_end_date.strftime('%Y%m%dT%H%M%S%z')  # e.g., 20231203T170000+0100

    # Generate Google Calendar link
    google_calendar_url = (
        "https://calendar.google.com/calendar/r/eventedit?" +
        urlencode({
            "text": event.title,
            "dates": f"{event_date_str}/{event_end_date_str}",  # Include timezone-aware dates
            "details": f"Meeting Link: {event.event_meeting_link} - {event.description}",
            "location": "Online"
        })
    )

    # Generate Outlook Calendar link
    outlook_calendar_url = (
        "https://outlook.live.com/calendar/0/deeplink/compose?" +
        urlencode({
            "path": "/calendar/action/compose",
            "subject": event.title,
            "startdt": event_date.isoformat(),  # ISO 8601 format
            "enddt": event_end_date.isoformat(),  # ISO 8601 format
            "body": f"Meeting Link: {event.event_meeting_link} - {event.description}",
        })
    )

    # Replace placeholders in the email title and body
    placeholders = {
        "{event_user}": attendee_name,
        "{event_title}": event_title,
        "{event_date}": event.date.strftime("%Y-%m-%d %H:%M %Z"),
        "{event_meeting_url}": event_meeting_url,
        "{host_name}": current_user.username,
        "{host_email}": current_user.email,
        "{google_calendar_url}": google_calendar_url,
        "{outlook_calendar_url}": outlook_calendar_url,
    }

    for placeholder, value in placeholders.items():
        confirmation_title = confirmation_title.replace(placeholder, str(value))
        confirmation_body = confirmation_body.replace(placeholder, str(value))

    # Create HTML body for the email
    confirmation_body_html = confirmation_body  # Already HTML-formatted from textarea

    # Find the attendee
    user = User.query.filter_by(email=attendee_email).first()
    if not user:
        return jsonify({"success": False, "message": "User not found"}), 404

    attendee = Attendee.query.join(Event).filter(
        Event.title == event_title,
        Attendee.user_id == user.id
    ).first()

    if not attendee:
        return jsonify({"success": False, "message": "Attendee not found"}), 404

    # Send the email
    msg = Message(confirmation_title, sender=host_email, recipients=[attendee_email])
    msg.body = confirmation_body  # Plain text fallback
    msg.html = confirmation_body_html  # Use the HTML version


    try:
        mail.send(msg)
        attendee.attending = True
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        print(f"Failed to send email: {e}")
        return jsonify({"success": False}), 500


    



@app.route("/close_event/<int:event_id>", methods=["POST"])
@login_required
def close_event(event_id):
    event = Event.query.get_or_404(event_id)

    # Ensure the current user is the organizer of the event
    if event.user_id != current_user.id:
        return jsonify({"success": False, "message": "You are not authorized to close this event."}), 403

    # Mark the event as closed
    event.is_closed = True
    db.session.commit()

    return jsonify({"success": True})


@app.route("/delete_event/<int:event_id>", methods=["GET", "POST"])
@login_required
def delete_event(event_id):
    event = Event.query.get_or_404(event_id)

    # Ensure only the creator can delete the event
    if event.user_id != current_user.id:
        flash("You are not authorized to delete this event.", "danger")
        return redirect(url_for("dashboard", view="created_events"))

    try:
        # Delete all attendees associated with the event
        Attendee.query.filter_by(event_id=event.id).delete()

        # Delete the event itself
        db.session.delete(event)
        db.session.commit()
        flash("Event deleted successfully!", "success")
    except Exception as e:
        flash(f"Error deleting event: {e}", "danger")

    return redirect(url_for("dashboard", view="created_events"))


from flask import Response
from datetime import timedelta

@app.route('/add_to_calendar/<int:event_id>')
@login_required
def add_to_calendar(event_id):
    event = Event.query.get_or_404(event_id)

    # Calculate the end time using the duration
    event_end_date = event.date + timedelta(minutes=event.duration)

    ics_content = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//YourApp//NONSGML v1.0//EN
BEGIN:VEVENT
UID:{event.id}@yourapp.com
DTSTAMP:{event.date.strftime('%Y%m%dT%H%M%SZ')}
DTSTART:{event.date.strftime('%Y%m%dT%H%M%SZ')}
DTEND:{event_end_date.strftime('%Y%m%dT%H%M%SZ')}
SUMMARY:{event.title}
DESCRIPTION:{event.description} - Meeting Link: {event.event_meeting_link}
LOCATION:Online
STATUS:CONFIRMED
SEQUENCE:0
END:VEVENT
END:VCALENDAR
"""

    response = Response(ics_content, mimetype="text/calendar")
    response.headers["Content-Disposition"] = f"attachment; filename={event.title}.ics"
    return response



@app.route('/rate_host/<int:host_id>', methods=['POST'])
@login_required
def rate_host(host_id):
    host = User.query.get_or_404(host_id)

    # Fetch closed events hosted by the host where the current user was an attendee
    closed_events_attended = Attendee.query.join(Event).filter(
        Attendee.user_id == current_user.id,
        Event.user_id == host.id,
        Event.is_closed == True,
        Attendee.attending == True
    ).all()

    max_votes = len(closed_events_attended)  # Max votes allowed based on closed events attended

    # Check how many votes the user has already cast for this host
    votes_cast = Vote.query.filter_by(user_id=current_user.id, host_id=host.id).count()

    if votes_cast >= max_votes:
        flash("You have reached the maximum number of votes for this host.", "danger")
        return redirect(request.referrer)

    # Get the rating value from the form
    rating = request.form.get('rating')
    if not rating:
        flash("No rating selected. Please select a value between 1 and 5.", "danger")
        return redirect(request.referrer)

    try:
        rating = int(rating)
        if rating < 1 or rating > 5:
            raise ValueError
    except ValueError:
        flash("Invalid rating. Please select a value between 1 and 5.", "danger")
        return redirect(request.referrer)

    # Record the vote
    vote = Vote(user_id=current_user.id, host_id=host.id, rating=rating)
    db.session.add(vote)

    # Update host's total rating and voter count
    host.total_rating += rating
    host.total_voters += 1

    db.session.commit()

    flash("Thank you for rating!", "success")
    return redirect(request.referrer)




@app.route('/host/<string:host_username>')
def host_profile(host_username):
    host = User.query.filter_by(username=host_username).first_or_404()

    # Host statistics
    hosted_events = Event.query.filter_by(user_id=host.id, is_closed=True).all()
    hosted_events_count = len(hosted_events)
    total_participants = sum(len(event.attendees) for event in hosted_events)

    # Calculate average rating and total voters
    average_rating = host.average_rating
    total_voters = host.total_voters
    total_rating = host.total_rating


    # Check if the current user is a confirmed attendee
    is_confirmed_attendee = False
    remaining_votes = 0
    max_votes = 0

    if current_user.is_authenticated:
        closed_events_attended = Attendee.query.join(Event).filter(
            Attendee.user_id == current_user.id,
            Event.user_id == host.id,
            Event.is_closed == True,
            Attendee.attending == True
        ).all()
        max_votes = len(closed_events_attended)
        votes_cast = Vote.query.filter_by(user_id=current_user.id, host_id=host.id).count()
        remaining_votes = max(max_votes - votes_cast, 0)
        is_confirmed_attendee = len(closed_events_attended) > 0

    # Pass all relevant data to the template
    return render_template(
        "host_statistics.html",
        host=host,
        hosted_events_count=hosted_events_count,
        total_participants=total_participants,
        is_confirmed_attendee=is_confirmed_attendee,
        remaining_votes=remaining_votes,
        max_votes=max_votes,
        average_rating=average_rating,  # Explicitly pass average rating
        total_voters=total_voters       # Explicitly pass total voters
    )


@app.route("/get_unchecked_count")
@login_required
def get_unchecked_count():
    unchecked_confirmations = db.session.query(Attendee).join(Event).filter(
        Event.user_id == current_user.id,
        Attendee.attending == False
    ).count()
    return jsonify({"count": unchecked_confirmations})


import pandas as pd
from flask import send_file
from io import BytesIO

@app.route('/download_attendee_table')
@login_required
def download_attendee_table():
    # Fetch attendee data
    attendee_data = []
    created_events = Event.query.filter_by(user_id=current_user.id).all()
    for event in created_events:
        for attendee in event.attendees:
            attendee_data.append({
                "Event": event.title,
                "Date": event.date.strftime('%Y-%m-%d %H:%M:%S'),
                "Attendee Name": attendee.user.username,
                "Attendee Email": attendee.user.email,
                "Attendee Age": attendee.user.age,
                "Payment Sent": "Yes" if attendee.attending else "No",
                "Payment Amount": event.price,
                "Currency": event.currency,
                "Payment Address": event.paymentaddress,
                "Payment Comment": f"Event {event.id} {attendee.user.username}",
                "Meeting URL": event.event_meeting_link
            })
    
    # Convert to DataFrame
    df = pd.DataFrame(attendee_data)

    # Write DataFrame to an Excel file in memory
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Attendee Table')

    # Rewind the buffer
    output.seek(0)

    # Send the file to the user
    return send_file(
        output,
        as_attachment=True,
        download_name='attendee_table.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


@app.errorhandler(500)
def internal_server_error(e):
    # Log the error
    current_app.logger.error(f"Server Error: {e}")
    # Optionally, send a notification to admins
    # return a user-friendly response
    return render_template('500.html'), 500



@app.errorhandler(404)
def internal_server_error(e):
    # Log the error
    current_app.logger.error(f"Server Error: {e}")
    # Optionally, send a notification to admins
    # return a user-friendly response
    return render_template('500.html'), 500



