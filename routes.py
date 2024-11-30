from flask import current_app, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_user, current_user, logout_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from .models import User, Event, Attendee, Vote
from .app import db, mail
import pytz
from pytz import timezone, all_timezones
from datetime import datetime, timedelta
from flask_mail import Message
from urllib.parse import urlparse
from sqlalchemy import cast, String
from sqlalchemy import asc, desc

def is_valid_url(url):
    parsed = urlparse(url)
    return bool(parsed.netloc) and bool(parsed.scheme)

@current_app.route("/")
def home():
    # Retrieve search and date filter parameters
    query = request.args.get("search", "")
    date_filter = request.args.get("dateFilter", "")  # Check if dateFilter parameter exists

    # Fetch all events
    events_query = Event.query  # Fetch all events from the database

    # Loop through each event
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

    # Commit changes after the loop
    db.session.commit()

    for event in events_query.all():
        # Count the number of attendees marked as attending
        attending_count = len([attendee for attendee in event.attendees if attendee.attending])

        # Check if the event should be closed
        if attending_count >= event.max_attendees and not event.is_closed:
            event.is_closed = True
            db.session.commit()

    # Apply filters based on query or date filter
    if query.startswith("host:"):
        host_username = query.split("host:")[1]
        events_query = events_query.join(User).filter(User.username == host_username)
    elif query:
        events_query = events_query.join(User).filter(
            Event.title.contains(query) |
            Event.description.contains(query) |
            Event.event_language.contains(query) |
            User.username.contains(query) |
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
        pytz=pytz
    )





@current_app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = generate_password_hash(request.form["password"])
        birthdate_str = request.form["birthdate"]

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
        user = User(username=username, email=email, password=password, birthdate=birthdate) #, iban = "", payment_email_title = "", payment_email_body= "", confirmation_email_title= "", confirmation_email_body= ""
        db.session.add(user)
        db.session.commit()

        flash(f"Account created for {username}! ", "success")  #Your age is {user.age}.
        return redirect(url_for('login'))

    return render_template("register.html")

@current_app.route("/login", methods=["GET", "POST"])
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

@current_app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out successfully.", "info")
    return redirect(url_for("home"))

@current_app.route("/dashboard")
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

    # Prepare data for the table
    table_data = []
    for event in created_events:
        for attendee in event.attendees:
            table_data.append({
                "event_id" : event.id,
                "event": event.title,
                "date": event.date.strftime("%Y-%m-%d %H:%M %Z"),
                "meeting_url": event.event_meeting_link,
                "attendee_name": attendee.user.username,
                "attendee_email": attendee.user.email,
                "attendee_age": attendee.user.age,
                "payment_sent": "Yes",
                "payment_amount": event.price,
                "payment_currency": event.currency,
                "payment_adress" : event.paymentaddress,
                "payment_comment": f"Event {event.id} + {attendee.user.email}",
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
    )


@current_app.route("/edit_profile", methods=["POST"])
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


@current_app.route("/create_event", methods=["GET", "POST"])
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
        event_language = request.form.get("event_language")  # New field
        dont_send_confirmation = request.form.get("dont_send_confirmation", False)  # Checkbox value

        # Validate all fields
        if not title or not description or not date_str or not hour_str or not tz_name or not price or not currency or not paymentaddress or not max_attendees or not event_language:
            flash("All fields are required.", "danger")
            return redirect(url_for("dashboard", view="create_event"))
        
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


@current_app.route("/edit_event/<int:event_id>", methods=["GET", "POST"])
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
        event.currency = request.form.get("event_currency")
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
            selected_timezone = pytz.timezone(tz_name)
            event_date = selected_timezone.localize(naive_datetime)  # Apply the selected timezone
            event.date = event_date  # Update the event's date
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




@current_app.route("/attend_event/<int:event_id>", methods=["GET"])
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

@current_app.route('/send_confirmation_email', methods=['POST'])
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
    # Generate Google Calendar link
    google_calendar_url = (
        "https://calendar.google.com/calendar/r/eventedit?" +
        urlencode({
            "text": event.title,
            "dates": f"{event_date.strftime('%Y%m%dT%H%M%S')}/{event_end_date.strftime('%Y%m%dT%H%M%S')}",
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
            "startdt": event_date.strftime('%Y-%m-%dT%H:%M:%S'),
            "enddt": event_end_date.strftime('%Y-%m-%dT%H:%M:%S'),
            "body": f"Meeting Link: {event.event_meeting_link} - {event.description}",
        })
    )

    # Replace placeholders in the email title and body
    placeholders = {
        "{event_user}": attendee_name,
        "{event_title}": event_title,
        "{event_date}": event_date.strftime('%Y-%m-%d %H:%M:%S'),
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


    



@current_app.route("/close_event/<int:event_id>", methods=["POST"])
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


@current_app.route("/delete_event/<int:event_id>", methods=["GET", "POST"])
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

@current_app.route("/add_to_calendar/<int:event_id>")
@login_required
def add_to_calendar(event_id):
    event = Event.query.get_or_404(event_id)

    # Format the .ics content
    ics_content = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//YourApp//NONSGML v1.0//EN
BEGIN:VEVENT
UID:{event.id}@yourapp.com
DTSTAMP:{event.date.strftime('%Y%m%dT%H%M%SZ')}
DTSTART:{event.date.strftime('%Y%m%dT%H%M%SZ')}
SUMMARY:{event.title}
DESCRIPTION:{event.description} - Meeting Link: {event.event_meeting_link}
LOCATION:Online
STATUS:CONFIRMED
SEQUENCE:0
END:VEVENT
END:VCALENDAR
"""

    # Return the .ics file as a downloadable response
    response = Response(ics_content, mimetype="text/calendar")
    response.headers["Content-Disposition"] = f"attachment; filename={event.title}.ics"
    return response




@current_app.route('/rate_host/<int:host_id>', methods=['POST'])
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
    print('rating: '+rating)
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




@current_app.route('/host/<string:host_username>')
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
    print(total_rating)
    print(average_rating)

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
