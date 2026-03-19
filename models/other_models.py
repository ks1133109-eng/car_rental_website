from datetime import datetime, timedelta
from extensions import db


class Review(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('user.id'))
    car_id      = db.Column(db.Integer, db.ForeignKey('car.id'))
    rating      = db.Column(db.Integer, nullable=False)
    comment     = db.Column(db.String(500))
    date_posted = db.Column(
        db.DateTime,
        default=lambda: datetime.utcnow() + timedelta(hours=5, minutes=30)
    )
    user = db.relationship('User')


class Coupon(db.Model):
    id              = db.Column(db.Integer, primary_key=True)
    code            = db.Column(db.String(20), unique=True, nullable=False)
    discount_amount = db.Column(db.Integer, nullable=False)
    is_active       = db.Column(db.Boolean, default=True)


class Offer(db.Model):
    id                  = db.Column(db.Integer, primary_key=True)
    title               = db.Column(db.String(100), nullable=False)
    description         = db.Column(db.String(255))
    discount_percentage = db.Column(db.Integer, nullable=False)
    is_active           = db.Column(db.Boolean, default=False)


class AuditLog(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.id'))
    action     = db.Column(db.String(100), nullable=False)
    details    = db.Column(db.String(500))
    ip_address = db.Column(db.String(50))
    timestamp  = db.Column(
        db.DateTime,
        default=lambda: datetime.utcnow().replace(microsecond=0) + timedelta(hours=5, minutes=30)
    )
    user = db.relationship('User')


class Notification(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message    = db.Column(db.String(300), nullable=False)
    link       = db.Column(db.String(200), default='/dashboard')
    is_read    = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class LoginAttempt(db.Model):
    """
    Tracks failed login attempts per email address.
    Stored server-side so clearing cookies cannot bypass the lockout.
    Old records are pruned automatically on each login attempt.
    """
    id            = db.Column(db.Integer, primary_key=True)
    email         = db.Column(db.String(120), nullable=False, index=True)
    attempts      = db.Column(db.Integer, default=0, nullable=False)
    locked_until  = db.Column(db.DateTime, nullable=True)
    last_attempt  = db.Column(db.DateTime, default=datetime.utcnow)

    @classmethod
    def get_or_create(cls, email):
        record = cls.query.filter_by(email=email).first()
        if not record:
            record = cls(email=email, attempts=0)
            db.session.add(record)
        return record

    def is_locked(self):
        return self.locked_until is not None and datetime.utcnow() < self.locked_until

    def seconds_remaining(self):
        if not self.is_locked():
            return 0
        return int((self.locked_until - datetime.utcnow()).total_seconds())

    def record_failure(self, max_attempts=5, lockout_seconds=900):
        self.attempts     += 1
        self.last_attempt  = datetime.utcnow()
        if self.attempts >= max_attempts:
            self.locked_until = datetime.utcnow() + timedelta(seconds=lockout_seconds)
            self.attempts     = 0
        db.session.commit()

    def record_success(self):
        self.attempts     = 0
        self.locked_until = None
        self.last_attempt = datetime.utcnow()
        db.session.commit()

    @classmethod
    def cleanup_old(cls):
        """Delete records that are unlocked and haven't had an attempt in 24 h."""
        cutoff = datetime.utcnow() - timedelta(hours=24)
        cls.query.filter(
            cls.last_attempt < cutoff,
            (cls.locked_until == None) | (cls.locked_until < datetime.utcnow()),
        ).delete()
        db.session.commit()
