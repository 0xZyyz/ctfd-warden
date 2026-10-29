"""Flag sharing: on challenges whose flags are unique per team or per session (an instancer, or a
remote service that prints a random suffix accepted by a regex flag), the same flag string coming
from two accounts means it was passed between them.

Admins pick the challenges to watch; nothing else is checked, because a normal static flag is the
same string for everyone. Detection reads CTFd's own submissions table, so a scan can also run over
everything submitted before the challenge was watched.
"""

import json

from flask import g, request

from CTFd.models import Submissions, db
from CTFd.utils import get_config, set_config
from CTFd.utils.user import get_ip

from .common import teams_mode
from .models import FlagShare

WATCH_KEY = "warden_shared_flag_challenges"
ATTEMPT_PATH = "/api/v1/challenges/attempt"
# Answers after which CTFd has stored (or already holds) the submission; ratelimited and paused
# attempts are not recorded, so they cannot be compared.
CHECKED_STATUSES = ("correct", "incorrect", "already_solved")


def watched():
    try:
        data = json.loads(get_config(WATCH_KEY) or "[]")
    except (TypeError, ValueError):
        return set()
    return {int(c) for c in data if str(c).isdigit()} if isinstance(data, list) else set()


def save_watched(challenge_ids):
    set_config(WATCH_KEY, json.dumps(sorted({int(c) for c in challenge_ids})))


def _other_accounts(query, team_id, user_id):
    if teams_mode():
        return query.filter(db.or_(Submissions.team_id != team_id, Submissions.team_id.is_(None)))
    return query.filter(Submissions.user_id != user_id)


def _first_correct(challenge_id, flag, team_id, user_id):
    """The earliest correct submission of this exact flag by another account."""
    query = Submissions.query.filter(
        Submissions.challenge_id == challenge_id,
        Submissions.provided == flag,
        Submissions.type == "correct",
    )
    return (
        _other_accounts(query, team_id, user_id)
        .order_by(Submissions.date.asc(), Submissions.id.asc())
        .first()
    )


def _record(challenge_id, flag, owner, team_id, user_id, status, ip, date=None):
    """Store one event per (challenge, owner account, other account). Returns True when new."""
    same = FlagShare.query.filter_by(challenge_id=challenge_id)
    if teams_mode():
        same = same.filter_by(owner_team_id=owner.team_id, team_id=team_id)
    else:
        same = same.filter_by(owner_user_id=owner.user_id, user_id=user_id)
    if same.first() is not None:
        return False
    event = FlagShare(
        challenge_id=challenge_id,
        flag=flag[:255],
        owner_team_id=owner.team_id,
        owner_user_id=owner.user_id,
        owner_date=owner.date,
        team_id=team_id,
        user_id=user_id,
        status=status,
        ip=ip,
    )
    if date is not None:
        event.date = date
    db.session.add(event)
    return True


def before_request(path, user):
    if path != ATTEMPT_PATH or request.method != "POST":
        return
    body = request.get_json(silent=True) or request.form
    try:
        challenge_id = int(body.get("challenge_id"))
    except (TypeError, ValueError, AttributeError):
        return
    if challenge_id not in watched():
        return
    # CTFd strips the submission the same way before storing it.
    flag = str(body.get("submission") or "").strip()
    if flag:
        g.warden_share = (challenge_id, flag, user.id, user.team_id)


def after_request(response):
    info = g.pop("warden_share", None)
    if not info or response.status_code != 200:
        return
    data = response.get_json(silent=True)
    status = ((data or {}).get("data") or {}).get("status") if isinstance(data, dict) else None
    if status not in CHECKED_STATUSES:
        return
    challenge_id, flag, user_id, team_id = info
    owner = _first_correct(challenge_id, flag, team_id, user_id)
    if owner is None:
        return
    try:
        if _record(challenge_id, flag, owner, team_id, user_id, status, get_ip()):
            db.session.commit()
    except Exception:
        db.session.rollback()


def scan():
    """Check every past submission on the watched challenges. Returns the number of new events."""
    created = 0
    for challenge_id in sorted(watched()):
        rows = (
            Submissions.query.filter(
                Submissions.challenge_id == challenge_id,
                Submissions.type.in_(("correct", "incorrect")),
            )
            .order_by(Submissions.date.asc(), Submissions.id.asc())
            .all()
        )
        by_flag = {}
        for row in rows:
            by_flag.setdefault((row.provided or "").strip(), []).append(row)
        for flag, submissions in by_flag.items():
            owner = next((s for s in submissions if s.type == "correct"), None)
            if not flag or owner is None:
                continue
            owner_account = owner.team_id if teams_mode() else owner.user_id
            for s in submissions:
                account = s.team_id if teams_mode() else s.user_id
                if account == owner_account:
                    continue
                if _record(challenge_id, flag, owner, s.team_id, s.user_id, s.type, s.ip, s.date):
                    created += 1
    db.session.commit()
    return created
