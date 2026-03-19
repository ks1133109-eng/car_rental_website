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
limiter = Limiter(
    get_remote_address,
    default_limits     = ["500 per day", "100 per hour"],
    storage_uri        = "memory://",
    default_limits_exempt_when = lambda: False,
)

login_manager.login_view      = 'auth.login'
login_manager.session_protection = "strong"
