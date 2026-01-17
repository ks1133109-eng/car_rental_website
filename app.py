import os
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

# --- Configuration ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'drivex-secret-key-2026'

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
    discount_amount = db.Column(db.Integer, nullable=False) # e.g., 500 (Rupees)
    is_active = db.Column(db.Boolean, default=True)

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    car_id = db.Column(db.Integer, db.ForeignKey('car.id'))
    status = db.Column(db.String(50), default='Upcoming')
    
    # Cost Breakdown
    base_cost = db.Column(db.Integer) # Car rental cost
    driver_cost = db.Column(db.Integer, default=0) # Chauffeur cost
    discount = db.Column(db.Integer, default=0) # Coupon discount
    total_cost = db.Column(db.Integer) # Final Amount
    
    # Details
    with_driver = db.Column(db.Boolean, default=False)
    date_booked = db.Column(db.DateTime, default=datetime.utcnow)
    
    car = db.relationship('Car')
    user = db.relationship('User')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Routes ---
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
        return redirect(url_for('home'))
    return render_template('register.html')

# --- BOOKING LOGIC (UPDATED) ---
@app.route('/book/<int:car_id>', methods=['GET', 'POST'])
@login_required
def book_car(car_id):
    car = Car.query.get_or_404(car_id)
    
    if request.method == 'POST':
        # 1. Calculate Base Cost (24 hours standard)
        base_price = car.price_per_hr * 24
        
        # 2. Check Driver Option
        needs_driver = 'with_driver' in request.form
        driver_fee = 500 if needs_driver else 0
        
        # 3. Check Coupon
        coupon_code = request.form.get('coupon_code').strip().upper()
        discount_value = 0
        
        if coupon_code:
            coupon = Coupon.query.filter_by(code=coupon_code, is_active=True).first()
            if coupon:
                discount_value = coupon.discount_amount
                flash(f'Coupon Applied! Saved ₹{discount_value}')
            else:
                flash('Invalid Coupon Code')
        
        # 4. Final Total
        final_total = (base_price + driver_fee + 648) - discount_value # 648 is Tax
        
        # 5. Create Booking
        new_booking = Booking(
            user_id=current_user.id,
            car_id=car.id,
            base_cost=base_price,
            driver_cost=driver_fee,
            discount=discount_value,
            total_cost=final_total,
            with_driver=needs_driver,
            status="Confirmed"
        )
        db.session.add(new_booking)
        db.session.commit()
        return redirect(url_for('dashboard'))
        
    return render_template('booking_details.html', car=car)

@app.route('/booking/invoice/<int:booking_id>')
@login_required
def invoice(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    # Security: Ensure user owns this booking
    if booking.user_id != current_user.id and not current_user.is_admin:
        return redirect(url_for('dashboard'))
    return render_template('invoice.html', booking=booking)

@app.route('/dashboard')
@login_required
def dashboard():
    recent_bookings = Booking.query.filter_by(user_id=current_user.id).order_by(Booking.date_booked.desc()).limit(3).all()
    return render_template('dashboard.html', bookings=recent_bookings)

@app.route('/fleet')
def fleet():
    category_filter = request.args.get('category')
    query = Car.query.filter_by(is_available=True)
    if category_filter and category_filter != 'All':
        query = query.filter_by(category=category_filter)
    cars = query.all()
    categories = [c[0] for c in db.session.query(Car.category).distinct().all()]
    return render_template('fleet.html', cars=cars, categories=categories, current_category=category_filter)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('home'))

# --- ADMIN & UTILS ---
@app.route('/admin')
@login_required
def admin_dashboard():
    if not current_user.is_admin: return redirect(url_for('home'))
    stats = {
        'total_fleet': Car.query.count(),
        'active_bookings': Booking.query.count(),
        'revenue': db.session.query(db.func.sum(Booking.total_cost)).scalar() or 0
    }
    return render_template('admin.html', stats=stats)

# (Keeping your other Admin routes for Cars/Users/Bookings...)
@app.route('/admin/bookings')
@login_required
def manage_bookings():
    if not current_user.is_admin: return redirect(url_for('home'))
    return render_template('manage_bookings.html', bookings=Booking.query.order_by(Booking.date_booked.desc()).all())

# --- RESET DB (With Coupon Seeding) ---
@app.route('/reset-db')
def reset_db():
    with app.app_context():
        db.drop_all()
        db.create_all()
        
        # Seed Cars
        if not Car.query.first():
            cars = [
                Car(name="Maruti Suzuki Swift", category="Hatchback", price_per_hr=75, transmission="Manual", fuel_type="Petrol", seats=5, image_url="https://images.unsplash.com/photo-1549317661-bd32c8ce0db2?w=600"),
                Car(name="Honda City", category="Sedan", price_per_hr=140, transmission="Auto", fuel_type="Petrol", seats=5, image_url="https://images.unsplash.com/photo-1550355291-bbee04a92027?w=600"),
                Car(name="Mahindra Thar", category="SUV", price_per_hr=180, transmission="Manual", fuel_type="Diesel", seats=4, image_url="https://images.unsplash.com/photo-1632245889029-e41314320873?w=600")
            ]
            db.session.add_all(cars)
            
            # Seed Admin
            admin = User(name="Admin User", email="admin@drivex.com", password=generate_password_hash("admin123", method='pbkdf2:sha256'), is_admin=True)
            db.session.add(admin)
            
            # Seed Coupons (Idea 2)
            c1 = Coupon(code="WELCOME20", discount_amount=200)
            c2 = Coupon(code="DRIVEX500", discount_amount=500)
            db.session.add_all([c1, c2])
            
            db.session.commit()
    return "Database reset! Coupons 'WELCOME20' and 'DRIVEX500' are active. <a href='/register'>Register Now</a>"

if __name__ == '__main__':
    app.run(debug=True)
        
