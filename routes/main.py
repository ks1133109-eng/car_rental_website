import os
from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app
from flask_login import login_required, current_user
from extensions import db, limiter
from services.cloudinary_service import upload_kyc_image
from models.car import Car
from models.other_models import Offer, Notification
from models.booking import Booking
from models.other_models import Review

main_bp = Blueprint('main', __name__)


# ── Home ──────────────────────────────────────────────────────────────────────
# Exempt from rate limiting — this is the loader.io test target and public page.

@main_bp.route('/')
@limiter.exempt
def home():
    cars         = Car.query.filter_by(status='Available').limit(6).all()
    active_offer = Offer.query.filter_by(is_active=True).first()
    locations    = [r[0] for r in db.session.query(Car.location).distinct().all() if r[0]]
    return render_template('index.html', cars=cars, active_offer=active_offer, locations=locations)


# ── loader.io verification — must be exempt + no CSRF ────────────────────────

@main_bp.route('/loaderio-cd2a53049dfe08065f7538306f831b70.txt')
@limiter.exempt
def loaderio_verify():
    return "loaderio-cd2a53049dfe08065f7538306f831b70"


# ── Static pages — exempt from rate limiting ──────────────────────────────────

@main_bp.route('/about')
@limiter.exempt
def about():
    return render_template('about.html')


@main_bp.route('/contact', methods=['GET', 'POST'])
@limiter.limit("5 per minute; 20 per hour", methods=["POST"])
def contact():
    if request.method == 'POST':
        flash('Message sent! We will get back to you soon.', 'success')
    return render_template('contact.html')


@main_bp.route('/help')
@limiter.exempt
def help_support():
    return render_template('help.html')


# ── Fleet — exempt from rate limiting (public read page) ─────────────────────

@main_bp.route('/fleet')
@limiter.exempt
def fleet():
    from datetime import datetime
    location  = request.args.get('location')
    category  = request.args.get('category')
    seats     = request.args.get('seats')
    start_str = request.args.get('start_date')
    end_str   = request.args.get('end_date')

    query = Car.query.filter_by(status='Available')

    if location and location.strip() and location != 'All':
        query = query.filter(Car.location.ilike(f"%{location.strip()}%"))
    if category and category != 'All':
        query = query.filter_by(category=category)
    if seats and seats != 'All':
        query = query.filter(Car.seats >= int(seats))
    if start_str and end_str:
        try:
            req_start     = datetime.strptime(start_str, '%Y-%m-%dT%H:%M')
            req_end       = datetime.strptime(end_str,   '%Y-%m-%dT%H:%M')
            busy_subquery = db.session.query(Booking.car_id).filter(
                Booking.status    != 'Cancelled',
                Booking.start_date < req_end,
                Booking.end_date   > req_start,
            ).subquery()
            query = query.filter(Car.id.notin_(busy_subquery))
        except ValueError:
            pass

    cars       = query.all()
    categories = [c[0] for c in db.session.query(Car.category).distinct().all()]
    return render_template('fleet.html', cars=cars, categories=categories,
                           current_filters=request.args)


# ── PWA service worker — must be exempt ───────────────────────────────────────

@main_bp.route('/static/sw.js')
@limiter.exempt
def service_worker():
    from flask import make_response
    response = make_response(current_app.send_static_file('sw.js'))
    response.headers['Service-Worker-Allowed'] = '/'
    response.headers['Cache-Control']          = 'no-cache'
    return response


# ── Dashboard (role router) ───────────────────────────────────────────────────

@main_bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'Admin':
        return redirect(url_for('admin.admin_dashboard'))
    if current_user.role == 'Client':
        return redirect(url_for('client.client_dashboard'))

    from config import Config
    bookings    = Booking.query.filter_by(user_id=current_user.id)\
                               .order_by(Booking.date_booked.desc()).limit(5).all()
    total       = current_user.total_spent
    tier        = current_user.loyalty_tier
    tier_config = Config.LOYALTY_TIERS[tier]
    next_tier   = current_user.next_tier
    return render_template('dashboard.html',
        bookings       = bookings,
        total_trips    = Booking.query.filter_by(user_id=current_user.id).count(),
        total_spent    = int(total),
        loyalty        = tier,
        loyalty_config = tier_config,
        next_tier      = next_tier,
        loyalty_tiers  = Config.LOYALTY_TIERS,
    )


# ── Loyalty ───────────────────────────────────────────────────────────────────

@main_bp.route('/loyalty')
@login_required
def loyalty_page():
    from config import Config
    from models.user import User
    total           = current_user.total_spent
    tier            = current_user.loyalty_tier
    next_tier_data  = current_user.next_tier
    referral_link   = url_for('auth.register', ref=current_user.referral_code, _external=True)
    referred_users  = User.query.filter_by(referred_by=current_user.id).all()
    recent_bookings = Booking.query.filter_by(user_id=current_user.id)\
                                   .order_by(Booking.date_booked.desc()).limit(10).all()
    return render_template('loyalty.html',
        tier            = tier,
        tier_config     = Config.LOYALTY_TIERS[tier],
        next_tier       = next_tier_data,
        total_spent     = int(total),
        loyalty_tiers   = Config.LOYALTY_TIERS,
        referral_link   = referral_link,
        referred_users  = referred_users,
        recent_bookings = recent_bookings,
    )


# ── Profile ───────────────────────────────────────────────────────────────────

@main_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    from utils.helpers import log_action
    if request.method == 'POST':
        name    = (request.form.get('name', '') or '').strip()[:100]
        phone   = (request.form.get('phone', '') or '').strip()[:20]
        address = (request.form.get('address', '') or '').strip()[:200]
        gov_id  = (request.form.get('gov_id', '') or '').strip()[:50]

        if not name:
            flash('Name cannot be empty.', 'danger')
            return render_template('profile.html')

        # SECURITY: validate phone contains only digits, spaces, +, -
        import re as _re
        if phone and not _re.match(r'^[0-9 +()\-]{0,20}$', phone):
            flash('Invalid phone number format.', 'danger')
            return render_template('profile.html')

        current_user.name    = name
        current_user.phone   = phone
        current_user.address = address
        current_user.gov_id  = gov_id
        db.session.commit()
        log_action("Profile Update", "User updated profile details")
        flash('Profile updated successfully!', 'success')
    return render_template('profile.html')


# ── Security ──────────────────────────────────────────────────────────────────

@main_bp.route('/security', methods=['GET', 'POST'])
@login_required
def security():
    from werkzeug.security import generate_password_hash
    if request.method == 'POST':
        new_password = request.form.get('new_password', '')
        confirm      = request.form.get('confirm_password', '')
        if len(new_password) < 8:
            flash('Password must be at least 8 characters.', 'danger')
        elif not any(c.isdigit() for c in new_password) and not any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in new_password):
            flash('Password must contain at least one number or special character.', 'danger')
        elif new_password != confirm:
            flash('Passwords do not match.', 'danger')
        else:
            current_user.password = generate_password_hash(new_password, method='pbkdf2:sha256')
            db.session.commit()
            flash('Password changed successfully.', 'success')
    return render_template('security.html')


# ── KYC ───────────────────────────────────────────────────────────────────────

@main_bp.route('/kyc', methods=['GET', 'POST'])
@login_required
def kyc():
    from utils.helpers import log_action
    if current_user.kyc_status == 'Verified':
        flash('You are already verified!')
        return redirect(url_for('main.dashboard'))
    if request.method == 'POST':
        phone   = (request.form.get('phone',   '') or '').strip()[:20]
        address = (request.form.get('address', '') or '').strip()[:200]
        gov_id  = (request.form.get('gov_id',  '') or '').strip()[:50]

        gov_id_b64 = request.form.get('gov_id_image_data', '').strip()
        selfie_b64 = request.form.get('user_selfie_data',  '').strip()

        if not gov_id_b64 or not selfie_b64:
            flash('Please upload both your ID and take a selfie.')
            return redirect(url_for('main.kyc'))

        # SECURITY: Upload KYC images to Cloudinary (private/authenticated)
        # instead of storing raw base64 in the database.
        gov_id_url = upload_kyc_image(base64_data=gov_id_b64, doc_type='gov_id')
        selfie_url = upload_kyc_image(base64_data=selfie_b64, doc_type='selfie')

        if not gov_id_url or not selfie_url:
            flash('Image upload failed. Please try again.', 'danger')
            return redirect(url_for('main.kyc'))

        current_user.phone        = phone
        current_user.address      = address
        current_user.gov_id       = gov_id
        current_user.gov_id_image = gov_id_url   # Cloudinary URL, not raw base64
        current_user.user_selfie  = selfie_url   # Cloudinary URL, not raw base64
        current_user.kyc_status   = 'Pending'
        db.session.commit()
        log_action("KYC Submit", "User submitted KYC documents via Cloudinary")
        flash('KYC Submitted! Please wait for Admin approval.')
        return redirect(url_for('main.dashboard'))
    return render_template('kyc.html')


# ── My Bookings ───────────────────────────────────────────────────────────────

@main_bp.route('/my-bookings')
@login_required
def my_bookings():
    bookings = Booking.query.filter_by(user_id=current_user.id)\
                            .order_by(Booking.date_booked.desc()).all()
    return render_template('my_bookings.html', bookings=bookings)


# ── Review submit ─────────────────────────────────────────────────────────────

@main_bp.route('/review/submit', methods=['POST'])
@login_required
def submit_review():
    car_id = request.form.get('car_id')
    rating = request.form.get('rating', '5')

    # SECURITY FIX: only allow reviews from users who actually booked this car
    has_booking = Booking.query.filter(
        Booking.user_id == current_user.id,
        Booking.car_id  == car_id,
        Booking.status.in_(['Paid', 'Completed', 'Confirmed']),
    ).first()
    if not has_booking:
        flash('You can only review cars you have booked.', 'danger')
        return redirect(url_for('main.dashboard'))

    # Validate rating is 1-5
    try:
        rating_int = int(rating)
        if not 1 <= rating_int <= 5:
            raise ValueError
    except (ValueError, TypeError):
        flash('Invalid rating value.', 'danger')
        return redirect(url_for('main.dashboard'))

    # Prevent duplicate reviews on same booking
    existing = Review.query.filter_by(
        user_id=current_user.id, car_id=car_id
    ).first()
    if existing:
        flash('You have already reviewed this car.', 'info')
        return redirect(url_for('main.dashboard'))

    comment = (request.form.get('comment', '') or '').strip()[:500]

    db.session.add(Review(
        user_id = current_user.id,
        car_id  = car_id,
        rating  = rating_int,
        comment = comment,
    ))
    db.session.commit()
    flash('Review submitted! Thank you.', 'success')
    return redirect(url_for('main.dashboard'))


# ── Notifications API ─────────────────────────────────────────────────────────

@main_bp.route('/notifications')
@login_required
def get_notifications():
    from flask import jsonify
    notifications = Notification.query.filter_by(
        user_id=current_user.id, is_read=False
    ).order_by(Notification.created_at.desc()).limit(10).all()
    return jsonify({
        'count': len(notifications),
        'notifications': [{
            'id':      n.id,
            'message': n.message,
            'link':    n.link,
            'time':    n.created_at.strftime('%b %d, %I:%M %p'),
        } for n in notifications],
    })


@main_bp.route('/notifications/read/<int:notif_id>', methods=['POST'])
@login_required
def mark_notification_read(notif_id):
    from flask import jsonify
    n = Notification.query.filter_by(id=notif_id, user_id=current_user.id).first()
    if n:
        n.is_read = True
        db.session.commit()
    return jsonify({'ok': True})


@main_bp.route('/notifications/read-all', methods=['POST'])
@login_required
def mark_all_notifications_read():
    from flask import jsonify
    Notification.query.filter_by(user_id=current_user.id, is_read=False)\
                      .update({'is_read': True})
    db.session.commit()
    return jsonify({'ok': True})
