import os
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

# ---------------- CONFIG ----------------
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

# ---------------- MODELS ----------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    kyc_status = db.Column(db.String(20), default='Unverified')
    is_admin = db.Column(db.Boolean, default=False)

class Car(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    price_per_hr = db.Column(db.Integer)
    image_url = db.Column(db.String(500))
    is_available = db.Column(db.Boolean, default=True)

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    car_id = db.Column(db.Integer, db.ForeignKey('car.id'))
    base_cost = db.Column(db.Integer)
    total_cost = db.Column(db.Integer)
    payment_method = db.Column(db.String(30))
    status = db.Column(db.String(20), default="Confirmed")
    date_booked = db.Column(db.DateTime, default=datetime.utcnow)

    car = db.relationship('Car')
    user = db.relationship('User')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ---------------- ROUTES ----------------
@app.route('/')
def home():
    cars = Car.query.filter_by(is_available=True).all()
    return render_template('index.html', cars=cars)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(email=request.form['email']).first()
        if user and check_password_hash(user.password, request.form['password']):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash("Invalid credentials")
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        user = User(
            name=request.form['name'],
            email=request.form['email'],
            password=generate_password_hash(request.form['password'], method='pbkdf2:sha256')
        )
        db.session.add(user)
        db.session.commit()
        login_user(user)
        return redirect(url_for('dashboard'))
    return render_template('register.html')

@app.route('/dashboard')
@login_required
def dashboard():
    bookings = Booking.query.filter_by(user_id=current_user.id).all()
    return render_template('dashboard.html', bookings=bookings)

# ---------------- BOOKING ----------------
@app.route('/book/<int:car_id>', methods=['GET', 'POST'])
@login_required
def book_car(car_id):
    car = Car.query.get_or_404(car_id)

    if request.method == 'POST':
        base_price = car.price_per_hr * 24
        tax = 648
        total = base_price + tax

        new_booking = Booking(
            user_id=current_user.id,
            car_id=car.id,
            base_cost=base_price,
            total_cost=total
        )

        db.session.add(new_booking)
        db.session.commit()

        # ✅ CORRECT REDIRECT
        return redirect(url_for('payment_page', booking_id=new_booking.id))

    return render_template('booking_details.html', car=car)

# ---------------- PAYMENT ----------------
@app.route('/booking/<int:booking_id>/payment')
@login_required
def payment_page(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    if booking.user_id != current_user.id:
        return redirect(url_for('dashboard'))

    return render_template('payment.html', booking=booking)

@app.route('/pay/<int:booking_id>', methods=['POST'])
@login_required
def process_payment(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    if booking.user_id != current_user.id:
        return redirect(url_for('dashboard'))

    payment_method = request.form.get('payment_method')
    if not payment_method:
        flash("Please select a payment method")
        return redirect(url_for('payment_page', booking_id=booking_id))

    booking.payment_method = payment_method
    booking.status = "Paid"
    db.session.commit()

    return redirect(url_for('invoice', booking_id=booking.id))

# ---------------- INVOICE ----------------
@app.route('/booking/invoice/<int:booking_id>')
@login_required
def invoice(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    if booking.user_id != current_user.id:
        return redirect(url_for('dashboard'))

    return render_template('invoice.html', booking=booking)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('home'))

# ---------------- RUN ----------------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
