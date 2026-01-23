import os
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

# --- Configuration ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'drivex-secret-key-2026'
# Increase upload limit to 16MB just in case
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

# --- Models ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(20))
    address = db.Column(db.String(200))
    
    # KYC FIELDS (Updated for Images)
    gov_id = db.Column(db.String(50)) 
    # We use db.Text to store the Image Data (Base64 string)
    gov_id_image = db.Column(db.Text) 
    user_selfie = db.Column(db.Text) 
    kyc_status = db.Column(db.String(20), default='Unverified')
    
    is_admin = db.Column(db.Boolean, default=False)

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

    payment_method = db.Column(db.String(30))  # ✅ FIXED FIELD

    date_booked = db.Column(db.DateTime, default=datetime.utcnow)

    car = db.relationship('Car')
    user = db.relationship('User')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Public Routes ---
@app.route('/')
def home():
    cars = Car.query.filter_by(is_available=True).all()
    return render_template('index.html', cars=cars)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email').lower()
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard') if not user.is_admin else url_for('admin_dashboard'))
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
        return redirect(url_for('dashboard'))
    return render_template('register.html')

@app.route('/fleet')
def fleet():
    category_filter = request.args.get('category')
    query = Car.query.filter_by(is_available=True)
    if category_filter and category_filter != 'All':
        query = query.filter_by(category=category_filter)
    cars = query.all()
    categories = [c[0] for c in db.session.query(Car.category).distinct().all()]
    return render_template('fleet.html', cars=cars, categories=categories, current_category=category_filter)

# --- KYC & Booking ---

@app.route('/kyc', methods=['GET', 'POST'])
@login_required
def kyc():
    if current_user.kyc_status == 'Verified':
        flash('You are already verified!')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        # Get form data
        current_user.phone = request.form.get('phone')
        current_user.address = request.form.get('address')
        current_user.gov_id = request.form.get('gov_id')
        
        # Get the Base64 Image Strings (Hidden Inputs)
        current_user.gov_id_image = request.form.get('gov_id_image_data')
        current_user.user_selfie = request.form.get('user_selfie_data')
        
        # Validate that images were provided
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
def book_car(car_id):
    # KYC Gatekeeper
    if current_user.kyc_status != 'Verified':
        if current_user.kyc_status == 'Pending':
            flash('⏳ Your KYC is Pending Approval.')
            return redirect(url_for('dashboard'))
        else:
            flash('⚠️ You must complete e-KYC Verification before booking.')
            return redirect(url_for('kyc'))
    car = Car.query.get_or_404(car_id)
    if request.method == 'POST':
        base_price = car.price_per_hr * 24
        needs_driver = 'with_driver' in request.form
        driver_fee = 500 if needs_driver else 0
        coupon_input = request.form.get('coupon_code')
        coupon_code = coupon_input.strip().upper() if coupon_input else None
        discount_value = 0
        if coupon_code:
            coupon = Coupon.query.filter_by(code=coupon_code, is_active=True).first()
            if coupon:
                discount_value = coupon.discount_amount
                flash(f'Coupon Applied! Saved ₹{discount_value}')
        final_total = (base_price + driver_fee + 648) - discount_value
        new_booking = Booking(
            user_id=current_user.id, car_id=car.id, base_cost=base_price,
            driver_cost=driver_fee, discount=discount_value, total_cost=final_total,
            with_driver=needs_driver, status="Confirmed"
        )
        db.session.add(new_booking)
        db.session.commit()
        return redirect(url_for('payment_page', booking_id=booking.id) )
    return render_template('booking_details.html', car=car)

@app.route('/booking/<int:booking_id>/payment', methods=['GET'])
@login_required
def payment_page(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    # safety check
    if booking.user_id != current_user.id:
        return redirect(url_for('dashboard'))

    return render_template(
        'payment.html',
        booking=booking
    )
    
@app.route('/pay/<int:booking_id>', methods=['POST'])
@login_required
def process_payment(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    payment_method = request.form.get('payment_method')
    if not payment_method:
        flash("Please select a payment method")
        return redirect(url_for('payment_page', booking_id=booking_id))
    booking.status = "Paid"
    booking.payment_method = payment_method
    db.session.commit()
    return redirect(url_for('invoice', booking_id=booking.id))

@app.route('/booking/invoice/<int:booking_id>')
@login_required
def invoice(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    if booking.user_id != current_user.id and not current_user.is_admin:
        return redirect(url_for('dashboard'))

    return render_template('invoice.html', booking=booking)

# --- Account Routes ---

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

# --- Admin Routes ---

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
        db.session.add(Car(name=request.form.get('name'), price_per_hr=int(request.form.get('price')), image_url=request.form.get('image'), category=request.form.get('category'), transmission="Auto", fuel_type="Petrol", seats=5))
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
                Car(name="Maruti Suzuki Swift", category="Hatchback", price_per_hr=75, transmission="Manual", fuel_type="Petrol", seats=5, image_url="https://images.unsplash.com/photo-1549317661-bd32c8ce0db2?w=600"),
                Car(name="Hyundai i20", category="Hatchback", price_per_hr=95, transmission="Auto", fuel_type="Petrol", seats=5, image_url="https://images.unsplash.com/photo-1609521263047-f8f205293f24?w=600"),
                Car(name="Mahindra Thar", category="SUV", price_per_hr=180, transmission="Manual", fuel_type="Diesel", seats=4, image_url="https://images.unsplash.com/photo-1632245889029-e41314320873?w=600")
            ]
            db.session.add_all(cars)
            admin = User(name="Admin User", email="admin@drivex.com", password=generate_password_hash("admin123", method='pbkdf2:sha256'), is_admin=True, kyc_status='Verified')
            db.session.add(admin)
            c1 = Coupon(code="WELCOME20", discount_amount=200)
            db.session.add(c1)
            db.session.commit()
    return "Database has been reset! Please <a href='/register'>Register Again</a>."

if __name__ == '__main__':
    app.run(debug=True)
    
