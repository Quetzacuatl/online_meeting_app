from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, current_user, logout_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from app import app, db, login_manager, mail
from models import User, Event, Attendee
from pytz import timezone, all_timezones
from datetime import datetime
from flask import flash
from urllib.parse import urlparse
from app import mail
from flask_mail import Message

def is_valid_url(url):
    parsed = urlparse(url)
    return bool(parsed.netloc) and bool(parsed.scheme)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route("/")
def home():
    query = request.args.get("search", "")
    if query:
        events = Event.query.filter(
            Event.title.contains(query) | Event.description.contains(query)
        ).all()
    else:
        events = Event.query.all()
    return render_template("event_list.html", events=events, query=query)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = generate_password_hash(request.form["password"])
        birthdate_str = request.form["birthdate"]

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
        user = User(username=username, email=email, password=password, birthdate=birthdate)
        db.session.add(user)
        db.session.commit()

        flash(f"Account created for {username}! Your age is {user.age}.", "success")
        return redirect(url_for("login"))

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
            return redirect(url_for("dashboard"))
        flash("Invalid credentials.", "danger")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out successfully.", "info")
    return redirect(url_for("home"))

@app.route("/dashboard")
@login_required
def dashboard():
    view = request.args.get("view", "dashboard")
    created_events = Event.query.filter_by(user_id=current_user.id).all()
    attending_events = Event.query.join(Attendee).filter(Attendee.user_id == current_user.id).all()

    # Prepare data for the table
    table_data = []
    for event in created_events:
        for attendee in event.attendees:
            table_data.append({
                "event": event.title,
                "date": event.date.strftime("%Y-%m-%d %H:%M %Z"),
                "meeting_url": event.event_meeting_link,
                "attendee_name": attendee.user.username,
                "attendee_email": attendee.user.email,
                "payment_sent": "Yes",
                "payment_comment": f"{event.id} + {attendee.user.email}"
            })

    return render_template("dashboard.html", view=view, created_events=created_events, attending_events=attending_events, table_data=table_data)


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

    # Commit changes to the database
    db.session.commit()
    flash("Profile updated successfully!", "success")
    return redirect(url_for("dashboard"))


@app.route("/create_event", methods=["GET", "POST"])
@login_required
def create_event():
    if request.method == "POST":
        title = request.form.get("title")
        description = request.form.get("description")
        date_str = request.form.get("date")
        hour_str = request.form.get("hour")
        tz_name = request.form.get("timezone")
        price = request.form.get("event_price")
        currency = request.form.get("event_currency")
        paymentaddress = request.form.get("event_paymentaddress")
        event_meeting_link = request.form.get("event_meeting_link")  # New Field
        max_attendees = request.form.get("max_attendees")
        payment_email_title = request.form.get("payment_email_title")
        payment_email_body = request.form.get("payment_email_body")
        confirmation_email_title = request.form.get("confirmation_email_title")
        confirmation_email_body = request.form.get("confirmation_email_body")

        # Validate data (optional)
        if not title or not description or not date_str or not hour_str or not tz_name or not price or not paymentaddress or not max_attendees or not event_meeting_link or not payment_email_title or not payment_email_body or not confirmation_email_title or not confirmation_email_body:
            flash("All fields are required.", "danger")
            return redirect(url_for('home'))
        
        # Combine date and hour into a single datetime object
        try:
            naive_datetime = datetime.strptime(f"{date_str} {hour_str}", "%Y-%m-%d %H:%M")
            event_timezone = timezone(tz_name)
            event_date = event_timezone.localize(naive_datetime)  # Apply the selected timezone
        except ValueError:
            flash("Invalid date or time format.", "danger")
            return redirect(url_for("dashboard", view="create_event"))
        except Exception:
            flash("Invalid timezone selected.", "danger")
            return redirect(url_for("dashboard", view="create_event"))


        # Check if the event date is in the past
        # Validate that the event date is not in the past
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
            return redirect(url_for("dashboard", view="dashboard"))
        
        # Validate the meeting link
        if not is_valid_url(event_meeting_link):
            flash("Invalid meeting link. Please enter a valid URL.", "danger")
            return redirect(url_for("dashboard", view="dashboard"))
    
        # Create and save the event
    # Create and save the event
        event = Event(
            title=title,
            description=description,
            date=event_date,
            price=price,
            currency=currency,
            paymentaddress=paymentaddress,
            max_attendees=max_attendees,
            event_meeting_link=event_meeting_link,  # Save the meeting link
            payment_email_title=payment_email_title,
            payment_email_body=payment_email_body,
            confirmation_email_title=confirmation_email_title,
            confirmation_email_body=confirmation_email_body,
            user_id=current_user.id
        )

        db.session.add(event)
        db.session.commit()
        flash("Event created!", "success")
        return redirect(url_for("dashboard"))
    return render_template("dashboard.html")

@app.route("/edit_event/<int:event_id>", methods=["GET", "POST"])
@login_required
def edit_event(event_id):
    event = Event.query.get_or_404(event_id)

    # Ensure only the creator can edit the event
    if event.user_id != current_user.id:
        flash("You are not authorized to edit this event.", "danger")
        return redirect(url_for("dashboard", view="dashboard"))

    if request.method == "POST":
        # Update event details
        event.title = request.form.get("title")
        event.description = request.form.get("description")
        date_str = request.form.get("date")              
        hour_str = request.form.get("hour")
        tz_name = request.form.get("timezone")
        event.price = request.form.get("event_price")
        event.currency = request.form.get("event_currency")
        event.paymentaddress = request.form.get("event_paymentaddress")
        event.max_attendees = request.form.get("max_attendees")
        event.event_meeting_link = request.form.get("event_meeting_link")
        event.payment_email_title = request.form.get("payment_email_title")
        event.payment_email_body = request.form.get("payment_email_body")
        event.confirmation_email_title = request.form.get("confirmation_email_title")
        event.confirmation_email_body = request.form.get("confirmation_email_body")

        # Validate numeric fields
        try:
            event.price = int(event.price)
            event.max_attendees = int(event.max_attendees)
            if event.price <= 0 or event.max_attendees <= 0:
                raise ValueError
        except ValueError:
            flash("Price and Max Attendees must be positive integers.", "danger")
            return redirect(url_for("edit_event", event_id=event.id))

        # Combine date and hour into a single datetime object
        try:
            naive_datetime = datetime.strptime(f"{date_str} {hour_str}", "%Y-%m-%d %H:%M")
            event_timezone = timezone(tz_name)
            event_date = event_timezone.localize(naive_datetime)  # Apply the selected timezone
        except ValueError:
            flash("Invalid date or time format.", "danger")
            return redirect(url_for("dashboard", view="create_event"))
        except Exception:
            flash("Invalid timezone selected.", "danger")
            return redirect(url_for("dashboard", view="create_event"))
        
        # Validate that the event date is not in the past
        if event_date < datetime.now(event_timezone):
            flash("Event date and time cannot be in the past.", "danger")
            return redirect(url_for("dashboard", view="create_event"))

        # Save changes
        db.session.commit()
        flash("Event updated successfully!", "success")
        return redirect(url_for("dashboard", view="dashboard"))

    # Prepopulate the edit form with event data
    return render_template("edit_event.html", event=event)


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
        "{event_date}": event.date.strftime("%Y-%m-%d %H:%M"),
        "{event_price}": event.price,
        "{event_currency}": event.currency,  # Add currency here
        "{host_iban}": event.paymentaddress,
        "{host_email}": host_email,
        "{event_user}": current_user.username,
        "{host_name}": event.organizer.username, 
        "{comment}": f"Event {event.id} {current_user.email}",  # Add the Comment placeholder
    }

    # Replace placeholders in the email content
    for placeholder, value in placeholders.items():
        payment_email_title = payment_email_title.replace(placeholder, str(value))
        payment_email_body = payment_email_body.replace(placeholder, str(value))

    # Configure the email
    msg = Message(payment_email_title, sender=host_email, recipients=[user_email])
    msg.body = payment_email_body

    try:
        mail.send(msg)
        flash("A payment instruction email has been sent to your email address.", "success")
    except Exception as e:
        flash("Failed to send email. Please try again later.", "danger")
        print(f"Email sending failed: {e}")
        return redirect(url_for("home"))

    # Add the user to the event attendees
    attendee = Attendee(user_id=current_user.id, event_id=event.id)
    db.session.add(attendee)
    db.session.commit()

    return redirect(url_for("home"))