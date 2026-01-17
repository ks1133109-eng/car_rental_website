import os
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'drivex-secret-key-2026'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///drivex.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- Enhanced Models ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    # Ensure email is unique and indexed
    email = db.Column(db.String(120), unique=True, nullable=False)
    # Increased length to 255 to safely store long hashes
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
    rating = db.Column(db.Float, default=4.5)
    trips_completed = db.Column(db.Integer, default=0)
    is_available = db.Column(db.Boolean, default=True)

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    car_id = db.Column(db.Integer, db.ForeignKey('car.id'))
    status = db.Column(db.String(50), default='Upcoming')
    total_cost = db.Column(db.Integer)
    date_booked = db.Column(db.DateTime, default=datetime.utcnow)
    
    car = db.relationship('Car')

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
        # FIX: Force email to lowercase to match registration
        email = request.form.get('email').lower()
        password = request.form.get('password')
        
        print(f"DEBUG: Attempting login for {email}") # Debugging
        
        user = User.query.filter_by(email=email).first()
        
        if user:
            if check_password_hash(user.password, password):
                login_user(user)
                print("DEBUG: Login Successful")
                return redirect(url_for('dashboard') if not user.is_admin else url_for('admin_dashboard'))
            else:
                print("DEBUG: Password Incorrect")
                flash('Incorrect password. Please try again.')
        else:
            print("DEBUG: User not found")
            flash('Email not found. Please register first.')
            
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        # FIX: Force email to lowercase
        email = request.form.get('email').lower()
        password = request.form.get('password')
        
        if User.query.filter_by(email=email).first():
            flash('Email already exists. Please login.')
            return redirect(url_for('login'))
        else:
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
        # Create the booking
        new_booking = Booking(
            user_id=current_user.id, 
            car_id=car.id, 
            total_cost=(car.price_per_hr * 24), # Cost for 24 hours
            status="Completed" # Mark as completed for demo
        )
        db.session.add(new_booking)
        db.session.commit()
        
        flash(f'Booking confirmed for {car.name}!')
        return redirect(url_for('dashboard'))
        
    return render_template('booking_details.html', car=car)

@app.route('/dashboard')
@login_required
def dashboard():
    bookings = Booking.query.filter_by(user_id=current_user.id).order_by(Booking.date_booked.desc()).all()
    return render_template('dashboard.html', bookings=bookings)

@app.route('/admin')
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        return redirect(url_for('home'))
    stats = {
        'total_fleet': Car.query.count(),
        'active_bookings': Booking.query.count(),
        'revenue': "7,200"
    }
    cars = Car.query.all()
    return render_template('admin.html', stats=stats, cars=cars)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('home'))

# --------------------
# Database Initialization (Render-safe)
# --------------------
with app.app_context():
    db.create_all()

    if not Car.query.first():
        cars = [
            Car(name="Maruti Suzuki Swift", 
                category="Hatchback",
                price_per_hr=75,
                transmission="Manual",
                fuel_type="Petrol",
                seats=5,
    
             image_url="https://images.unsplash.com/photo-1549317661-bd32c8ce0db2?w=600"),
 
            Car(name="Hyundai i20",
                category="Hatchback",
                price_per_hr=95,
                transmission="Auto",
                fuel_type="Petrol",
                seats=5,
          
            image_url="https://images.unsplash.com/photo-1609521263047-f8f205293f24?w=600"),
     
           Car(name="Honda City",
                category="Sedan",
                price_per_hr=140,
                transmission="Auto",
                fuel_type="Petrol",
                seats=5,
               
            image_url="https://images.unsplash.com/photo-1550355291-bbee04a92027?w=600"),
  
           Car(name="Mahindra Thar",
               category="SUV",
               price_per_hr=180,
               transmission="Manual",
               fuel_type="Diesel",
               seats=4,
              
           image_url="https://images.unsplash.com/photo-1632245889029-e41314320873?w=600"),
         
          Car(name="Tata Nexon EV",
              category="SUV",
              price_per_hr=160,
              transmission="Auto",
              fuel_type="Electric",
              seats=5,
             
          image_url="https://images.unsplash.com/photo-1678721245345-429a6568858a?w=600")
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

if __name__ == '__main__':
    app.run(debug=True)
