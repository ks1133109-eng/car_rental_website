import os
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

# --- Configuration ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-change-this-in-prod')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- Database Models ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)

class Car(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    price = db.Column(db.Integer, nullable=False)
    image_url = db.Column(db.String(500), nullable=False)
    is_available = db.Column(db.Boolean, default=True)

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    car_id = db.Column(db.Integer, db.ForeignKey('car.id'), nullable=False)
    date_booked = db.Column(db.DateTime, default=datetime.utcnow)
    
    car = db.relationship('Car', backref='bookings')

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
        username = request.form.get('username')
        password = request.form.get('password')
        action = request.form.get('action')

        if action == 'register':
            if User.query.filter_by(username=username).first():
                flash('Username already exists.')
            else:
                hashed_pw = generate_password_hash(password, method='pbkdf2:sha256')
                new_user = User(username=username, password=hashed_pw)
                db.session.add(new_user)
                db.session.commit()
                login_user(new_user)
                return redirect(url_for('home'))
        else: # Login
            user = User.query.filter_by(username=username).first()
            if user and check_password_hash(user.password, password):
                login_user(user)
                return redirect(url_for('home'))
            else:
                flash('Login failed. Check details.')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route('/book/<int:car_id>')
@login_required
def book_car(car_id):
    car = Car.query.get_or_404(car_id)
    if car.is_available:
        booking = Booking(user_id=current_user.id, car_id=car.id)
        car.is_available = False # Mark as rented
        db.session.add(booking)
        db.session.commit()
        flash(f'You successfully booked the {car.name}!')
    else:
        flash('This car is no longer available.')
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
@login_required
def dashboard():
    bookings = Booking.query.filter_by(user_id=current_user.id).all()
    return render_template('dashboard.html', bookings=bookings)

# --- Database Seeder (Run once) ---
def seed_database():
    with app.app_context():
        db.create_all()
        if not Car.query.first():
            cars = [
                Car(name="Toyota Camry", type="Sedan", price=50, image_url="https://images.unsplash.com/photo-1617788138017-80ad40651399?w=500"),
                Car(name="Ford Mustang", type="Sport", price=120, image_url="https://images.unsplash.com/photo-1580273916550-e323be2ebcc5?w=500"),
                Car(name="Jeep Wrangler", type="SUV", price=90, image_url="https://images.unsplash.com/photo-1533473359331-0135ef1b58bf?w=500")
            ]
            db.session.add_all(cars)
            db.session.commit()
            print("Database initialized with dummy cars.")

if __name__ == '__main__':
    seed_database() # Auto-create DB on start
    app.run(debug=True)
