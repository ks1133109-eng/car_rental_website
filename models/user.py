from flask_login import UserMixin
from extensions import db
from config import Config


def get_loyalty_tier(total_spent):
    tier = 'Bronze'
    for name, config in Config.LOYALTY_TIERS.items():
        if total_spent >= config['min']:
            tier = name
    return tier


class User(UserMixin, db.Model):
    id             = db.Column(db.Integer, primary_key=True)
    name           = db.Column(db.String(100))
    email          = db.Column(db.String(120), unique=True, nullable=False)
    password       = db.Column(db.String(255), nullable=False)
    phone          = db.Column(db.String(20))
    address        = db.Column(db.String(200))
    gov_id         = db.Column(db.String(50))
    # Stores Cloudinary URL (or base64 in dev mode).
    # Stores Cloudinary URL (or base64 in dev mode)
    # String(500) — Cloudinary URLs are short strings, not megabytes of base64
    gov_id_image   = db.Column(db.String(500))
    user_selfie    = db.Column(db.String(500))
    kyc_status     = db.Column(db.String(20), default='Unverified')
    role           = db.Column(db.String(20), default='User')
    status         = db.Column(db.String(20), default='Active')
    session_token  = db.Column(db.String(100), nullable=True)
    two_fa_enabled = db.Column(db.Boolean, default=False, nullable=False)
    loyalty_points = db.Column(db.Integer, default=0)
    referral_code  = db.Column(db.String(20), unique=True, nullable=True)
    referred_by    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    owned_cars     = db.relationship('Car', backref='owner', lazy=True)

    @property
    def total_spent(self):
        from models.booking import Booking
        return sum(
            b.total_cost for b in Booking.query.filter_by(user_id=self.id).all()
            if b.status not in ['Cancelled']
        )

    @property
    def loyalty_tier(self):
        return get_loyalty_tier(self.total_spent)

    @property
    def loyalty_tier_config(self):
        return Config.LOYALTY_TIERS[self.loyalty_tier]

    @property
    def next_tier(self):
        tiers   = list(Config.LOYALTY_TIERS.items())
        current = self.loyalty_tier
        for i, (name, _) in enumerate(tiers):
            if name == current and i < len(tiers) - 1:
                return tiers[i + 1]
        return None
