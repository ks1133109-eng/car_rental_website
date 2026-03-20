import os
import time
import uuid
import secrets
from flask import Blueprint, render_template, redirect, url_for, request, flash, session, current_app
from flask_login import login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer
from extensions import db, limiter
from models.user import User
from models.other_models import LoginAttempt
from utils.helpers import (
    generate_referral_code, generate_and_store_session_token, log_action
)
from services.email_service import (
    send_otp_email, send_password_reset_email, send_referral_bonus_email
)

auth_bp = Blueprint('auth', __name__)


def _get_serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])


# ── Login ─────────────────────────────────────────────────────────

_MAX_LOGIN_ATTEMPTS = 5
_LOCKOUT_SECONDS    = 15 * 60   # 15 minutes

@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if request.method == 'POST':
        email    = request.form.get('email', '').lower().strip()
        password = request.form.get('password', '')

        # ── DB-backed lockout (clearing cookies cannot bypass this) ──
        attempt_record = LoginAttempt.get_or_create(email)
        if attempt_record.is_locked():
            mins = max(1, attempt_record.seconds_remaining() // 60 + 1)
            flash(
                f'Account temporarily locked due to too many failed attempts. '
                f'Please try again in {mins} minute(s).',
                'danger'
            )
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
            return render_template('login.html')

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            try:
                attempt_record.record_success()
                LoginAttempt.cleanup_old()
            except Exception:
                db.session.rollback()

            if user.status == 'Banned':
                flash('Your account has been suspended. Please contact support.', 'danger')
                return redirect(url_for('auth.login'))

            if user.two_fa_enabled:
                otp_code = str(secrets.randbelow(900000) + 100000)
                session['2fa_user_id']    = user.id
                session['2fa_otp']        = otp_code
                session['2fa_otp_expiry'] = time.time() + 300
                session['2fa_attempts']   = 0
                send_otp_email(user.email, user.name, otp_code)
                flash('A 6-digit verification code has been sent to your email.', 'info')
                return redirect(url_for('auth.verify_email_otp'))

            generate_and_store_session_token(user)
            login_user(user)
            log_action("Login", "Standard login")

            # FIX 8: Respect 'next' param with safety check (relative paths only)
            next_url = request.args.get('next', '')
            if next_url and next_url.startswith('/') and not next_url.startswith('//'):
                return redirect(next_url)
            return redirect(
                url_for('admin.admin_dashboard') if user.role == 'Admin' else url_for('main.home')
            )

        # ── Failed login ──────────────────────────────────────────
        try:
            attempt_record.record_failure(
                max_attempts    = _MAX_LOGIN_ATTEMPTS,
                lockout_seconds = _LOCKOUT_SECONDS,
            )
        except Exception:
            db.session.rollback()

        if attempt_record.is_locked():
            flash(
                f'Too many failed attempts. Your account has been locked for '
                f'{_LOCKOUT_SECONDS // 60} minutes. Please try again later.',
                'danger'
            )
        else:
            remaining = _MAX_LOGIN_ATTEMPTS - attempt_record.attempts
            flash(
                f'Invalid email or password. '
                f'{remaining} attempt(s) remaining before your account is temporarily locked.',
                'danger'
            )

    return render_template('login.html')


# ── Email OTP 2FA ─────────────────────────────────────────────────

@auth_bp.route('/verify-email-otp', methods=['GET', 'POST'])
def verify_email_otp():
    if '2fa_user_id' not in session or '2fa_otp' not in session:
        flash('Session expired. Please log in again.', 'warning')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        entered  = request.form.get('code', '').strip()
        attempts = session.get('2fa_attempts', 0)

        if attempts >= 5:
            for k in ('2fa_user_id', '2fa_otp', '2fa_otp_expiry', '2fa_attempts'):
                session.pop(k, None)
            flash('Too many incorrect attempts. Please log in again.', 'danger')
            return redirect(url_for('auth.login'))

        if time.time() > session.get('2fa_otp_expiry', 0):
            for k in ('2fa_user_id', '2fa_otp', '2fa_otp_expiry', '2fa_attempts'):
                session.pop(k, None)
            flash('Verification code expired. Please log in again.', 'warning')
            return redirect(url_for('auth.login'))

        if entered == session.get('2fa_otp'):
            user = User.query.get(session['2fa_user_id'])
            for k in ('2fa_user_id', '2fa_otp', '2fa_otp_expiry', '2fa_attempts'):
                session.pop(k, None)
            generate_and_store_session_token(user)
            login_user(user)
            log_action("Login", "Successful login via Email OTP 2FA")
            return redirect(
                url_for('admin.admin_dashboard') if user.role == 'Admin' else url_for('main.home')
            )
        else:
            session['2fa_attempts'] = attempts + 1
            remaining = 5 - session['2fa_attempts']
            flash(f'Incorrect code. {remaining} attempt(s) remaining.', 'danger')

    masked_email = ''
    uid = session.get('2fa_user_id')
    if uid:
        u = User.query.get(uid)
        if u:
            parts        = u.email.split('@')
            masked_email = parts[0][0] + '***@' + parts[1]

    return render_template('verify_email_otp.html', masked_email=masked_email)


@auth_bp.route('/verify-email-otp/resend', methods=['POST'])
def resend_otp():
    if '2fa_user_id' not in session:
        return redirect(url_for('auth.login'))
    user = User.query.get(session['2fa_user_id'])
    if not user:
        return redirect(url_for('auth.login'))
    otp_code = str(secrets.randbelow(900000) + 100000)
    session['2fa_otp']        = otp_code
    session['2fa_otp_expiry'] = time.time() + 300
    session['2fa_attempts']   = 0
    send_otp_email(user.email, user.name, otp_code)
    flash('A new verification code has been sent to your email.', 'info')
    return redirect(url_for('auth.verify_email_otp'))


# ── 2FA enable / disable ──────────────────────────────────────────

@auth_bp.route('/security/2fa/enable', methods=['POST'])
@login_required
def enable_2fa():
    current_user.two_fa_enabled = True
    db.session.commit()
    log_action("Enabled 2FA", "User enabled Email OTP Two-Factor Authentication")
    flash('Two-Factor Authentication enabled! You will receive a code by email on each login.', 'success')
    return redirect(url_for('main.security'))


@auth_bp.route('/security/2fa/disable', methods=['POST'])
@login_required
def disable_2fa():
    current_user.two_fa_enabled = False
    db.session.commit()
    log_action("Disabled 2FA", "User disabled Two-Factor Authentication")
    flash('Two-Factor Authentication has been disabled.', 'warning')
    return redirect(url_for('main.security'))


# ── Register (User) ───────────────────────────────────────────────

@auth_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit("5 per minute; 20 per hour", methods=["POST"])
def register():
    ref_code = request.args.get('ref', '')
    if request.method == 'POST':
        name           = request.form.get('name')
        email          = request.form.get('email', '').lower()
        password       = request.form.get('password')
        referral_input = request.form.get('referral_code', '').strip().upper()

        if User.query.filter_by(email=email).first():
            flash('An account with this email already exists.', 'danger')
            return redirect(url_for('auth.login'))

        # SECURITY: enforce minimum password strength
        if not password or len(password) < 8:
            flash('Password must be at least 8 characters.', 'danger')
            return render_template('register.html', ref_code=ref_code)
        if not any(c.isdigit() for c in password) and not any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in password):
            flash('Password must contain at least one number or special character.', 'danger')
            return render_template('register.html', ref_code=ref_code)

        hashed_pw = generate_password_hash(password, method='pbkdf2:sha256')
        new_code  = generate_referral_code()
        while User.query.filter_by(referral_code=new_code).first():
            new_code = generate_referral_code()

        referrer = (
            User.query.filter_by(referral_code=referral_input).first()
            if referral_input else None
        )

        new_user = User(
            name          = name,
            email         = email,
            password      = hashed_pw,
            role          = 'User',
            referral_code = new_code,
            referred_by   = referrer.id if referrer else None,
            loyalty_points= 100 if referrer else 0,
        )
        db.session.add(new_user)
        db.session.flush()

        if referrer:
            referrer.loyalty_points = (referrer.loyalty_points or 0) + 200
            send_referral_bonus_email(referrer, new_user)

        db.session.commit()

        # SECURITY: require email verification before full access
        otp_code = str(secrets.randbelow(900000) + 100000)
        session['verify_user_id']    = new_user.id
        session['verify_otp']        = otp_code
        session['verify_otp_expiry'] = time.time() + 600   # 10 min
        session['verify_attempts']   = 0
        send_otp_email(new_user.email, new_user.name, otp_code)
        log_action("Register", "New user account created — pending email verification")
        flash('Account created! Please check your email for a 6-digit verification code.', 'info')
        return redirect(url_for('auth.verify_registration_email'))

    return render_template('register.html', ref_code=ref_code)


# ── Email verification after registration ─────────────────────────

@auth_bp.route('/verify-email', methods=['GET', 'POST'])
@limiter.limit("10 per minute", methods=["POST"])
def verify_registration_email():
    """Verify a newly registered user's email with OTP before granting access."""
    if 'verify_user_id' not in session:
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        entered  = request.form.get('code', '').strip()
        attempts = session.get('verify_attempts', 0)

        if attempts >= 5:
            for k in ('verify_user_id', 'verify_otp', 'verify_otp_expiry', 'verify_attempts'):
                session.pop(k, None)
            flash('Too many incorrect attempts. Please register again.', 'danger')
            return redirect(url_for('auth.register'))

        if time.time() > session.get('verify_otp_expiry', 0):
            for k in ('verify_user_id', 'verify_otp', 'verify_otp_expiry', 'verify_attempts'):
                session.pop(k, None)
            flash('Verification code expired. Please register again.', 'warning')
            return redirect(url_for('auth.register'))

        if entered == session.get('verify_otp'):
            user = User.query.get(session['verify_user_id'])
            if user:
                user.email_verified = True
                db.session.commit()
            for k in ('verify_user_id', 'verify_otp', 'verify_otp_expiry', 'verify_attempts'):
                session.pop(k, None)
            generate_and_store_session_token(user)
            login_user(user)
            log_action("Email Verified", "User verified email after registration")
            flash('Email verified! Welcome to DriveX 🎉', 'success')
            return redirect(url_for('main.home'))
        else:
            session['verify_attempts'] = attempts + 1
            remaining = 5 - session['verify_attempts']
            flash(f'Incorrect code. {remaining} attempt(s) remaining.', 'danger')

    uid = session.get('verify_user_id')
    masked = ''
    if uid:
        u = User.query.get(uid)
        if u:
            parts  = u.email.split('@')
            masked = parts[0][0] + '***@' + parts[1]

    return render_template('verify_email_otp.html', masked_email=masked,
                           resend_url=url_for('auth.resend_registration_otp'),
                           page_title='Verify Your Email')


@auth_bp.route('/verify-email/resend', methods=['POST'])
@limiter.limit("3 per minute", methods=["POST"])
def resend_registration_otp():
    if 'verify_user_id' not in session:
        return redirect(url_for('auth.login'))
    user = User.query.get(session['verify_user_id'])
    if not user:
        return redirect(url_for('auth.login'))
    otp_code = str(secrets.randbelow(900000) + 100000)
    session['verify_otp']        = otp_code
    session['verify_otp_expiry'] = time.time() + 600
    session['verify_attempts']   = 0
    send_otp_email(user.email, user.name, otp_code)
    flash('A new code has been sent to your email.', 'info')
    return redirect(url_for('auth.verify_registration_email'))


# ── Register (Client / Partner) ───────────────────────────────────

@auth_bp.route('/register/client', methods=['GET', 'POST'])
@limiter.limit("5 per minute; 20 per hour", methods=["POST"])
def register_client():
    if request.method == 'POST':
        email    = request.form.get('email', '').lower()
        password = request.form.get('password', '')

        if User.query.filter_by(email=email).first():
            flash('An account with this email already exists.', 'danger')
            return redirect(url_for('auth.login'))

        # SECURITY FIX: enforce password strength for client accounts
        if not password or len(password) < 8:
            flash('Password must be at least 8 characters.', 'danger')
            return render_template('register_client.html')
        if not any(c.isdigit() for c in password) and not any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in password):
            flash('Password must contain at least one number or special character.', 'danger')
            return render_template('register_client.html')

        new_code = generate_referral_code()
        while User.query.filter_by(referral_code=new_code).first():
            new_code = generate_referral_code()
        hashed_pw = generate_password_hash(password, method='pbkdf2:sha256')
        new_user  = User(
            name          = request.form.get('name'),
            email         = email,
            password      = hashed_pw,
            role          = 'Client',
            referral_code = new_code,
        )
        db.session.add(new_user)
        db.session.commit()

        # SECURITY: require email verification before full access
        otp_code = str(secrets.randbelow(900000) + 100000)
        session['verify_user_id']    = new_user.id
        session['verify_otp']        = otp_code
        session['verify_otp_expiry'] = time.time() + 600
        session['verify_attempts']   = 0
        send_otp_email(new_user.email, new_user.name, otp_code)
        log_action("Register", "New Client account created — pending email verification")
        flash('Account created! Please verify your email.', 'info')
        return redirect(url_for('auth.verify_registration_email'))
    return render_template('register_client.html')


# ── Forgot / Reset Password ───────────────────────────────────────

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
@limiter.limit("3 per minute; 10 per hour", methods=["POST"])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user  = User.query.filter_by(email=email).first()
        flash('If an account exists for that email, a reset link has been sent.')
        if user:
            s     = _get_serializer()
            token = s.dumps(email, salt='reset-password')
            link  = url_for('auth.reset_password', token=token, _external=True)
            send_password_reset_email(user, link)
        return redirect(url_for('auth.login'))
    return render_template('forgot_password.html')


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    s = _get_serializer()
    try:
        email = s.loads(token, salt='reset-password', max_age=3600)
    except Exception:
        flash('The reset link is invalid or has expired.')
        return redirect(url_for('auth.forgot_password'))

    user = User.query.filter_by(email=email).first()
    if not user:
        flash('Account not found.')
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm  = request.form.get('confirm_password', '')
        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'danger')
            return render_template('reset_password.html', token=token)
        if password != confirm:
            flash('Passwords do not match.')
            return render_template('reset_password.html', token=token)
        user.password      = generate_password_hash(password, method='pbkdf2:sha256')
        user.session_token = str(uuid.uuid4())
        db.session.commit()
        flash('Password updated! Please log in.')
        return redirect(url_for('auth.login'))

    return render_template('reset_password.html', token=token)


# ── Logout ────────────────────────────────────────────────────────

@auth_bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('main.home'))
