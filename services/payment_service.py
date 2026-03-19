import razorpay
from flask import current_app


def _get_client():
    """Return an authenticated Razorpay client."""
    key_id     = current_app.config.get('RAZORPAY_KEY_ID', '')
    key_secret = current_app.config.get('RAZORPAY_KEY_SECRET', '')
    return razorpay.Client(auth=(key_id, key_secret))


def create_razorpay_order(amount_inr):
    """
    Create a Razorpay order.
    amount_inr  — total in Indian Rupees (integer).
    Returns the full Razorpay order dict (contains 'id', 'amount', 'currency', …).
    """
    client = _get_client()
    order  = client.order.create({
        'amount':   int(amount_inr) * 100,   # Razorpay expects paise
        'currency': 'INR',
        'payment_capture': 1,                 # auto-capture on success
    })
    return order


def verify_razorpay_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature):
    """
    Verify the Razorpay webhook/callback signature.
    Returns True if valid, False otherwise.
    """
    client = _get_client()
    try:
        client.utility.verify_payment_signature({
            'razorpay_order_id':   razorpay_order_id,
            'razorpay_payment_id': razorpay_payment_id,
            'razorpay_signature':  razorpay_signature,
        })
        return True
    except razorpay.errors.SignatureVerificationError:
        return False
