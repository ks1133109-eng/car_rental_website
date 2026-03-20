from flask_login import UserMixin
from extensions import db
from config import Config
import os as _os
import base64 as _b64

def _get_fernet():
    """Return a Fernet cipher if FIELD_ENCRYPT_KEY is set, else None."""
    key = _os.environ.get('FIELD_ENCRYPT_KEY', '')
    if not key:
        return None
    try:
        from cryptography.fernet import Fernet
        # Key must be 32 url-safe base64 bytes; pad/trim if needed
        raw = key.encode()
        # If it looks like a valid Fernet key already, use it directly
        if len(raw) == 44 and raw.endswith(b'='):
            return Fernet(raw)
        # Otherwise derive a 32-byte key from it
        import hashlib
        hashed = hashlib.sha256(raw).digest()
        fernet_key = _b64.urlsafe_b64encode(hashed)
        return Fernet(fernet_key)
    except Exception:
        return None

def encrypt_field(value):
    """Encrypt a string field. Returns ciphertext prefixed with 'enc:' or plain value."""
    if not value:
        return value
    f = _get_fernet()
    if not f:
        return value  # dev mode — store plain
    try:
        return 'enc:' + f.encrypt(value.encode()).decode()
    except Exception:
        return value

def decrypt_field(value):
    """Decrypt a field encrypted by encrypt_field(). Returns plaintext."""
    if not value or not value.startswith('enc:'):
        return value  # already plain (dev mode or pre-encryption data)
    f = _get_fernet()
    if not f:
        return value  # can't decrypt without key — return as-is
    try:
        return f.decrypt(value[4:].encode()).decode()
    except Exception:
        return value  # return as-is if decryption fails


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
    gov_id         = db.Column(db.String(500))  # encrypted in production
    # Stores Cloudinary URL (or base64 in dev mode).
    # Stores Cloudinary URL (or base64 in dev mode)
    # String(500) — Cloudinary URLs are short strings, not megabytes of base64
    gov_id_image   = db.Column(db.String(500))
    user_selfie    = db.Column(db.String(500))
    email_verified = db.Column(db.Boolean, default=False, nullable=False)
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
