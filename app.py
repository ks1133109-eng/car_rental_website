import os
import uuid  # ✅ Required for Single Session Security
from flask import Flask, render_template, redirect, url_for, request, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

# --- Configuration ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'drivex-secret-key-2026'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 

# Database Configuration
database_url = os.environ.get('DATABASE_URL')
if database_url:
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///drivex.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.session_protection = "strong"

# --- Models ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(20))
    address = db.Column(db.String(200))
    gov_id = db.Column(db.String(50)) 
    gov_id_image = db.Column(db.Text) 
    user_selfie = db.Column(db.Text) 
    kyc_status = db.Column(db.String(20), default='Unverified')
    is_admin = db.Column(db.Boolean, default=False)
    
    # ✅ FIX #4: Single Session Token
    session_token = db.Column(db.String(100), nullable=True)

class Car(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50))
    price_per_hr = db.Column(db.Integer, nullable=False)
    image_url = db.Column(db.String(500), nullable=False)
    transmission = db.Column(db.String(20))
    fuel_type = db.Column(db.String(20))
    seats = db.Column(db.Integer)
    is_available = db.Column(db.Boolean, default=True)
    location = db.Column(db.String(50), default='Mumbai')
    reviews = db.relationship('Review', backref='car', lazy=True)

    @property
    def average_rating(self):
        if not self.reviews:
            return 5.0
        return round(sum([r.rating for r in self.reviews]) / len(self.reviews), 1)

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    car_id = db.Column(db.Integer, db.ForeignKey('car.id'))
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.String(500))
    date_posted = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User')

class Coupon(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    discount_amount = db.Column(db.Integer, nullable=False)
    is_active = db.Column(db.Boolean, default=True)

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    car_id = db.Column(db.Integer, db.ForeignKey('car.id'))
    status = db.Column(db.String(50), default='Upcoming')
    base_cost = db.Column(db.Integer)
    driver_cost = db.Column(db.Integer, default=0)
    discount = db.Column(db.Integer, default=0)
    total_cost = db.Column(db.Integer)
    with_driver = db.Column(db.Boolean, default=False)
    payment_method = db.Column(db.String(30))
    start_date = db.Column(db.DateTime)
    end_date = db.Column(db.DateTime)
    date_booked = db.Column(db.DateTime, default=datetime.utcnow)
    car = db.relationship('Car')
    user = db.relationship('User')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ✅ FIX #4: Force Logout if logged in elsewhere
@app.before_request
def check_session_token():
    if current_user.is_authenticated:
        if current_user.session_token != session.get('token'):
            logout_user()
            flash('You have been logged out because your account was accessed from another device.')
            return redirect(url_for('login'))

# --- Routes ---
@app.route('/')
def home():
    locations = [c[0] for c in db.session.query(Car.location).distinct().all()]
    cars = Car.query.filter_by(is_available=True).all()
    return render_template('index.html', cars=cars, locations=locations)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email').lower()
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            
            # ✅ FIX #4: Generate unique session token
            new_token = str(uuid.uuid4())
            user.session_token = new_token
            db.session.commit()
            
            login_user(user)
            session['token'] = new_token  # Save to browser session
            
            # ✅ FIX #10: Redirect to Home (unless admin)
            if user.is_admin:
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('home'))
            
        flash('Invalid credentials')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email').lower()
        password = request.form.get('password')
        if User.query.filter_by(email=email).first():
            flash('Email exists')
            return redirect(url_for('login'))
        hashed_pw = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(name=name, email=email, password=hashed_pw)
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for('home')) # Redirect to Home
    return render_template('register.html')

@app.route('/fleet')
def fleet():
    location = request.args.get('location')
    category = request.args.get('category')
    fuel_type = request.args.get('fuel_type')
    seats = request.args.get('seats')
    start_str = request.args.get('start_date')
    end_str = request.args.get('end_date')

    query = Car.query.filter_by(is_available=True)

    if location and location != 'All':
        query = query.filter_by(location=location)
    if category and category != 'All':
        query = query.filter_by(category=category)
    if fuel_type and fuel_type != 'All':
        query = query.filter_by(fuel_type=fuel_type)
    if seats and seats != 'All':
        query = query.filter_by(seats=int(seats))

    if start_str and end_str:
        try:
            req_start = datetime.strptime(start_str, '%Y-%m-%d')
            req_end = datetime.strptime(end_str, '%Y-%m-%d').replace(hour=23, minute=59)
            busy_subquery = db.session.query(Booking.car_id).filter(
                Booking.status != 'Cancelled',
                Booking.start_date < req_end,
                Booking.end_date > req_start
            ).subquery()
            query = query.filter(Car.id.notin_(busy_subquery))
        except ValueError:
            pass

    cars = query.all()
    locations = [c[0] for c in db.session.query(Car.location).distinct().all()]
    categories = [c[0] for c in db.session.query(Car.category).distinct().all()]
    fuel_types = [c[0] for c in db.session.query(Car.fuel_type).distinct().all()]
    seat_options = [c[0] for c in db.session.query(Car.seats).distinct().order_by(Car.seats).all()]

    return render_template('fleet.html', cars=cars, locations=locations, categories=categories, fuel_types=fuel_types, seat_options=seat_options, current_filters=request.args)

@app.route('/kyc', methods=['GET', 'POST'])
@login_required
def kyc():
    if current_user.kyc_status == 'Verified':
        flash('You are already verified!')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        current_user.phone = request.form.get('phone')
        current_user.address = request.form.get('address')
        current_user.gov_id = request.form.get('gov_id')
        current_user.gov_id_image = request.form.get('gov_id_image_data')
        current_user.user_selfie = request.form.get('user_selfie_data')
        if not current_user.gov_id_image or not current_user.user_selfie:
            flash('⚠️ Please upload both your ID and take a selfie.')
            return redirect(url_for('kyc'))
        current_user.kyc_status = 'Pending'
        db.session.commit()
        flash('KYC Submitted! Please wait for Admin approval.')
        return redirect(url_for('dashboard'))
    return render_template('kyc.html')

@app.route('/book/<int:car_id>', methods=['GET', 'POST'])
@login_required
def book_car_dates(car_id):
    if current_user.kyc_status != 'Verified':
        if current_user.kyc_status == 'Pending':
            flash('⏳ Your KYC is Pending Approval.')
            return redirect(url_for('dashboard'))
        else:
            flash('⚠️ You must complete e-KYC Verification before booking.')
            return redirect(url_for('kyc'))
            
    car = Car.query.get_or_404(car_id)

    if request.method == 'POST':
        start_str = request.form.get('start_date')
        end_str = request.form.get('end_date')
        try:
            start_date = datetime.strptime(start_str, '%Y-%m-%dT%H:%M')
            end_date = datetime.strptime(end_str, '%Y-%m-%dT%H:%M')
        except ValueError:
            flash("Invalid date format.")
            return redirect(url_for('book_car_dates', car_id=car.id))

        # ✅ FIX #1: Minimum 1 day, Maximum 30 days
        duration_delta = end_date - start_date
        duration_hours = duration_delta.total_seconds() / 3600
        days = duration_delta.days

        if days < 1:
            flash("❌ Minimum booking duration is 24 hours (1 Day).")
            return redirect(url_for('book_car_dates', car_id=car.id))
        
        if days > 30:
            flash("❌ Maximum booking duration is 30 Days.")
            return redirect(url_for('book_car_dates', car_id=car.id))

        collision = Booking.query.filter(
            Booking.car_id == car.id,
            Booking.status != 'Cancelled',
            Booking.start_date < end_date,
            Booking.end_date > start_date
        ).first()

        if collision:
            s_fmt = collision.start_date.strftime('%d %b')
            e_fmt = collision.end_date.strftime('%d %b')
            flash(f'❌ Unavailable! This car is already booked from {s_fmt} to {e_fmt}.')
            return redirect(url_for('book_car_dates', car_id=car.id))

        base_cost = int(duration_hours * car.price_per_hr)
        driver_fee = 500 if 'with_driver' in request.form else 0
        tax = 648
        total_cost = base_cost + driver_fee + tax

        return render_template('booking_payment.html', 
                               car=car, 
                               start_date=start_str, 
                               end_date=end_str,
                               base_cost=base_cost,
                               driver_fee=driver_fee,
                               tax=tax,
                               total=total_cost,
                               with_driver=('with_driver' in request.form))

    return render_template('booking_dates.html', car=car)

@app.route('/book/apply-coupon', methods=['POST'])
@login_required
def apply_coupon():
    car_id = request.form.get('car_id')
    start_str = request.form.get('start_date')
    end_str = request.form.get('end_date')
    with_driver = request.form.get('with_driver') == 'True'
    coupon_code = request.form.get('coupon_code').strip().upper()
    
    car = Car.query.get_or_404(car_id)
    start_date = datetime.strptime(start_str, '%Y-%m-%dT%H:%M')
    end_date = datetime.strptime(end_str, '%Y-%m-%dT%H:%M')
    duration_hours = (end_date - start_date).total_seconds() / 3600
    
    base_cost = int(duration_hours * car.price_per_hr)
    driver_fee = 500 if with_driver else 0
    tax = 648
    
    discount = 0
    coupon = Coupon.query.filter_by(code=coupon_code, is_active=True).first()
    if coupon:
        discount = coupon.discount_amount
        flash(f'✅ Coupon Applied! You saved ₹{discount}')
    else:
        flash('❌ Invalid or Expired Coupon Code')
    
    total_cost = max(0, (base_cost + driver_fee + tax) - discount)

    return render_template('booking_payment.html', 
                           car=car, 
                           start_date=start_str, 
                           end_date=end_str,
                           base_cost=base_cost,
                           driver_fee=driver_fee,
                           tax=tax,
                           discount=discount,
                           total=total_cost,
                           with_driver=with_driver,
                           applied_coupon=coupon_code if discount > 0 else "")

@app.route('/book/confirm/<int:car_id>', methods=['POST'])
@login_required
def confirm_booking(car_id):
    car = Car.query.get_or_404(car_id)
    start_str = request.form.get('start_date')
    end_str = request.form.get('end_date')
    start_date = datetime.strptime(start_str, '%Y-%m-%dT%H:%M')
    end_date = datetime.strptime(end_str, '%Y-%m-%dT%H:%M')

    total_cost = float(request.form.get('total_cost'))
    base_cost = float(request.form.get('base_cost'))
    driver_fee = float(request.form.get('driver_fee'))
    discount = float(request.form.get('discount', 0))
    with_driver = request.form.get('with_driver') == 'True'
    payment_method = request.form.get('payment_method')

    new_booking = Booking(
        user_id=current_user.id,
        car_id=car.id,
        base_cost=base_cost,
        driver_cost=driver_fee,
        discount=discount,
        total_cost=total_cost,
        with_driver=with_driver,
        payment_method=payment_method,
        status='Paid' if payment_method != 'cod' else 'Confirmed',
        start_date=start_date,
        end_date=end_date
    )
    db.session.add(new_booking)
    db.session.commit()
    
    # ❌ Email Removed as requested
    
    return redirect(url_for('booking_success', booking_id=new_booking.id))

@app.route('/booking/success/<int:booking_id>')
@login_required
def booking_success(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    if booking.user_id != current_user.id:
        return redirect(url_for('dashboard'))
    return render_template('booking_success.html', booking=booking)

@app.route('/booking/invoice/<int:booking_id>')
@login_required
def invoice(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    if booking.user_id != current_user.id and not current_user.is_admin:
        return redirect(url_for('dashboard'))
    return render_template('invoice.html', booking=booking)

@app.route('/review/submit', methods=['POST'])
@login_required
def submit_review():
    car_id = request.form.get('car_id')
    rating = int(request.form.get('rating'))
    comment = request.form.get('comment')
    db.session.add(Review(user_id=current_user.id, car_id=car_id, rating=rating, comment=comment))
    db.session.commit()
    flash('Thank you for your feedback!')
    return redirect(url_for('my_bookings'))

# --- Account & Admin ---
@app.route('/dashboard')
@login_required
def dashboard():
    recent_bookings = Booking.query.filter_by(user_id=current_user.id).order_by(Booking.date_booked.desc()).limit(3).all()
    return render_template('dashboard.html', bookings=recent_bookings)

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        current_user.name = request.form.get('name')
        current_user.phone = request.form.get('phone')
        current_user.address = request.form.get('address')
        current_user.gov_id = request.form.get('gov_id')
        db.session.commit()
        flash('Profile updated!')
        return redirect(url_for('profile'))
    return render_template('profile.html')

@app.route('/my-bookings')
@login_required
def my_bookings():
    all_bookings = Booking.query.filter_by(user_id=current_user.id).order_by(Booking.date_booked.desc()).all()
    return render_template('my_bookings.html', bookings=all_bookings)

@app.route('/security', methods=['GET', 'POST'])
@login_required
def security():
    if request.method == 'POST':
        new_pw = request.form.get('new_password')
        current_user.password = generate_password_hash(new_pw, method='pbkdf2:sha256')
        db.session.commit()
        flash('Password changed successfully.')
    return render_template('security.html')

@app.route('/help')
def help_support():
    return render_template('help.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        flash('Message sent! We will get back to you shortly.')
        return redirect(url_for('contact'))
    return render_template('contact.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route('/admin')
@login_required
def admin_dashboard():
    if not current_user.is_admin: return redirect(url_for('home'))
    stats = {
        'total_fleet': Car.query.count(),
        'active_bookings': Booking.query.filter(Booking.status != 'Cancelled').count(),
        'pending_kyc': User.query.filter_by(kyc_status='Pending').count(),
        'revenue': db.session.query(db.func.sum(Booking.total_cost)).filter(Booking.status != 'Cancelled').scalar() or 0
    }
    pending_users = User.query.filter_by(kyc_status='Pending').all()
    return render_template('admin.html', stats=stats, pending_users=pending_users)

@app.route('/admin/approve-kyc/<int:user_id>')
@login_required
def approve_kyc(user_id):
    if not current_user.is_admin: return redirect(url_for('home'))
    user = User.query.get(user_id)
    if user:
        user.kyc_status = 'Verified'
        db.session.commit()
        flash(f'User {user.name} verified!')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/reject-kyc/<int:user_id>')
@login_required
def reject_kyc(user_id):
    if not current_user.is_admin: return redirect(url_for('home'))
    user = User.query.get(user_id)
    if user:
        user.kyc_status = 'Rejected'
        db.session.commit()
        flash(f'User {user.name} KYC rejected.')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/cars', methods=['GET', 'POST'])
@login_required
def manage_cars():
    if not current_user.is_admin: return redirect(url_for('home'))
    if request.method == 'POST':
        db.session.add(Car(
            name=request.form.get('name'), 
            price_per_hr=int(request.form.get('price')), 
            image_url=request.form.get('image'), 
            category=request.form.get('category'), 
            location=request.form.get('location'),
            transmission="Auto", 
            fuel_type="Petrol", 
            seats=5
        ))
        db.session.commit()
    cars = Car.query.all()
    return render_template('manage_cars.html', cars=cars)

@app.route('/admin/cars/delete/<int:id>')
@login_required
def delete_car(id):
    if not current_user.is_admin: return redirect(url_for('home'))
    db.session.delete(Car.query.get(id))
    db.session.commit()
    return redirect(url_for('manage_cars'))

@app.route('/admin/coupons', methods=['GET', 'POST'])
@login_required
def manage_coupons():
    if not current_user.is_admin: return redirect(url_for('home'))
    if request.method == 'POST':
        code = request.form.get('code').upper()
        discount = int(request.form.get('discount'))
        if Coupon.query.filter_by(code=code).first():
            flash('Error: Coupon code already exists!')
        else:
            db.session.add(Coupon(code=code, discount_amount=discount))
            db.session.commit()
            flash('Coupon created successfully!')
    coupons = Coupon.query.all()
    return render_template('manage_coupons.html', coupons=coupons)

@app.route('/admin/coupons/delete/<int:id>')
@login_required
def delete_coupon(id):
    if not current_user.is_admin: return redirect(url_for('home'))
    coupon = Coupon.query.get(id)
    if coupon:
        db.session.delete(coupon)
        db.session.commit()
    return redirect(url_for('manage_coupons'))

@app.route('/admin/bookings')
@login_required
def manage_bookings():
    if not current_user.is_admin: return redirect(url_for('home'))
    return render_template('manage_bookings.html', bookings=Booking.query.order_by(Booking.date_booked.desc()).all())

@app.route('/admin/booking/update/<int:id>/<status>')
@login_required
def update_booking(id, status):
    if not current_user.is_admin: return redirect(url_for('home'))
    booking = Booking.query.get(id)
    if booking:
        booking.status = status
        db.session.commit()
    return redirect(url_for('manage_bookings'))

@app.route('/admin/users')
@login_required
def manage_users():
    if not current_user.is_admin: return redirect(url_for('home'))
    return render_template('manage_users.html', users=User.query.all())

@app.route('/admin/users/delete/<int:id>')
@login_required
def delete_user(id):
    if not current_user.is_admin: return redirect(url_for('home'))
    user = User.query.get(id)
    if user and not user.is_admin:
        db.session.delete(user)
        db.session.commit()
    return redirect(url_for('manage_users'))

# --- Reset DB ---
@app.route('/reset-db')
def reset_db():
    with app.app_context():
        db.drop_all()
        db.create_all()
        if not Car.query.first():
            cars = [
                Car(name="Maruti Suzuki Swift", category="Hatchback", price_per_hr=75, transmission="Manual", fuel_type="Petrol", seats=5, location="Mumbai", image_url="https://images.unsplash.com/photo-1549317661-bd32c8ce0db2?w=600"),
                Car(name="Hyundai i20", category="Hatchback", price_per_hr=95, transmission="Auto", fuel_type="Petrol", seats=5, location="Delhi", image_url="https://images.unsplash.com/photo-1609521263047-f8f205293f24?w=600"),
                Car(name="Mahindra Thar", category="SUV", price_per_hr=180, transmission="Manual", fuel_type="Diesel", seats=4, location="Bangalore", image_url="https://images.unsplash.com/photo-1632245889029-e41314320873?w=600")
            ]
            db.session.add_all(cars)
            admin = User(name="Admin User", email="admin@drivex.com", password=generate_password_hash("admin123", method='pbkdf2:sha256'), is_admin=True, kyc_status='Verified')
            db.session.add(admin)
            c1 = Coupon(code="WELCOME20", discount_amount=200)
            db.session.add(c1)
            db.session.commit()
    return "Database has been reset! Cars are now distributed in Mumbai, Delhi, and Bangalore. Please <a href='/register'>Register Again</a>."

if __name__ == '__main__':
    app.run(debug=True)
