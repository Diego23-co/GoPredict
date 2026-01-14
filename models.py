from datetime import datetime
from extensions import db  # <- import db from extensions
from flask_login import UserMixin


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(120), unique=True)
    phone = db.Column(db.String(20), unique=True)
    verified = db.Column(db.Boolean, default=False)
    active = db.Column(db.Boolean, default=True)

    # Flask-Login uses this property
    @property
    def is_active(self):
        return self.active

class Match(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    api_id = db.Column(db.Integer, unique=True, nullable=False)
    home = db.Column(db.String(120), nullable=False)
    away = db.Column(db.String(120), nullable=False)
    utc_date = db.Column(db.String(50), nullable=False)
    local_date = db.Column(db.String(50))

    home_score = db.Column(db.Integer, nullable=True)
    away_score = db.Column(db.Integer, nullable=True)

    status = db.Column(db.String(30), default="SCHEDULED")
    league_name = db.Column(db.String(100))

    home_logo = db.Column(db.String(255))
    away_logo = db.Column(db.String(255))




class Prediction(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    match_id = db.Column(db.Integer, db.ForeignKey("match.id"), nullable=False)

    pred_home = db.Column(db.Integer, nullable=False)
    pred_away = db.Column(db.Integer, nullable=False)

    points = db.Column(db.Integer, default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref="predictions")
    match = db.relationship("Match", backref="predictions")

