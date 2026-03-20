from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from flask_talisman import Talisman

db            = SQLAlchemy()
login_manager = LoginManager()
csrf          = CSRFProtect()
talisman      = Talisman()

# ── Rate Limiter ──────────────────────────────────────────────────────────────
# Default limits only apply to routes that don't have their own @limiter.limit().
# Public/read-only pages (home, fleet) are decorated with @limiter.exempt so
# load tests and crawlers don't get 429s.
# Auth routes keep tight per-route limits for brute-force protection.
import os as _os
_redis_url = _os.environ.get('REDIS_URL', '')

# Use Redis if configured (recommended for multi-worker production).
# Falls back to memory:// for local dev — each Gunicorn worker gets
# independent counters in memory mode, so brute-force limit is
# effectively multiplied by worker count. Set REDIS_URL on Render
# to get consistent limits: Render → Environment → REDIS_URL
if _redis_url:
    _storage_uri = _redis_url
else:
    import sys as _sys
    _sys.stderr.write(
        "[DriveX] WARNING: REDIS_URL not set — rate limiter using in-process "
        "memory. Set REDIS_URL on Render for consistent brute-force protection.\n"
    )
    _storage_uri = "memory://"

limiter = Limiter(
    get_remote_address,
    default_limits             = ["500 per day", "100 per hour"],
    storage_uri                = _storage_uri,
    default_limits_exempt_when = lambda: False,
)

login_manager.login_view      = 'auth.login'
login_manager.session_protection = "strong"
