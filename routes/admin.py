import json
from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from extensions import db, limiter
from models.user import User
from models.car import Car
from models.booking import Booking
from models.other_models import Review, Coupon, Offer, AuditLog, Notification, LoginAttempt
from services.email_service import send_kyc_status_email, send_booking_cancellation_email
from services.cloudinary_service import get_signed_kyc_url
from models.user import decrypt_field
from utils.helpers import log_action, push_notification

admin_bp = Blueprint('admin', __name__)


def _admin_required():
    return current_user.role != 'Admin'


# ── Dashboard / Analytics ─────────────────────────────────────────

@admin_bp.route('/admin')
@login_required
def admin_dashboard():
    if _admin_required():
        return redirect(url_for('main.home'))

    total_cars       = Car.query.count()
    total_users      = User.query.filter(User.role != 'Admin').count()
    active_bookings  = Booking.query.filter(Booking.status.in_(['Confirmed', 'Paid'])).count()
    maintenance_cars = Car.query.filter_by(status='Maintenance').count()
    available_cars   = Car.query.filter_by(status='Available').count()
    total_revenue    = (
        db.session.query(db.func.sum(Booking.total_cost))
        .filter(Booking.status != 'Cancelled').scalar() or 0
    )
    cancelled_count = Booking.query.filter_by(status='Cancelled').count()
    total_bookings  = Booking.query.count()
    cancel_rate     = round((cancelled_count / total_bookings * 100), 1) if total_bookings else 0

    current_year   = datetime.now().year
    monthly_rev    = {m: 0 for m in range(1, 13)}
    monthly_counts = {m: 0 for m in range(1, 13)}
    for b in Booking.query.filter(
        Booking.status != 'Cancelled',
        db.func.extract('year', Booking.date_booked) == current_year,
    ).all():
        if b.date_booked:
            monthly_rev[b.date_booked.month]    += b.total_cost or 0
            monthly_counts[b.date_booked.month] += 1

    categories = db.session.query(Car.category, db.func.count(Car.id)).group_by(Car.category).all()

    top_cars_raw = (
        db.session.query(
            Car.name, Car.category,
            db.func.count(Booking.id).label('bookings'),
            db.func.sum(Booking.total_cost).label('revenue'),
        )
        .join(Booking, Booking.car_id == Car.id)
        .filter(Booking.status != 'Cancelled')
        .group_by(Car.id, Car.name, Car.category)
        .order_by(db.func.count(Booking.id).desc())
        .limit(5).all()
    )
    top_cars = [
        {'name': r[0], 'category': r[1], 'bookings': r[2], 'revenue': r[3] or 0}
        for r in top_cars_raw
    ]

    user_growth        = []
    user_growth_labels = []
    now_dt = datetime.now()
    from datetime import date as _date
    for i in range(5, -1, -1):
        month_offset = (now_dt.month - 1 - i) % 12 + 1
        year_offset  = now_dt.year + ((now_dt.month - 1 - i) // 12)
        count = (
            db.session.query(db.func.count(db.func.distinct(Booking.user_id)))
            .filter(
                db.func.extract('year',  Booking.date_booked) == year_offset,
                db.func.extract('month', Booking.date_booked) == month_offset,
            ).scalar() or 0
        )
        user_growth.append(count)
        user_growth_labels.append(_date(year_offset, month_offset, 1).strftime('%b'))

    payment_split = (
        db.session.query(Booking.payment_method, db.func.count(Booking.id))
        .filter(Booking.payment_method != None)
        .group_by(Booking.payment_method).all()
    )
    status_split = (
        db.session.query(Booking.status, db.func.count(Booking.id))
        .group_by(Booking.status).all()
    )
    recent_bookings = Booking.query.order_by(Booking.date_booked.desc()).limit(5).all()

    now = datetime.now()
    rev_this_month = (
        db.session.query(db.func.sum(Booking.total_cost)).filter(
            Booking.status != 'Cancelled',
            db.func.extract('year',  Booking.date_booked) == now.year,
            db.func.extract('month', Booking.date_booked) == now.month,
        ).scalar() or 0
    )
    last_month = (now.replace(day=1) - timedelta(days=1))
    rev_last_month = (
        db.session.query(db.func.sum(Booking.total_cost)).filter(
            Booking.status != 'Cancelled',
            db.func.extract('year',  Booking.date_booked) == last_month.year,
            db.func.extract('month', Booking.date_booked) == last_month.month,
        ).scalar() or 0
    )
    rev_change = (
        round(((rev_this_month - rev_last_month) / rev_last_month * 100), 1)
        if rev_last_month else 0
    )

    pending_users = User.query.filter_by(kyc_status='Pending').all()
    pending_cars  = Car.query.filter_by(status='Pending').all()

    stats = {
        'total_cars':      total_cars,
        'total_users':     total_users,
        'active_bookings': active_bookings,
        'maintenance_cars':maintenance_cars,
        'available_cars':  available_cars,
        'total_revenue':   int(total_revenue),
        'cancel_rate':     cancel_rate,
        'total_bookings':  total_bookings,
        'rev_this_month':  int(rev_this_month),
        'rev_change':      rev_change,
    }
    charts = {
        'rev_data':           json.dumps(list(monthly_rev.values())),
        'book_data':          json.dumps(list(monthly_counts.values())),
        'cat_labels':         json.dumps([c[0] or 'Uncategorized' for c in categories]),
        'cat_data':           json.dumps([c[1] for c in categories]),
        'user_growth':        json.dumps(user_growth),
        'user_growth_labels': json.dumps(user_growth_labels),
        'payment_labels':     json.dumps([p[0] or 'Unknown' for p in payment_split]),
        'payment_data':       json.dumps([p[1] for p in payment_split]),
        'status_labels':      json.dumps([s[0] for s in status_split]),
        'status_data':        json.dumps([s[1] for s in status_split]),
    }
    return render_template('admin.html',
        stats           = stats,
        charts          = charts,
        pending_users   = pending_users,
        pending_cars    = pending_cars,
        top_cars        = top_cars,
        recent_bookings = recent_bookings,
    )


# ── KYC signed URL (admin only) ──────────────────────────────────

@admin_bp.route('/admin/kyc-view/<int:user_id>/<doc_type>')
@login_required
def kyc_view_url(user_id, doc_type):
    """Return a short-lived signed URL for viewing a private KYC document."""
    from flask import jsonify
    if _admin_required():
        return jsonify({'error': 'Unauthorized'}), 403
    if doc_type not in ('gov_id', 'selfie'):
        return jsonify({'error': 'Invalid doc type'}), 400

    user = User.query.get_or_404(user_id)
    raw  = user.gov_id_image if doc_type == 'gov_id' else user.user_selfie
    if not raw:
        return jsonify({'error': 'No document found'}), 404

    signed = get_signed_kyc_url(raw, expires_in_seconds=300)
    log_action("Admin KYC View", f"Admin viewed {doc_type} for user {user.email}")
    return jsonify({'url': signed})


# ── KYC ───────────────────────────────────────────────────────────

@admin_bp.route('/admin/approve-kyc/<int:user_id>')
@login_required
@limiter.limit("30 per minute")
def approve_kyc(user_id):
    if _admin_required(): return redirect(url_for('main.home'))
    user = User.query.get(user_id)
    if user:
        user.kyc_status = 'Verified'
        db.session.commit()
        send_kyc_status_email(user, 'Verified')
        push_notification(user.id, 'Your KYC has been verified! You can now book cars.', '/fleet')
        log_action("Admin KYC Approve", f"Approved user {user.email}")
    return redirect(url_for('admin.admin_dashboard'))


@admin_bp.route('/admin/reject-kyc/<int:user_id>')
@login_required
def reject_kyc(user_id):
    if _admin_required(): return redirect(url_for('main.home'))
    user = User.query.get(user_id)
    if user:
        user.kyc_status = 'Rejected'
        db.session.commit()
        send_kyc_status_email(user, 'Rejected')
        push_notification(user.id, 'Your KYC was not verified. Please re-submit your documents.', '/kyc')
        log_action("Admin KYC Reject", f"Rejected user {user.email}")
    return redirect(url_for('admin.admin_dashboard'))


# ── Car management ────────────────────────────────────────────────

@admin_bp.route('/admin/cars', methods=['GET', 'POST'])
@login_required
def manage_cars():
    if _admin_required(): return redirect(url_for('main.home'))
    if request.method == 'POST':
        try:
            name     = request.form.get('name', '').strip()
            price    = request.form.get('price', '').strip()
            location = request.form.get('location', '').strip()
            if not name:
                flash('Car name is required.', 'danger')
                return redirect(url_for('admin.manage_cars'))
            if not price or not price.isdigit() or int(price) <= 0:
                flash('A valid price per day is required.', 'danger')
                return redirect(url_for('admin.manage_cars'))
            img_url    = request.form.get('image_url', '').strip()
            img_upload = request.form.get('image_base64', '').strip()
            final_image = img_url or img_upload or '/static/images/car_placeholder.jpg'
            seats = request.form.get('seats', '5').strip()
            seats = int(seats) if seats.isdigit() else 5
            db.session.add(Car(
                name          = name,
                price_per_day = int(price),
                image_url     = final_image,
                category      = request.form.get('category', 'Sedan'),
                location      = location,
                transmission  = request.form.get('transmission', 'Auto'),
                fuel_type     = request.form.get('fuel_type', 'Petrol'),
                seats         = seats,
                status        = request.form.get('status', 'Available'),
            ))
            db.session.commit()
            log_action("Admin Car Add", f"Added {name}")
            flash('New car added to the fleet.', 'success')
        except ValueError as e:
            db.session.rollback()
            flash(f'Invalid value: {e}', 'danger')
        except Exception as e:
            db.session.rollback()
            print(f"[manage_cars POST error] {e}")
            flash('Failed to add car. Please check your inputs.', 'danger')
        return redirect(url_for('admin.manage_cars'))
    return render_template('manage_cars.html', cars=Car.query.all())


@admin_bp.route('/admin/cars/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_car(id):
    if _admin_required(): return redirect(url_for('main.home'))
    car = Car.query.get_or_404(id)
    if request.method == 'POST':
        car.name          = request.form.get('name')
        car.price_per_day = int(request.form.get('price'))
        car.category      = request.form.get('category')
        car.location      = request.form.get('location')
        car.transmission  = request.form.get('transmission')
        car.fuel_type     = request.form.get('fuel_type')
        car.seats         = int(request.form.get('seats'))
        car.status        = request.form.get('status')
        img_url    = request.form.get('image_url', '').strip()
        img_upload = request.form.get('image_base64', '').strip()
        if img_url:
            car.image_url = img_url
        elif img_upload:
            car.image_url = img_upload
        db.session.commit()
        log_action("Admin Car Edit", f"Edited Car ID {id} ({car.name})")
        flash('Car updated successfully!', 'success')
        return redirect(url_for('admin.manage_cars'))
    return render_template('edit_car.html', car=car)


@admin_bp.route('/admin/cars/delete/<int:id>')
@login_required
def delete_car(id):
    if _admin_required(): return redirect(url_for('main.home'))
    car = Car.query.get_or_404(id)
    try:
        Review.query.filter_by(car_id=id).delete()
        Booking.query.filter_by(car_id=id).delete()
        db.session.delete(car)
        db.session.commit()
        log_action("Admin Car Delete", f"Deleted Car ID {id}")
    except Exception:
        db.session.rollback()
    return redirect(url_for('admin.manage_cars'))


@admin_bp.route('/admin/cars/approve/<int:id>')
@login_required
def approve_car(id):
    if _admin_required(): return redirect(url_for('main.home'))
    car = Car.query.get_or_404(id)
    car.status = 'Available'
    db.session.commit()
    if car.owner_id:
        push_notification(
            car.owner_id,
            f'Your car "{car.name}" has been approved and is now live!',
            '/client-dashboard',
        )
    flash(f'Car {car.name} is now LIVE.', 'success')
    return redirect(url_for('admin.admin_dashboard'))


@admin_bp.route('/admin/cars/reject/<int:id>')
@login_required
def reject_car(id):
    if _admin_required(): return redirect(url_for('main.home'))
    car      = Car.query.get_or_404(id)
    car_name = car.name
    if car.owner_id:
        push_notification(
            car.owner_id,
            f'Your car "{car_name}" was not approved. Please review and resubmit.',
            '/client-dashboard',
        )
    db.session.delete(car)
    db.session.commit()
    flash(f'Car "{car_name}" has been rejected and removed.', 'warning')
    return redirect(url_for('admin.admin_dashboard'))


# ── Coupon management ─────────────────────────────────────────────

@admin_bp.route('/admin/coupons', methods=['GET', 'POST'])
@login_required
def manage_coupons():
    if _admin_required(): return redirect(url_for('main.home'))
    if request.method == 'POST':
        db.session.add(Coupon(
            code            = request.form.get('code').upper(),
            discount_amount = int(request.form.get('discount')),
        ))
        db.session.commit()
    return render_template('manage_coupons.html', coupons=Coupon.query.all())


@admin_bp.route('/admin/coupons/delete/<int:id>')
@login_required
def delete_coupon(id):
    if _admin_required(): return redirect(url_for('main.home'))
    db.session.delete(Coupon.query.get(id))
    db.session.commit()
    return redirect(url_for('admin.manage_coupons'))


# ── Booking management ────────────────────────────────────────────

@admin_bp.route('/admin/bookings')
@login_required
def manage_bookings():
    if _admin_required(): return redirect(url_for('main.home'))
    return render_template('manage_bookings.html',
        bookings=Booking.query.order_by(Booking.date_booked.desc()).all())


ALLOWED_BOOKING_STATUSES = {'Upcoming', 'Confirmed', 'Paid', 'Completed', 'Cancelled'}

@admin_bp.route('/admin/booking/update/<int:id>/<status>')
@login_required
def update_booking(id, status):
    if _admin_required(): return redirect(url_for('main.home'))
    # SECURITY: whitelist valid status values — prevents status injection
    if status not in ALLOWED_BOOKING_STATUSES:
        flash(f'Invalid booking status: {status}', 'danger')
        return redirect(url_for('admin.manage_bookings'))
    booking = Booking.query.get(id)
    if booking:
        booking.status = status
        db.session.commit()
        if status == 'Cancelled':
            send_booking_cancellation_email(booking)
            push_notification(
                booking.user_id,
                f'Your booking #{booking.id} for {booking.car.name} has been cancelled.',
                '/my-bookings',
            )
    return redirect(url_for('admin.manage_bookings'))


# ── User management ───────────────────────────────────────────────

@admin_bp.route('/admin/users')
@login_required
def manage_users():
    if _admin_required(): return redirect(url_for('main.home'))
    return render_template('manage_users.html', users=User.query.all())


@admin_bp.route('/admin/users/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_user(id):
    if _admin_required(): return redirect(url_for('main.home'))
    user = User.query.get_or_404(id)
    if request.method == 'POST':
        user.status = request.form.get('status')
        user.role   = request.form.get('role')
        db.session.commit()
        flash('User updated successfully.', 'success')
        return redirect(url_for('admin.manage_users'))
    return render_template('edit_user.html', user=user)


@admin_bp.route('/admin/users/history/<int:id>')
@login_required
def user_booking_history(id):
    if _admin_required(): return redirect(url_for('main.home'))
    user     = User.query.get_or_404(id)
    bookings = Booking.query.filter_by(user_id=id).order_by(Booking.date_booked.desc()).all()
    return render_template('manage_bookings.html', bookings=bookings,
                           title=f"Booking History for {user.name}")


@admin_bp.route('/admin/users/delete/<int:id>')
@login_required
@limiter.limit("20 per minute")
def delete_user(id):
    if _admin_required(): return redirect(url_for('main.home'))
    u = User.query.get(id)
    if u and u.role != 'Admin':
        try:
            Booking.query.filter_by(user_id=id).delete()
            Review.query.filter_by(user_id=id).delete()
            AuditLog.query.filter_by(user_id=id).delete()
            Notification.query.filter_by(user_id=id).delete()
            for car in Car.query.filter_by(owner_id=id).all():
                Booking.query.filter_by(car_id=car.id).delete()
                Review.query.filter_by(car_id=car.id).delete()
                db.session.delete(car)
            db.session.delete(u)
            db.session.commit()
            flash(f"User {u.name} removed.", "success")
        except Exception:
            db.session.rollback()
    return redirect(url_for('admin.manage_users'))


# ── Clients ───────────────────────────────────────────────────────

@admin_bp.route('/admin/clients')
@login_required
def manage_clients():
    if _admin_required(): return redirect(url_for('main.home'))
    return render_template('manage_users.html', users=User.query.filter_by(role='Client').all())


# ── Offers ────────────────────────────────────────────────────────

@admin_bp.route('/admin/offers', methods=['GET', 'POST'])
@login_required
def manage_offers():
    if _admin_required(): return redirect(url_for('main.home'))
    if request.method == 'POST':
        is_active = 'is_active' in request.form
        if is_active:
            Offer.query.update({Offer.is_active: False})
        db.session.add(Offer(
            title               = request.form.get('title'),
            description         = request.form.get('description'),
            discount_percentage = int(request.form.get('discount')),
            is_active           = is_active,
        ))
        db.session.commit()
        return redirect(url_for('admin.manage_offers'))
    return render_template('manage_offers.html', offers=Offer.query.all())


@admin_bp.route('/admin/offers/toggle/<int:id>')
@login_required
def toggle_offer(id):
    if _admin_required(): return redirect(url_for('main.home'))
    o = Offer.query.get_or_404(id)
    if not o.is_active:
        Offer.query.update({Offer.is_active: False})
    o.is_active = not o.is_active
    db.session.commit()
    return redirect(url_for('admin.manage_offers'))


@admin_bp.route('/admin/offers/delete/<int:id>')
@login_required
def delete_offer(id):
    if _admin_required(): return redirect(url_for('main.home'))
    db.session.delete(Offer.query.get_or_404(id))
    db.session.commit()
    return redirect(url_for('admin.manage_offers'))


# ── Audit logs ────────────────────────────────────────────────────

@admin_bp.route('/admin/logs')
@login_required
def admin_logs():
    if _admin_required(): return redirect(url_for('main.home'))
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(50).all()
    return render_template('admin_logs.html', logs=logs, tz_label='IST')


# ── DB reset (protected by token) ────────────────────────────────
# SECURITY: Protected by RESET_DB_TOKEN env var (works on Render too).
#
# SETUP STEPS on Render:
#   1. Go to Render Dashboard → Your Service → Environment
#   2. Add:  RESET_DB_TOKEN = drivex_super_secure_987654  (or any secret)
#   3. Add:  ADMIN_PASSWORD = YourStrongPassword123
#   4. Visit: https://yourdomain.com/reset-db?token=drivex_super_secure_987654
#
# After first run, DELETE or CHANGE the token to prevent re-use.

@admin_bp.route('/reset-db')
@limiter.limit("3 per hour")
def reset_db():
    import os
    from flask import current_app

    # Require a secret token — works in both dev and production
    expected_token = os.environ.get('RESET_DB_TOKEN', '')
    provided_token = request.args.get('token', '')

    if not expected_token:
        return (
            "<h2>RESET_DB_TOKEN not set</h2>"
            "<p>Add <b>RESET_DB_TOKEN</b> as an environment variable on Render "
            "(Dashboard → Your Service → Environment), then revisit this URL "
            "with <code>?token=YOUR_TOKEN</code>.</p>"
        ), 403

    import hmac as _hmac
    if not _hmac.compare_digest(expected_token, provided_token):
        return (
            "<h2>403 — Invalid Token</h2>"
            "<p>The token in the URL does not match <b>RESET_DB_TOKEN</b>. "
            "Check your Render environment variables.</p>"
        ), 403

    from werkzeug.security import generate_password_hash as _hash
    with current_app.app_context():
        db.drop_all()
        db.create_all()
        cars_data = [
            ("Hyundai i20 Sportz","Hatchback",2200,"Manual","Petrol",5,"Mumbai","/static/images/hyundai_i20.jpg"),
            ("Tata Nexon XZA+","SUV",3000,"Auto","Petrol",5,"Pune","/static/images/tata_nexon.jpg"),
            ("Honda City 5th Gen","Sedan",3500,"Auto","Petrol",5,"Delhi","/static/images/honda_city.jpg"),
            ("Mahindra Thar 4x4","SUV",5500,"Manual","Diesel",4,"Goa","/static/images/mahindra_thar.jpg"),
            ("Toyota Fortuner Legender","SUV",8000,"Auto","Diesel",7,"Mumbai","/static/images/toyota_fortuner.jpg"),
            ("BMW 3 Series M Sport","Luxury",12000,"Auto","Petrol",5,"Delhi","/static/images/bmw_3series.jpg"),
            ("Mercedes-Benz C-Class","Luxury",14000,"Auto","Diesel",5,"Bangalore","/static/images/mercedes_cclass.jpg"),
            ("Maruti Suzuki Baleno","Hatchback",2000,"Manual","Petrol",5,"Chennai","/static/images/baleno.jpg"),
            ("Ford Endeavour","SUV",7500,"Auto","Diesel",7,"Goa","/static/images/ford_endeavour.webp"),
            ("Rolls-Royce Phantom","Ultra-Luxury",120000,"Auto","Petrol",5,"Mumbai","/static/images/rolls_royce_phantom.jpg"),
            ("Bentley Continental GT","Luxury GT",85000,"Auto","Petrol",4,"Delhi","/static/images/bentley_gt.jpg"),
            ("Mercedes Maybach GLS","Luxury SUV",75000,"Auto","Petrol",5,"Pune","/static/images/maybach_gls.jpg"),
            ("Lamborghini Revuelto","Supercar",150000,"Auto","Hybrid",2,"Bangalore","/static/images/lamborghini_revuelto.jpg"),
            ("Ferrari SF90 Stradale","Supercar",150000,"Auto","Hybrid",2,"Mumbai","/static/images/ferrari_sf90.webp"),
            ("Range Rover","Luxury SUV",45000,"Auto","Petrol",5,"Pune","/static/images/range_rover.jpg"),
            ("Tesla Cybertruck","Electric SUV",25000,"Auto","Electric",5,"Hyderabad","/static/images/tesla_cybertruck.jpg"),
            ("Audi e-tron","Electric SUV",18000,"Auto","Electric",5,"Delhi","/static/images/audi_etron.jpg"),
            ("Volvo EX30","Electric SUV",12000,"Auto","Electric",5,"Chennai","/static/images/volvo_ex30.jpg"),
            ("Porsche 911","Sports",40000,"Auto","Petrol",4,"Pune","/static/images/porsche_911.jpg"),
            ("Porsche Taycan Turbo S","Electric Sports",50000,"Auto","Electric",4,"Bangalore","/static/images/porsche_taycan.jpg"),
            ("Bugatti Divo","Hypercar",300000,"Auto","Petrol",2,"Dubai","/static/images/Bugatti Divo.webp"),
            ("Pagani Huayra","Hypercar",280000,"Auto","Petrol",2,"Monaco","/static/images/Pagani Huayra.webp"),
            ("Nissan GT-R","Sports",35000,"Auto","Petrol",4,"Tokyo","/static/images/Nissan GT-R.webp"),
            ("Aston Martin Valkyrie","Hypercar",320000,"Auto","Hybrid",2,"London","/static/images/Aston Martin Valkyrie.webp"),
            ("Ford GT","Supercar",90000,"Auto","Petrol",2,"Detroit","/static/images/Ford GT.webp"),
            ("Ford Mustang Boss 302","Muscle",25000,"Manual","Petrol",4,"Texas","/static/images/Ford Mustang Boss 302.webp"),
            ("Ford Mustang Dark Horse","Muscle",30000,"Manual","Petrol",4,"Texas","/static/images/Ford Mustang Dark Horse.webp"),
            ("Lamborghini Veneno","Hypercar",400000,"Auto","Petrol",2,"Rome","/static/images/Lamborghini Veneno.webp"),
            ("Batmobile","Concept",500000,"Auto","Electric",2,"Gotham","/static/images/bat mobile.webp"),
            ("Red Bull RB16B","F1",500000,"Auto","Hybrid",1,"Austria","/static/images/Red Bull RB16B.webp"),
        ]
        for name, cat, price, trans, fuel, seats, loc, img in cars_data:
            db.session.add(Car(
                name=name, category=cat, price_per_day=price,
                transmission=trans, fuel_type=fuel, seats=seats,
                location=loc, image_url=img, status='Available',
            ))
        import os as _os
        # SECURITY: read admin credentials from env vars — never hardcode passwords
        admin_email    = _os.environ.get('ADMIN_EMAIL',    'harshs1929@gmail.com')
        admin_password = _os.environ.get('ADMIN_PASSWORD', '')
        if not admin_password:
            import secrets as _sec
            admin_password = _sec.token_urlsafe(16)
            print(f"[DriveX] !! Auto-generated admin password: {admin_password}")
            print(f"[DriveX] !! Set ADMIN_PASSWORD env var to avoid this.")
        admin = User(
            name="Admin User", email=admin_email,
            password=_hash(admin_password, method='pbkdf2:sha256'),
            role='Admin', kyc_status='Verified', referral_code='ADMIN0000',
        )
        db.session.add(admin)
        db.session.add_all([
            Coupon(code="WELCOME20", discount_amount=500),
            Coupon(code="SUMMER10",  discount_amount=200),
        ])
        db.session.commit()
    return "Database reset successfully! <a href='/'>Go Home</a>"
