import os
import resend
from flask import Flask, request
from sqlalchemy.exc import OperationalError

from config import Config
from extensions import db, login_manager, limiter, csrf, talisman
from utils.helpers import check_session_token, create_pwa_icons


# ── Routes that should NEVER be rate-limited ─────────────────────────────────
# loader.io verification, PWA service worker, static assets, public read pages.
_EXEMPT_PREFIXES = (
    '/static/',
    '/loaderio-',
    '/',           # home — exempt; fleet is also exempt (see main.py decorators)
)


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    import cloudinary
    cloudinary.config(
        cloud_name=app.config['CLOUDINARY_CLOUD_NAME'],
        api_key=app.config['CLOUDINARY_API_KEY'],
        api_secret=app.config['CLOUDINARY_API_SECRET']
    )

    # ── Initialise extensions ────────────────────────────────────
    db.init_app(app)
    login_manager.init_app(app)
    limiter.init_app(app)
    csrf.init_app(app)
    talisman.init_app(
        app,
        content_security_policy   = config_class.CSP,
        force_https               = False,
        strict_transport_security = False,
        session_cookie_secure     = False,
        session_cookie_http_only  = True,
        frame_options             = 'SAMEORIGIN',
    )

    # ── Third-party SDK config ───────────────────────────────────
    resend.api_key = app.config.get('RESEND_API_KEY', '')

    # ── Register user loader ─────────────────────────────────────
    from models.user import User

    @login_manager.user_loader
    def load_user(user_id):
        try:
            return db.session.get(User, int(user_id))
        except OperationalError:
            return None

    # ── Session token guard (before_request) ─────────────────────
    app.before_request(check_session_token)

    # ── Response caching headers for public pages ─────────────────
    @app.after_request
    def add_cache_headers(response):
        path = request.path
        # Cache static assets aggressively
        if path.startswith('/static/'):
            response.cache_control.max_age = 86400  # 1 day
            response.cache_control.public  = True
        # Short cache for public read pages (home, fleet)
        elif path in ('/', '/fleet', '/about', '/help', '/contact'):
            response.cache_control.max_age = 60     # 1 minute
            response.cache_control.public  = True
        # Never cache auth / user-specific pages
        else:
            response.cache_control.no_store = True
        return response

    # ── Rate-limit error handler (429) ──────────────────────────
    from flask_limiter.errors import RateLimitExceeded
    from flask import render_template as _rt

    @app.errorhandler(RateLimitExceeded)
    def handle_rate_limit(e):
        # Friendly lockout page instead of raw 429
        limit_str = str(e.description) if hasattr(e, 'description') else str(e)
        # Detect how long the lockout is from the limit string
        if 'hour' in limit_str:
            wait_msg = 'Please wait 1 hour before trying again.'
        elif 'minute' in limit_str:
            wait_msg = 'Please wait 15 minutes before trying again.'
        else:
            wait_msg = 'Please wait a moment before trying again.'
        from flask import flash, redirect, url_for, request as _req
        flash(
            f'Too many attempts — your access has been temporarily locked. {wait_msg}',
            'danger'
        )
        # Redirect back to wherever they came from (login, register, etc.)
        referrer = _req.referrer or url_for('auth.login')
        return redirect(referrer), 303

    # ── Register blueprints ──────────────────────────────────────
    from routes.auth    import auth_bp
    from routes.main    import main_bp
    from routes.booking import booking_bp
    from routes.admin   import admin_bp
    from routes.client  import client_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(booking_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(client_bp)

    # ── Startup: create tables + PWA icons ───────────────────────
    with app.app_context():
        from models import User, Car, Booking  # noqa: F401
        from models.other_models import Review, Coupon, Offer, AuditLog, Notification, LoginAttempt  # noqa: F401
        db.create_all()
        create_pwa_icons(app.static_folder)

    return app


# ── Application entry point ──────────────────────────────────────
app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
