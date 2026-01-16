import os
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    login_required,
    logout_user,
    current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

# --------------------
# App Configuration
# --------------------
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'drivex-secret-key-2026')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///drivex.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --------------------
# Database Models
# --------------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
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
    rating = db.Column(db.Float, default=4.5)
    trips_completed = db.Column(db.Integer, default=0)
    is_available = db.Column(db.Boolean, default=True)


class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    car_id = db.Column(db.Integer, db.ForeignKey('car.id'), nullable=False)
    status = db.Column(db.String(50), default='Upcoming')
    total_cost = db.Column(db.Integer)
    date_booked = db.Column(db.DateTime, default=datetime.utcnow)

    car = db.relationship('Car')


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# --------------------
# Database Initialization
# --------------------
with app.app_context():
    db.create_all()

    if not Car.query.first():
        cars = [
            Car(
                name="Maruti Suzuki Swift",
                category="Hatchback",
                price_per_hr=75,
                transmission="Manual",
                fuel_type="Petrol",
                seats=5,
                image_url="https://images.unsplash.com/photo-1549317661-bd32c8ce0db2?w=600"
            ),
            Car(
                name="Hyundai i20",
                category="Hatchback",
                price_per_hr=95,
                transmission="Auto",
                fuel_type="Petrol",
                seats=5,
                image_url="https://images.unsplash.com/photo-1609521263047-f8f205293f24?w=600"
            )
        ]
        db.session.add_all(cars)

        admin = User(
            name="Admin User",
            email="admin@drivex.com",
            password=generate_password_hash("admin123"),
            is_admin=True
        )
        db.session.add(admin)
        db.session.commit()


# --------------------
# Routes
# --------------------
@app.route('/')
def home():
    cars = Car.query.filter_by(is_available=True).all()
    return render_template('index.html', cars=cars)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('admin_dashboard' if user.is_admin else 'dashboard'))

        flash('Invalid email or password')

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')

        if User.query.filter_by(email=email).first():
            flash('Email already exists')
        else:
            user = User(
                name=name,
                email=email,
                password=generate_password_hash(password)
            )
            db.session.add(user)
            db.session.commit()
            login_user(user)
            return redirect(url_for('home'))

    return render_template('register.html')


@app.route('/book/<int:car_id>', methods=['POST'])
@login_required
def book_car(car_id):
    car = Car.query.get_or_404(car_id)

    booking = Booking(
        user_id=current_user.id,
        car_id=car.id,
        total_cost=car.price_per_hr * 24
    )
    car.is_available = False
    db.session.add(booking)
    db.session.commit()

    return redirect(url_for('dashboard'))


@app.route('/dashboard')
@login_required
def dashboard():
    bookings = Booking.query.filter_by(user_id=current_user.id).all()
    return render_template('dashboard.html', bookings=bookings)


@app.route('/admin')
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        return redirect(url_for('home'))

    cars = Car.query.all()
    return render_template('admin.html', cars=cars)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))


# --------------------
# Run App (local only)
# --------------------
if __name__ == '__main__':
    app.run(debug=True)
