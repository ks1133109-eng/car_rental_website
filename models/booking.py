from datetime import datetime, timedelta
from extensions import db


class Booking(db.Model):
    id               = db.Column(db.Integer, primary_key=True)
    user_id          = db.Column(db.Integer, db.ForeignKey('user.id'))
    car_id           = db.Column(db.Integer, db.ForeignKey('car.id'))
    status           = db.Column(db.String(50), default='Upcoming')
    base_cost        = db.Column(db.Integer)
    driver_cost      = db.Column(db.Integer, default=0)
    discount         = db.Column(db.Integer, default=0)
    delivery_type    = db.Column(db.String(20), default='Pickup')
    delivery_address = db.Column(db.String(500), nullable=True)
    delivery_fee     = db.Column(db.Integer, default=0)
    total_cost       = db.Column(db.Integer)
    with_driver      = db.Column(db.Boolean, default=False)
    payment_method      = db.Column(db.String(30))
    start_date       = db.Column(db.DateTime)
    end_date         = db.Column(db.DateTime)
    date_booked      = db.Column(
        db.DateTime,
        default=lambda: datetime.utcnow() + timedelta(hours=5, minutes=30)
    )
    points_earned        = db.Column(db.Integer, default=0)
    # Razorpay payment tracking — required for duplicate-booking prevention
    razorpay_order_id    = db.Column(db.String(100), nullable=True)
    razorpay_payment_id  = db.Column(db.String(100), nullable=True, index=True)
    car              = db.relationship('Car')
    user             = db.relationship('User')
