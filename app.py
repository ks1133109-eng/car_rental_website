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

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    car_id = db.Column(db.Integer, db.ForeignKey('car.id'))
    status = db.Column(db.String(50), default='Upcoming')
    total_cost = db.Column(db.Integer)
    date_booked = db.Column(db.DateTime, default=datetime.utcnow)
    
    car = db.relationship('Car')
    user = db.relationship('User') # Added this to access user name in bookings

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
        return redirect(url_for('home'))
    return render_template('register.html')

@app.route('/book/<int:car_id>', methods=['GET', 'POST'])
@login_required
def book_car(car_id):
    car = Car.query.get_or_404(car_id)
    if request.method == 'POST':
        new_booking = Booking(
            user_id=current_user.id, car_id=car.id, 
            total_cost=(car.price_per_hr * 24), status="Confirmed"
        )
        db.session.add(new_booking)
        db.session.commit()
        return redirect(url_for('dashboard'))
    return render_template('booking_details.html', car=car)

@app.route('/dashboard')
@login_required
def dashboard():
    bookings = Booking.query.filter_by(user_id=current_user.id).order_by(Booking.date_booked.desc()).all()
    return render_template('dashboard.html', bookings=bookings)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('home'))

# --- ADMIN ROUTES (NEW FEATURES) ---

@app.route('/admin')
@login_required
def admin_dashboard():
    if not current_user.is_admin: return redirect(url_for('home'))
    stats = {
        'total_fleet': Car.query.count(),
        'active_bookings': Booking.query.filter(Booking.status != 'Cancelled').count(),
        'total_users': User.query.count(),
        'revenue': db.session.query(db.func.sum(Booking.total_cost)).filter(Booking.status != 'Cancelled').scalar() or 0
    }
    return render_template('admin.html', stats=stats)

# 1. Manage Cars (Add / View)
@app.route('/admin/cars', methods=['GET', 'POST'])
@login_required
def manage_cars():
    if not current_user.is_admin: return redirect(url_for('home'))
    
    if request.method == 'POST':
        # Add New Car Logic
        name = request.form.get('name')
        price = request.form.get('price')
        image = request.form.get('image')
        category = request.form.get('category')
        
        new_car = Car(
            name=name, price_per_hr=int(price), 
            image_url=image, category=category,
            transmission="Auto", fuel_type="Petrol", seats=5 # Defaults for demo
        )
        db.session.add(new_car)
        db.session.commit()
        flash('Car added successfully!')
    
    cars = Car.query.all()
    return render_template('manage_cars.html', cars=cars)

@app.route('/admin/cars/delete/<int:id>')
@login_required
def delete_car(id):
    if not current_user.is_admin: return redirect(url_for('home'))
    car = Car.query.get(id)
    if car:
        db.session.delete(car)
        db.session.commit()
        flash('Car deleted.')
    return redirect(url_for('manage_cars'))

# 2. Manage Bookings (View / Status Update)
@app.route('/admin/bookings')
@login_required
def manage_bookings():
    if not current_user.is_admin: return redirect(url_for('home'))
    bookings = Booking.query.order_by(Booking.date_booked.desc()).all()
    return render_template('manage_bookings.html', bookings=bookings)

@app.route('/admin/booking/update/<int:id>/<status>')
@login_required
def update_booking(id, status):
    if not current_user.is_admin: return redirect(url_for('home'))
    booking = Booking.query.get(id)
    if booking:
        booking.status = status
        db.session.commit()
    return redirect(url_for('manage_bookings'))

# 3. Manage Users (View / Delete)
@app.route('/admin/users')
@login_required
def manage_users():
    if not current_user.is_admin: return redirect(url_for('home'))
    users = User.query.all()
    return render_template('manage_users.html', users=users)

@app.route('/admin/users/delete/<int:id>')
@login_required
def delete_user(id):
    if not current_user.is_admin: return redirect(url_for('home'))
    user = User.query.get(id)
    if user and not user.is_admin: # Prevent deleting yourself
        db.session.delete(user)
        db.session.commit()
        flash('User removed.')
    return redirect(url_for('manage_users'))

# --- Seeder ---
def seed_data():
    with app.app_context():
        db.create_all()
        if not Car.query.first():
            # (Keep your existing seeder logic here, shortened for brevity)
            print("Database initialized.")

seed_data()

if __name__ == '__main__':
    app.run(debug=True)
