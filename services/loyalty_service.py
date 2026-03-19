from config import Config
from extensions import db


def get_loyalty_tier(total_spent):
    """Return the loyalty tier name for a given total spend."""
    tier = 'Bronze'
    for name, cfg in Config.LOYALTY_TIERS.items():
        if total_spent >= cfg['min']:
            tier = name
    return tier


def award_loyalty_points(user, booking):
    """
    Calculate and award loyalty points to the user for a completed booking.
    Returns the number of points earned.
    """
    tier_config   = Config.LOYALTY_TIERS[get_loyalty_tier(user.total_spent)]
    earned        = int(int(booking.total_cost / 100) * tier_config['points_rate'])
    user.loyalty_points   = (user.loyalty_points or 0) + earned
    booking.points_earned = earned
    db.session.commit()
    return earned


def redeem_loyalty_points(user, total_before_redemption):
    """
    Calculate the maximum discount achievable by redeeming the user's points.
    Returns (points_discount_amount, points_to_deduct).
    100 points = ₹50 off.
    """
    if user.loyalty_points < 100:
        return 0, 0
    max_points_usable = min(
        user.loyalty_points,
        int(total_before_redemption / 50) * 100
    )
    points_discount  = int(max_points_usable / 100) * 50
    points_to_deduct = int(points_discount / 50) * 100
    return points_discount, points_to_deduct


def apply_referral_bonus(referrer, new_user):
    """
    Award referral points: 200 to referrer, 100 to new user.
    Caller is responsible for db.session.commit().
    """
    referrer.loyalty_points = (referrer.loyalty_points or 0) + 200
    new_user.loyalty_points = (new_user.loyalty_points or 0) + 100
