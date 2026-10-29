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


class FlagShare(db.Model):
    """The same unique flag submitted by two accounts on one challenge."""

    __tablename__ = "warden_flag_shares"

    id = db.Column(db.Integer, primary_key=True)
    challenge_id = db.Column(
        db.Integer, db.ForeignKey("challenges.id", ondelete="CASCADE"), nullable=True
    )
    flag = db.Column(db.String(255), nullable=False)
    # The account that submitted this flag correctly first ...
    owner_team_id = db.Column(
        db.Integer, db.ForeignKey("teams.id", ondelete="SET NULL"), nullable=True
    )
    owner_user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    owner_date = db.Column(db.DateTime, nullable=True)
    # ... and the other account that submitted the same string.
    team_id = db.Column(
        db.Integer, db.ForeignKey("teams.id", ondelete="SET NULL"), nullable=True
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status = db.Column(db.String(16))  # what CTFd answered: "correct", "incorrect", ...
    ip = db.Column(db.String(46))
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
