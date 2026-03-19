import json
from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify
from flask_login import login_required, current_user
from extensions import db
from models.car import Car
from models.booking import Booking
from models.other_models import Review
from services.cloudinary_service import upload_image
from utils.helpers import log_action, push_notification
from services.email_service import send_booking_cancellation_email

client_bp = Blueprint('client', __name__)


# ── Client Dashboard ──────────────────────────────────────────────

@client_bp.route('/client-dashboard', methods=['GET', 'POST'])
@login_required
def client_dashboard():
    if current_user.role != 'Client':
        return redirect(url_for('main.home'))

    if request.method == 'POST':
        try:
            name     = request.form.get('name', '').strip()
            price    = request.form.get('price', '').strip()
            location = request.form.get('location', '').strip()

            if not name:
                flash('Car name is required.', 'danger')
                return redirect(url_for('client.client_dashboard'))
            if not price or not price.isdigit() or int(price) <= 0:
                flash('A valid price per day is required.', 'danger')
                return redirect(url_for('client.client_dashboard'))
            if not location:
                flash('Location is required.', 'danger')
                return redirect(url_for('client.client_dashboard'))

            # ── Image: Cloudinary first, then URL fallback ──
            final_image = None

            # 1. Try direct file upload via Cloudinary
            file_obj = request.files.get('car_image_file')
            if file_obj and file_obj.filename:
                final_image = upload_image(file_storage=file_obj, folder='drivex/cars')

            # 2. Try base64 data URI via Cloudinary
            if not final_image:
                b64 = request.form.get('image_base64', '').strip()
                if b64 and b64.startswith('data:image'):
                    final_image = upload_image(base64_data=b64, folder='drivex/cars')

            # 3. Plain URL fallback
            if not final_image:
                final_image = request.form.get('image_url', '').strip() or '/static/images/car_placeholder.jpg'

            seats = request.form.get('seats', '5').strip()
            seats = int(seats) if seats.isdigit() else 5

            db.session.add(Car(
                owner_id      = current_user.id,
                name          = name,
                price_per_day = int(price),
                image_url     = final_image,
                category      = request.form.get('category', 'Sedan'),
                location      = location,
                transmission  = request.form.get('transmission', 'Auto'),
                fuel_type     = request.form.get('fuel_type', 'Petrol'),
                seats         = seats,
                status        = 'Pending',
            ))
            db.session.commit()
            log_action("Car Listed", f"Client listed car: {name}")
            flash('Car submitted for Admin approval!', 'success')

        except ValueError as e:
            db.session.rollback()
            flash(f'Invalid value in form: {e}', 'danger')
        except Exception as e:
            db.session.rollback()
            print(f"[client_dashboard POST error] {e}")
            flash('An error occurred while adding your car. Please try again.', 'danger')

        return redirect(url_for('client.client_dashboard'))

    # ── Build analytics ──
    my_cars = Car.query.filter_by(owner_id=current_user.id).all()
    car_ids = [c.id for c in my_cars]

    total_earnings        = 0
    active_bookings_count = 0
    total_trips           = 0
    monthly_earnings      = {m: 0 for m in range(1, 13)}
    car_stats             = []

    if car_ids:
        bookings = Booking.query.filter(
            Booking.car_id.in_(car_ids),
            Booking.status != 'Cancelled',
        ).all()
        total_earnings        = sum(b.total_cost or 0 for b in bookings)
        active_bookings_count = sum(1 for b in bookings if b.status in ['Confirmed', 'Paid'])
        total_trips           = len(bookings)
        for b in bookings:
            if b.date_booked:
                monthly_earnings[b.date_booked.month] += b.total_cost or 0
        for car in my_cars:
            car_bookings = [b for b in bookings if b.car_id == car.id]
            car_stats.append({
                'car':      car,
                'trips':    len(car_bookings),
                'earnings': sum(b.total_cost or 0 for b in car_bookings),
                'active':   sum(1 for b in car_bookings if b.status in ['Confirmed', 'Paid']),
            })

    monthly_chart = json.dumps(list(monthly_earnings.values()))

    # Bookings on client's cars (for cancellation management)
    active_car_bookings = []
    if car_ids:
        active_car_bookings = Booking.query.filter(
            Booking.car_id.in_(car_ids),
            Booking.status.in_(['Confirmed', 'Paid', 'Upcoming']),
        ).order_by(Booking.date_booked.desc()).all()

    return render_template('client_dashboard.html',
        cars                  = my_cars,
        car_stats             = car_stats,
        total_earnings        = total_earnings,
        active_bookings_count = active_bookings_count,
        total_trips           = total_trips,
        monthly_chart         = monthly_chart,
        active_car_bookings   = active_car_bookings,
    )


# ── Edit car (client) ─────────────────────────────────────────────

@client_bp.route('/client/cars/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def client_edit_car(id):
    if current_user.role != 'Client':
        return redirect(url_for('main.home'))
    car = Car.query.get_or_404(id)
    if car.owner_id != current_user.id:
        return redirect(url_for('client.client_dashboard'))

    if request.method == 'POST':
        car.name          = request.form.get('name')
        car.price_per_day = int(request.form.get('price'))
        car.category      = request.form.get('category')
        car.location      = request.form.get('location')

        # ── Image update with Cloudinary ──
        new_image = None

        file_obj = request.files.get('car_image_file')
        if file_obj and file_obj.filename:
            new_image = upload_image(file_storage=file_obj, folder='drivex/cars')

        if not new_image:
            b64 = request.form.get('image_base64', '').strip()
            if b64 and b64.startswith('data:image'):
                new_image = upload_image(base64_data=b64, folder='drivex/cars')

        if not new_image:
            url_input = request.form.get('image_url', '').strip()
            if url_input:
                new_image = url_input

        if new_image:
            car.image_url = new_image

        car.status = 'Pending'
        db.session.commit()
        log_action("Car Updated", f"Client updated car: {car.name}")
        flash('Car updated! Sent to Admin for re-approval.', 'success')
        return redirect(url_for('client.client_dashboard'))

    return render_template('client_edit_car.html', car=car)


# ── Delete car (client) ───────────────────────────────────────────

@client_bp.route('/client/cars/delete/<int:id>')
@login_required
def client_delete_car(id):
    if current_user.role != 'Client':
        return redirect(url_for('main.home'))
    car = Car.query.get_or_404(id)
    if car.owner_id == current_user.id:
        try:
            Review.query.filter_by(car_id=id).delete()
            Booking.query.filter_by(car_id=id).delete()
            db.session.delete(car)
            db.session.commit()
            flash('Car removed from your fleet.', 'success')
        except Exception:
            db.session.rollback()
    return redirect(url_for('client.client_dashboard'))


# ── Cancel booking (customer & client self-service) ───────────────

@client_bp.route('/booking/cancel/<int:booking_id>', methods=['POST'])
@login_required
def cancel_booking(booking_id):
    """
    Allow the renter OR the car owner (client) to cancel,
    provided the trip hasn't started yet and is in a cancellable state.
    """
    booking = Booking.query.get_or_404(booking_id)

    is_renter = booking.user_id == current_user.id
    is_owner  = booking.car and booking.car.owner_id == current_user.id

    if not (is_renter or is_owner or current_user.role == 'Admin'):
        flash('You are not authorised to cancel this booking.', 'danger')
        return redirect(url_for('main.my_bookings'))

    if booking.status in ('Cancelled', 'Completed'):
        flash('This booking cannot be cancelled.', 'warning')
        return redirect(url_for('main.my_bookings'))

    now = datetime.utcnow() + timedelta(hours=5, minutes=30)  # IST
    if booking.start_date and booking.start_date <= now:
        flash('You cannot cancel a booking that has already started.', 'warning')
        return redirect(url_for('main.my_bookings'))

    booking.status = 'Cancelled'
    db.session.commit()

    try:
        send_booking_cancellation_email(booking)
    except Exception as e:
        print(f"[cancel_booking email error] {e}")

    push_notification(
        booking.user_id,
        f'Your booking #{booking.id} for {booking.car.name} has been cancelled.',
        '/my-bookings',
    )

    log_action("Booking Cancelled", f"Booking #{booking.id} cancelled")

    if is_owner and not is_renter:
        flash(f'Booking #{booking.id} has been cancelled and the customer has been notified.', 'success')
        return redirect(url_for('client.client_dashboard'))

    flash(f'Booking #{booking.id} has been cancelled successfully.', 'success')
    return redirect(url_for('main.my_bookings'))
