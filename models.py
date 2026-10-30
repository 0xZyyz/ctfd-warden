from datetime import datetime

from CTFd.models import db


class ClientEvent(db.Model):
    __tablename__ = "warden_client_events"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    team_id = db.Column(
        db.Integer, db.ForeignKey("teams.id", ondelete="SET NULL"), nullable=True
    )
    kind = db.Column(db.String(16), nullable=False)
    label = db.Column(db.String(64), nullable=False)
    ip = db.Column(db.String(46))
    user_agent = db.Column(db.String(255))
    referer = db.Column(db.String(255))
    method = db.Column(db.String(8))
    path = db.Column(db.String(255))
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class DeviceSession(db.Model):
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
    __tablename__ = "warden_flag_shares"

    id = db.Column(db.Integer, primary_key=True)
    challenge_id = db.Column(
        db.Integer, db.ForeignKey("challenges.id", ondelete="CASCADE"), nullable=True
    )
    flag = db.Column(db.String(255), nullable=False)
    owner_team_id = db.Column(
        db.Integer, db.ForeignKey("teams.id", ondelete="SET NULL"), nullable=True
    )
    owner_user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    owner_date = db.Column(db.DateTime, nullable=True)
    team_id = db.Column(
        db.Integer, db.ForeignKey("teams.id", ondelete="SET NULL"), nullable=True
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status = db.Column(db.String(16))
    ip = db.Column(db.String(46))
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)



class HoneypotHit(db.Model):
    __tablename__ = "warden_honeypot_hits"

    id = db.Column(db.Integer, primary_key=True)
    challenge_id = db.Column(
        db.Integer, db.ForeignKey("challenges.id", ondelete="CASCADE"), nullable=True
    )
    team_id = db.Column(
        db.Integer, db.ForeignKey("teams.id", ondelete="SET NULL"), nullable=True
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    flag = db.Column(db.String(255), nullable=False)
    ip = db.Column(db.String(46))
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
