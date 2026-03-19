import os
import random
import string
import uuid
from flask import request, session
from flask_login import current_user, logout_user
from extensions import db
from models.other_models import AuditLog, Notification


# ── Referral code generator ───────────────────────────────────────

def generate_referral_code(length=8):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


# ── Session token enforcement ─────────────────────────────────────

def check_session_token():
    from flask import redirect, url_for, flash

    try:
        if current_user.is_authenticated:
            if current_user.session_token != session.get('token'):
                logout_user()
                flash('Logged out: Account accessed from another device.')
                return redirect(url_for('auth.login'))
    except Exception:
        # Prevent crash if DB connection fails
        return None

def generate_and_store_session_token(user):
    """Create a new UUID session token, persist it, store it in Flask session."""
    new_token          = str(uuid.uuid4())
    user.session_token = new_token
    db.session.commit()
    session['token']  = new_token
    session.permanent = True
    return new_token


# ── Audit logging ─────────────────────────────────────────────────

def log_action(action, details=None):
    """Write an AuditLog entry for the currently logged-in user."""
    if current_user.is_authenticated:
        try:
            db.session.add(AuditLog(
                user_id    = current_user.id,
                action     = action,
                details    = details,
                ip_address = request.remote_addr,
            ))
            db.session.commit()
        except Exception:
            db.session.rollback()


# ── Push notifications ────────────────────────────────────────────

def push_notification(user_id, message, link='/dashboard'):
    """Create an in-app notification for a user."""
    try:
        db.session.add(Notification(user_id=user_id, message=message, link=link))
        db.session.commit()
    except Exception as e:
        print(f"[push_notification error] {e}")
        db.session.rollback()


# ── PWA icon creator ──────────────────────────────────────────────

def create_pwa_icons(static_folder):
    icons_dir = os.path.join(static_folder, 'icons')
    os.makedirs(icons_dir, exist_ok=True)
    s192 = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="192" height="192" viewBox="0 0 192 192">'
        '<rect width="192" height="192" rx="40" fill="#2563EB"/>'
        '<text x="96" y="80" font-family="Arial Black,Arial" font-weight="900" font-size="46" '
        'fill="white" text-anchor="middle">Drive</text>'
        '<text x="96" y="138" font-family="Arial Black,Arial" font-weight="900" font-size="62" '
        'fill="#BFDBFE" text-anchor="middle">X</text></svg>'
    )
    s512 = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">'
        '<rect width="512" height="512" rx="96" fill="#2563EB"/>'
        '<text x="256" y="210" font-family="Arial Black,Arial" font-weight="900" font-size="122" '
        'fill="white" text-anchor="middle">Drive</text>'
        '<text x="256" y="368" font-family="Arial Black,Arial" font-weight="900" font-size="165" '
        'fill="#BFDBFE" text-anchor="middle">X</text></svg>'
    )
    for fname, content in [('icon-192.svg', s192), ('icon-512.svg', s512)]:
        p = os.path.join(icons_dir, fname)
        if not os.path.exists(p):
            open(p, 'w').write(content)
