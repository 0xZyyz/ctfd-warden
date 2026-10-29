from datetime import datetime

from CTFd.models import db


class ClientEvent(db.Model):
    """A logged-in request from a self-identified AI agent, an automation library or an API token."""

    __tablename__ = "warden_client_events"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    team_id = db.Column(
        db.Integer, db.ForeignKey("teams.id", ondelete="SET NULL"), nullable=True
    )
    kind = db.Column(db.String(16), nullable=False)  # "ai", "api-token" or "automation"
    label = db.Column(db.String(64), nullable=False)
    ip = db.Column(db.String(46))
    user_agent = db.Column(db.String(255))
    referer = db.Column(db.String(255))
    method = db.Column(db.String(8))
    path = db.Column(db.String(255))
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class DeviceSession(db.Model):
    """One browser (device ID cookie) seen logged in as one account."""

    __tablename__ = "warden_device_sessions"

    device_id = db.Column(db.String(64), primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    user_agent = db.Column(db.String(255))
    ip = db.Column(db.String(46))
    first_seen = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_seen = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class LockoutEvent(db.Model):
    """An account locked out of a challenge after too many wrong flags."""

    __tablename__ = "warden_lockout_events"

    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(
        db.Integer, db.ForeignKey("teams.id", ondelete="SET NULL"), nullable=True
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    challenge_id = db.Column(db.Integer, nullable=True)
    ip = db.Column(db.String(46))
    attempts = db.Column(db.Integer, nullable=False)
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
