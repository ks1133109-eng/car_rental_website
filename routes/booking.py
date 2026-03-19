import math
import hmac
import hashlib
from datetime import datetime
from flask import (Blueprint, render_template, redirect, url_for,
                   request, flash, session, jsonify, current_app)
from flask_login import login_required, current_user
from extensions import db
from models.car import Car
from models.booking import Booking
from models.other_models import Offer, Coupon
from services.email_service import send_booking_confirmation_email
from services.loyalty_service import award_loyalty_points
from services.payment_service import create_razorpay_order, verify_razorpay_signature
from utils.helpers import log_action, push_notification

booking_bp = Blueprint('booking', __name__)


# ── Book — select dates ───────────────────────────────────────────

@booking_bp.route('/book/<int:car_id>', methods=['GET', 'POST'])
@login_required
def book_car_dates(car_id):
    if current_user.kyc_status != 'Verified':
        if current_user.kyc_status == 'Pending':
            flash('Your KYC is Pending Approval.')
            return redirect(url_for('main.dashboard'))
        flash('You must complete e-KYC Verification before booking.')
        return redirect(url_for('main.kyc'))

    car          = Car.query.get_or_404(car_id)
    active_offer = Offer.query.filter_by(is_active=True).first()

    if request.method == 'POST':
        start_str = request.form.get('start_date')
        end_str   = request.form.get('end_date')
        try:
            start_date = datetime.strptime(start_str, '%Y-%m-%dT%H:%M')
            end_date   = datetime.strptime(end_str,   '%Y-%m-%dT%H:%M')
        except ValueError:
            flash("Invalid date format.")
            return redirect(url_for('booking.book_car_dates', car_id=car.id))

        now = datetime.utcnow()
        if start_date < now:
            flash("Start date cannot be in the past.", "danger")
            return redirect(url_for('booking.book_car_dates', car_id=car.id))

        if start_date >= end_date:
            flash("End date must be after start date.")
            return redirect(url_for('booking.book_car_dates', car_id=car.id))

        duration_days = max(1, math.ceil((end_date - start_date).total_seconds() / 86400))
        if duration_days > 60:
            flash("Maximum booking duration is 60 Days.")
            return redirect(url_for('booking.book_car_dates', car_id=car.id))

        collision = Booking.query.filter(
            Booking.car_id     == car.id,
            Booking.status     != 'Cancelled',
            Booking.start_date  < end_date,
            Booking.end_date    > start_date,
        ).first()
        if collision:
            flash('Unavailable! This car is already booked.')
            return redirect(url_for('booking.book_car_dates', car_id=car.id))

        base_cost             = int(duration_days * car.price_per_day)
        offer_discount_amount = (
            int(base_cost * (active_offer.discount_percentage / 100.0))
            if active_offer else 0
        )
        with_driver      = 'with_driver'   in request.form
        with_delivery    = 'with_delivery' in request.form
        driver_fee       = (500 * duration_days) if with_driver else 0
        delivery_fee     = 500 if with_delivery and not with_driver else 0
        delivery_address = request.form.get('delivery_address') if with_delivery else "Self Pickup"
        delivery_type    = "Delivery" if with_delivery else "Pickup"
        subtotal         = base_cost + driver_fee + delivery_fee
        tax              = int(subtotal * 0.18) if subtotal > 0 else 0
        total            = (subtotal + tax) - offer_discount_amount

        points_discount = 0
        use_points      = 'use_points' in request.form
        if use_points and current_user.loyalty_points >= 100:
            max_points_usable = min(
                current_user.loyalty_points,
                int(total / 50) * 100,
            )
            points_discount = int(max_points_usable / 100) * 50
            total           = max(0, total - points_discount)

        return render_template('booking_payment.html',
            car              = car,
            start_date       = start_str,
            end_date         = end_str,
            base_cost        = base_cost,
            driver_fee       = driver_fee,
            delivery_fee     = delivery_fee,
            delivery_type    = delivery_type,
            delivery_address = delivery_address,
            tax              = tax,
            discount         = offer_discount_amount,
            points_discount  = points_discount,
            total            = max(0, total),
            with_driver      = with_driver,
            active_offer     = active_offer,
            use_points       = use_points,
            razorpay_key_id  = current_app.config.get('RAZORPAY_KEY_ID', ''),
        )

    return render_template('booking_dates.html', car=car, active_offer=active_offer)


# ── Apply coupon ──────────────────────────────────────────────────

@booking_bp.route('/book/apply-coupon', methods=['POST'])
@login_required
def apply_coupon():
    car_id           = request.form.get('car_id')
    start_str        = request.form.get('start_date')
    end_str          = request.form.get('end_date')
    with_driver      = request.form.get('with_driver') == 'True'
    delivery_fee     = float(request.form.get('delivery_fee', 0))
    delivery_type    = request.form.get('delivery_type')
    delivery_address = request.form.get('delivery_address')
    coupon_code      = request.form.get('coupon_code', '').strip().upper()

    car           = Car.query.get_or_404(car_id)
    start_date    = datetime.strptime(start_str, '%Y-%m-%dT%H:%M')
    end_date      = datetime.strptime(end_str,   '%Y-%m-%dT%H:%M')
    duration_days = max(1, math.ceil((end_date - start_date).total_seconds() / 3600 / 24))
    base_cost     = int(duration_days * car.price_per_day)
    driver_fee    = (500 * duration_days) if with_driver else 0
    tax           = 648
    discount      = 0

    coupon = Coupon.query.filter_by(code=coupon_code, is_active=True).first()
    if coupon:
        discount = coupon.discount_amount
        flash(f'Coupon Applied! You saved ₹{discount}')
    else:
        flash('Invalid or Expired Coupon Code')

    total_cost = max(0, (base_cost + driver_fee + delivery_fee + tax) - discount)
    return render_template('booking_payment.html',
        car              = car,
        start_date       = start_str,
        end_date         = end_str,
        base_cost        = base_cost,
        driver_fee       = driver_fee,
        delivery_fee     = delivery_fee,
        delivery_type    = delivery_type,
        delivery_address = delivery_address,
        tax              = tax,
        discount         = discount,
        points_discount  = 0,
        total            = total_cost,
        with_driver      = with_driver,
        applied_coupon   = coupon_code if discount > 0 else "",
        razorpay_key_id  = current_app.config.get('RAZORPAY_KEY_ID', ''),
    )


# ── Razorpay: create order ────────────────────────────────────────

@booking_bp.route('/payment/create-razorpay-order', methods=['POST'])
@login_required
def create_razorpay_order_route():
    """
    Called by the booking_payment.html JS before launching the Razorpay popup.
    SECURITY: All monetary values are recalculated server-side from trusted DB records.
    Client-supplied prices are IGNORED — only dates, booleans, and delivery address are read.
    Returns JSON: { order_id, amount, currency, key_id }
    """
    if not current_app.config.get('RAZORPAY_KEY_ID'):
        return jsonify({'error': 'Razorpay is not configured on this server.'}), 500

    try:
        data = request.get_json()

        # Parse and validate dates
        start_date = datetime.strptime(data['start_date'], '%Y-%m-%dT%H:%M')
        end_date   = datetime.strptime(data['end_date'],   '%Y-%m-%dT%H:%M')
        if start_date >= end_date:
            return jsonify({'error': 'End date must be after start date.'}), 400

        duration_days = max(1, math.ceil((end_date - start_date).total_seconds() / 86400))
        if duration_days > 60:
            return jsonify({'error': 'Maximum booking duration is 60 days.'}), 400

        # Load car from DB — never trust client-supplied price
        car = Car.query.get(int(data['car_id']))
        if not car or car.status != 'Available':
            return jsonify({'error': 'Car not available.'}), 400

        # Collision check
        collision = Booking.query.filter(
            Booking.car_id     == car.id,
            Booking.status     != 'Cancelled',
            Booking.start_date  < end_date,
            Booking.end_date    > start_date,
        ).first()
        if collision:
            return jsonify({'error': 'This car is already booked for those dates.'}), 409

        # Recalculate ALL costs server-side from DB values
        with_driver      = bool(data.get('with_driver', False))
        with_delivery    = data.get('delivery_type') == 'Delivery'
        delivery_address = str(data.get('delivery_address', 'Self Pickup'))[:500]
        delivery_type    = 'Delivery' if with_delivery else 'Pickup'

        base_cost    = int(duration_days * car.price_per_day)
        driver_fee   = (500 * duration_days) if with_driver else 0
        delivery_fee = 500 if with_delivery and not with_driver else 0
        subtotal     = base_cost + driver_fee + delivery_fee
        tax          = int(subtotal * 0.18) if subtotal > 0 else 0

        active_offer          = Offer.query.filter_by(is_active=True).first()
        offer_discount_amount = (
            int(base_cost * (active_offer.discount_percentage / 100.0))
            if active_offer else 0
        )

        total = (subtotal + tax) - offer_discount_amount

        # Loyalty points — validate against live DB balance
        use_points      = bool(data.get('use_points', False))
        points_discount = 0
        if use_points and current_user.loyalty_points >= 100:
            max_points_usable = min(
                current_user.loyalty_points,
                int(total / 50) * 100,
            )
            points_discount = int(max_points_usable / 100) * 50
            total = max(0, total - points_discount)

        verified_total = max(0, total)

        # Persist server-calculated booking in session
        session['pending_booking'] = {
            'car_id':           car.id,
            'start_date':       data['start_date'],
            'end_date':         data['end_date'],
            'base_cost':        base_cost,
            'driver_fee':       driver_fee,
            'delivery_fee':     delivery_fee,
            'delivery_type':    delivery_type,
            'delivery_address': delivery_address,
            'discount':         offer_discount_amount,
            'points_discount':  points_discount,
            'use_points':       use_points,
            'with_driver':      with_driver,
            'total_cost':       verified_total,
        }

        order = create_razorpay_order(verified_total)
        return jsonify({
            'order_id': order['id'],
            'amount':   order['amount'],
            'currency': order['currency'],
            'key_id':   current_app.config.get('RAZORPAY_KEY_ID', ''),
        })

    except Exception as e:
        print(f"[create_razorpay_order error] {e}")
        return jsonify({'error': 'Could not create payment order. Please try again.'}), 500


# ── Razorpay: verify payment & confirm booking ────────────────────

@booking_bp.route('/payment/razorpay-success', methods=['POST'])
@login_required
def razorpay_payment_success():
    """
    Called after the Razorpay popup closes successfully.
    Verifies the HMAC signature, then creates the booking record.
    """
    razorpay_order_id   = request.form.get('razorpay_order_id', '')
    razorpay_payment_id = request.form.get('razorpay_payment_id', '')
    razorpay_signature  = request.form.get('razorpay_signature', '')
    pending             = session.get('pending_booking')

    if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature, pending]):
        flash('Payment verification failed. Please contact support.', 'danger')
        return redirect(url_for('main.my_bookings'))

    # Verify HMAC signature
    if not verify_razorpay_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature):
        flash('Payment signature mismatch. Please contact support.', 'danger')
        return redirect(url_for('main.my_bookings'))

    # Prevent duplicate booking on double-submit
    existing = Booking.query.filter_by(razorpay_payment_id=razorpay_payment_id).first()
    if existing:
        return redirect(url_for('booking.booking_success', booking_id=existing.id))

    try:
        start_date  = datetime.strptime(pending['start_date'], '%Y-%m-%dT%H:%M')
        end_date    = datetime.strptime(pending['end_date'],   '%Y-%m-%dT%H:%M')
        new_booking = Booking(
            user_id             = current_user.id,
            car_id              = pending['car_id'],
            base_cost           = pending['base_cost'],
            driver_cost         = pending['driver_fee'],
            delivery_fee        = pending['delivery_fee'],
            delivery_type       = pending['delivery_type'],
            delivery_address    = pending['delivery_address'],
            discount            = pending['discount'] + pending['points_discount'],
            total_cost          = pending['total_cost'],
            with_driver         = pending['with_driver'],
            payment_method      = 'razorpay',
            razorpay_order_id   = razorpay_order_id,
            razorpay_payment_id = razorpay_payment_id,
            status              = 'Paid',
            start_date          = start_date,
            end_date            = end_date,
        )
        db.session.add(new_booking)

        if pending.get('use_points') and pending['points_discount'] > 0:
            current_user.loyalty_points = max(
                0,
                current_user.loyalty_points - int(pending['points_discount'] / 50) * 100,
            )

        db.session.commit()
        earned = award_loyalty_points(current_user, new_booking)
        log_action("Booking Created", f"Booking ID {new_booking.id} (Razorpay)")
        send_booking_confirmation_email(new_booking)
        push_notification(
            current_user.id,
            f"Booking #{new_booking.id} confirmed for {new_booking.car.name}! "
            f"You earned {earned} loyalty points.",
            f"/booking/success/{new_booking.id}",
        )
        session.pop('pending_booking', None)
        return redirect(url_for('booking.booking_success', booking_id=new_booking.id))

    except Exception as e:
        db.session.rollback()
        print(f"[razorpay_payment_success error] {e}")
        flash(
            f'Booking creation failed. Your payment was received — '
            f'contact support with payment ID: {razorpay_payment_id}',
            'danger',
        )
        return redirect(url_for('main.my_bookings'))


# ── COD: confirm booking (Pay Later / Cash) ───────────────────────

@booking_bp.route('/book/confirm-cod/<int:car_id>', methods=['POST'])
@login_required
def confirm_booking_cod(car_id):
    car = Car.query.get_or_404(car_id)

    def safe_int(v, d=0):
        try:
            return int(v)
        except Exception:
            return d

    try:
        start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%dT%H:%M')
        end_date   = datetime.strptime(request.form.get('end_date'),   '%Y-%m-%dT%H:%M')
    except (ValueError, TypeError):
        flash('Invalid dates provided.', 'danger')
        return redirect(url_for('booking.book_car_dates', car_id=car_id))

    # SECURITY FIX: COD must also check for booking collisions
    if start_date >= end_date:
        flash('End date must be after start date.', 'danger')
        return redirect(url_for('booking.book_car_dates', car_id=car_id))

    collision = Booking.query.filter(
        Booking.car_id     == car.id,
        Booking.status     != 'Cancelled',
        Booking.start_date  < end_date,
        Booking.end_date    > start_date,
    ).first()
    if collision:
        flash('Sorry! This car was just booked for those dates. Please choose different dates.', 'danger')
        return redirect(url_for('booking.book_car_dates', car_id=car_id))

    # SECURITY FIX: recalculate all costs server-side for COD
    # Never trust form-submitted prices — a user could forge total_cost=1
    import math as _math
    duration_days    = max(1, _math.ceil((end_date - start_date).total_seconds() / 86400))
    with_driver      = request.form.get('with_driver') == 'True'
    with_delivery    = request.form.get('delivery_type') == 'Delivery'
    base_cost        = int(duration_days * car.price_per_day)
    driver_cost      = (500 * duration_days) if with_driver else 0
    delivery_fee     = 500 if with_delivery and not with_driver else 0
    delivery_address = request.form.get('delivery_address', 'Self Pickup') if with_delivery else 'Self Pickup'
    delivery_type    = 'Delivery' if with_delivery else 'Pickup'
    subtotal         = base_cost + driver_cost + delivery_fee
    tax              = int(subtotal * 0.18) if subtotal > 0 else 0
    active_offer     = Offer.query.filter_by(is_active=True).first()
    offer_discount   = int(base_cost * (active_offer.discount_percentage / 100.0)) if active_offer else 0

    use_points       = request.form.get('use_points') == 'True'
    # Cap loyalty points discount to what user actually has
    max_points_disc  = min(current_user.loyalty_points // 100 * 50, subtotal // 2)
    points_discount  = min(safe_int(request.form.get('points_discount', 0)), max_points_disc) if use_points else 0

    total_cost       = max(0, (subtotal + tax) - offer_discount - points_discount)

    new_booking = Booking(
        user_id          = current_user.id,
        car_id           = car.id,
        base_cost        = base_cost,
        driver_cost      = driver_cost,
        delivery_fee     = delivery_fee,
        delivery_type    = delivery_type,
        delivery_address = delivery_address,
        discount         = offer_discount + points_discount,
        total_cost       = total_cost,
        with_driver      = with_driver,
        payment_method   = 'cod',
        status           = 'Confirmed',
        start_date       = start_date,
        end_date         = end_date,
    )
    db.session.add(new_booking)

    if use_points and points_discount > 0:
        current_user.loyalty_points = max(
            0,
            current_user.loyalty_points - int(points_discount / 50) * 100,
        )

    db.session.commit()
    earned = award_loyalty_points(current_user, new_booking)
    log_action("Booking Created", f"Booking ID {new_booking.id} (COD)")
    send_booking_confirmation_email(new_booking)
    push_notification(
        current_user.id,
        f"Booking #{new_booking.id} confirmed for {car.name}! You earned {earned} loyalty points.",
        f"/booking/success/{new_booking.id}",
    )
    return redirect(url_for('booking.booking_success', booking_id=new_booking.id))


# ── Booking success & invoice ─────────────────────────────────────

@booking_bp.route('/booking/success/<int:booking_id>')
@login_required
def booking_success(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    if booking.user_id != current_user.id:
        return redirect(url_for('main.dashboard'))
    return render_template('booking_success.html', booking=booking)


@booking_bp.route('/booking/invoice/<int:booking_id>')
@login_required
def invoice(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    if booking.user_id != current_user.id and current_user.role != 'Admin':
        return redirect(url_for('main.dashboard'))
    return render_template('invoice.html', booking=booking)
