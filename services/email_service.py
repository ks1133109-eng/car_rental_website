import os
import resend


def _get_resend_key():
    return os.environ.get('RESEND_API_KEY', '')


def send_email(subject, recipient, body_text):
    """Generic email sender via Resend. Falls back to console in dev."""
    api_key = _get_resend_key()
    if not api_key:
        print(f">> [DEV] Email → {recipient} | {subject}\n{body_text}\n")
        return
    try:
        resend.api_key = api_key
        resend.Emails.send({
            "from":    "DriveX <support@drivex.qzz.io>",
            "to":      [recipient],
            "subject": subject,
            "text":    body_text,
        })
        print(f">> Email sent → {recipient}")
    except Exception as e:
        print(f">> Email error: {e}")


def send_otp_email(user_email, user_name, otp_code):
    body = (
        f"Hello {user_name},\n\n"
        f"Your DriveX login verification code is:\n\n"
        f"    {otp_code}\n\n"
        f"This code expires in 5 minutes. Do NOT share it with anyone.\n\n"
        f"If you did not attempt to log in, change your password immediately.\n\n"
        f"DriveX Security Team"
    )
    send_email("DriveX Login Verification Code", user_email, body)


def send_booking_confirmation_email(booking):
    duration = (booking.end_date - booking.start_date).days or 1
    body = (
        f"Hello {booking.user.name},\n\nBooking CONFIRMED!\n\n"
        f"Booking ID : #{booking.id}\n"
        f"Vehicle    : {booking.car.name}\n"
        f"Pick-up    : {booking.start_date.strftime('%b %d, %Y %I:%M %p')}\n"
        f"Return     : {booking.end_date.strftime('%b %d, %Y %I:%M %p')}\n"
        f"Duration   : {duration} day(s)\n"
        f"Amount Paid: Rs.{booking.total_cost}\n\n"
        f"Thank you for choosing DriveX!\nsupport@drivex.qzz.io"
    )
    send_email(f"Booking Confirmed - DriveX #{booking.id}", booking.user.email, body)


def send_booking_cancellation_email(booking):
    body = (
        f"Hello {booking.user.name},\n\n"
        f"Your booking #{booking.id} for {booking.car.name} has been cancelled.\n\n"
        f"DriveX Team"
    )
    send_email(f"Booking Cancelled - DriveX #{booking.id}", booking.user.email, body)


def send_kyc_status_email(user, status):
    if status == 'Verified':
        send_email(
            "KYC Verified!", user.email,
            f"Hello {user.name},\n\nYour KYC has been APPROVED!\n"
            f"Book at https://drivex.qzz.io/fleet\n\nDriveX Team"
        )
    else:
        send_email(
            "KYC Failed", user.email,
            f"Hello {user.name},\n\nYour KYC could not be verified. "
            f"Re-submit at https://drivex.qzz.io/kyc\n\nDriveX Team"
        )


def send_referral_bonus_email(referrer, new_user):
    body = (
        f"Hello {referrer.name},\n\n"
        f"{new_user.name} joined using your referral code! "
        f"You earned 200 points.\n"
        f"Current points: {referrer.loyalty_points}\n\n"
        f"DriveX Team"
    )
    send_email("You earned a referral bonus!", referrer.email, body)


def send_password_reset_email(user, reset_link):
    body = (
        f"Hi {user.name},\n\n"
        f"Reset your password (valid 1 hour):\n{reset_link}\n\n"
        f"DriveX Team"
    )
    send_email('Password Reset - DriveX', user.email, body)
