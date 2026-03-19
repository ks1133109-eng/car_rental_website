from extensions import db


class Car(db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    owner_id      = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    name          = db.Column(db.String(100), nullable=False)
    category      = db.Column(db.String(50))
    price_per_day = db.Column(db.Integer, nullable=False)
    image_url     = db.Column(db.String(500), nullable=False)
    transmission  = db.Column(db.String(20))
    fuel_type     = db.Column(db.String(20))
    seats         = db.Column(db.Integer)
    location      = db.Column(db.String(100))
    status        = db.Column(db.String(20), default='Available')
    reviews       = db.relationship('Review', backref='car', lazy=True)

    @property
    def average_rating(self):
        if not self.reviews:
            return 5.0
        return round(sum(r.rating for r in self.reviews) / len(self.reviews), 1)
