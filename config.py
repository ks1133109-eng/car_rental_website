import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class Config:
    _secret = os.environ.get('SECRET_KEY', '')
    # SECURITY: In production (RENDER env set), refuse to start with no SECRET_KEY.
    # In dev, fall back to a fixed string so local runs still work.
    if not _secret:
        if os.environ.get('RENDER'):
            raise RuntimeError(
                "SECRET_KEY environment variable must be set in production. "
                "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        _secret = 'drivex-dev-only-secret-key-2026-NOT-FOR-PRODUCTION'
    SECRET_KEY = _secret
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 1800
    SESSION_COOKIE_SECURE = bool(os.environ.get('RENDER'))
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024

    # ✅ Cloudinary config (FIXED - inside class)
    CLOUDINARY_CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME")
    CLOUDINARY_API_KEY = os.environ.get("CLOUDINARY_API_KEY")
    CLOUDINARY_API_SECRET = os.environ.get("CLOUDINARY_API_SECRET")

    # ── Database ─────────────────────────────────────
    _database_url = os.environ.get('DATABASE_URL', '')

    if _database_url and _database_url.startswith('postgres://'):
        _database_url = _database_url.replace('postgres://', 'postgresql://', 1)

    if _database_url and "sslmode" not in _database_url:
        _database_url += "?sslmode=require"

    SQLALCHEMY_DATABASE_URI = _database_url or 'sqlite:///drivex.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Optimized for Supabase (free tier disconnects idle connections at ~300s)
    # pool_recycle=200 ensures connections are replaced well before Supabase kills them.
    # connect_args keepalives prevent silent TCP drops on long-idle connections.
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 2,
        'max_overflow': 3,
        'pool_recycle': 200,        # Well under Supabase's 300s idle timeout
        'pool_pre_ping': True,      # Test connection before use (catches stale connections)
        'pool_timeout': 20,         # Don't wait forever for a connection
        'connect_args': {
            'connect_timeout': 10,
            'keepalives': 1,
            'keepalives_idle': 60,
            'keepalives_interval': 10,
            'keepalives_count': 5,
        },
    }

    # ── Payment ─────────────────────────────────────
    RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID', '')
    RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET', '')

    # ── Email ─────────────────────────────────────
    RESEND_API_KEY = os.environ.get('RESEND_API_KEY', '')

    # ── CSP ─────────────────────────────────────
    CSP = {
        'default-src': ["'self'"],
        'script-src': [
            "'self'", "'unsafe-inline'",
            "https://cdn.jsdelivr.net",
            "https://cdnjs.cloudflare.com",
            "https://unpkg.com",
            "https://checkout.razorpay.com"
        ],
        'style-src': [
            "'self'", "'unsafe-inline'",
            "https://cdnjs.cloudflare.com",
            "https://fonts.googleapis.com",
            "https://unpkg.com"
        ],
        'font-src': [
            "'self'",
            "https://cdnjs.cloudflare.com",
            "https://fonts.gstatic.com",
            "data:"
        ],
        'img-src': ["'self'", "data:", "blob:", "https:", "https://res.cloudinary.com"],
        'connect-src': [
            "'self'",
            "https://api.cloudinary.com",
            "https://cdn.jsdelivr.net",
            "https://unpkg.com",
            "https://api.razorpay.com",
            "https://lumberjack.razorpay.com",
            "https://nominatim.openstreetmap.org",
            "https://tile.openstreetmap.org",
            "https://*.tile.openstreetmap.org",
            "https://a.tile.openstreetmap.org",
            "https://b.tile.openstreetmap.org",
            "https://c.tile.openstreetmap.org",
        ],
        'frame-src': [
            "'self'",
            "https://api.razorpay.com",
            "https://checkout.razorpay.com"
        ],
        'worker-src': ["'self'"],
        'manifest-src': ["'self'"],
        'child-src': ["'self'", "blob:"],
    }

    # ── Loyalty ─────────────────────────────────────
    LOYALTY_TIERS = {
        'Bronze':   {'min': 0,     'points_rate': 1,   'discount_pct': 0,  'color': '#cd7f32', 'icon': '🥉'},
        'Silver':   {'min': 5000,  'points_rate': 1.5, 'discount_pct': 5,  'color': '#94a3b8', 'icon': '🥈'},
        'Gold':     {'min': 20000, 'points_rate': 2,   'discount_pct': 10, 'color': '#f59e0b', 'icon': '🥇'},
        'Platinum': {'min': 50000, 'points_rate': 3,   'discount_pct': 15, 'color': '#6366f1', 'icon': '💎'},
    }
