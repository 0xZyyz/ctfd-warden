import json
import re
from datetime import datetime
from statistics import median

from flask import g, request
from sqlalchemy.exc import IntegrityError

from CTFd.cache import cache
from CTFd.models import Solves, Users, db
from CTFd.utils import get_config, set_config

from .common import account_key, teams_mode
from .models import ChallengeView

CHALLENGE_DETAIL = re.compile(r"^/api/v1/challenges/(\d+)/?$")
SECONDS_KEY = "warden_fast_solve_seconds"
IGNORED_KEY = "warden_fast_solve_ignored"
SINCE_KEY = "warden_fast_solve_since"
DEFAULT_SECONDS = 60
MIN_SECONDS = 5
MAX_SECONDS = 86400


def threshold():
    try:
        value = int(get_config(SECONDS_KEY) or DEFAULT_SECONDS)
    except (TypeError, ValueError):
        value = DEFAULT_SECONDS
    return min(MAX_SECONDS, max(MIN_SECONDS, value))


def save_threshold(seconds):
    set_config(SECONDS_KEY, str(int(seconds)))


def ignored():
    try:
        data = json.loads(get_config(IGNORED_KEY) or "[]")
    except (TypeError, ValueError):
        return set()
    return {int(c) for c in data if str(c).isdigit()} if isinstance(data, list) else set()


def save_ignored(challenge_ids):
    set_config(IGNORED_KEY, json.dumps(sorted({int(c) for c in challenge_ids})))


def since():
    value = get_config(SINCE_KEY)
    try:
        return datetime.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        return None


def start_tracking(reset=False):
    if reset or since() is None:
        set_config(SINCE_KEY, datetime.utcnow().isoformat(timespec="seconds"))


def before_request(path, user):
    if request.method != "GET":
        return
    match = CHALLENGE_DETAIL.match(path)
    account = account_key(user)
    if match and account:
        g.warden_view = (account, int(match.group(1)), user.id, user.team_id)


def after_request(response):
    info = g.pop("warden_view", None)
    if not info or response.status_code != 200:
        return
    account, challenge_id, user_id, team_id = info
    key = f"warden:viewed:{account}:{challenge_id}"
    if cache.get(key):
        return
    if ChallengeView.query.filter_by(account=account, challenge_id=challenge_id).first() is None:
        db.session.add(
            ChallengeView(
                account=account, challenge_id=challenge_id, user_id=user_id, team_id=team_id
            )
        )
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
    cache.set(key, 1, timeout=86400)


def _account(solve):
    return f"t{solve.team_id}" if teams_mode() else f"u{solve.user_id}"


def rows():
    limit, skip, start = threshold(), ignored(), since()
    opened = {
        (account, challenge_id): date
        for account, challenge_id, date in db.session.query(
            ChallengeView.account, ChallengeView.challenge_id, ChallengeView.date
        )
    }
    durations, found = {}, []
    solves = (
        Solves.query.join(Users, Users.id == Solves.user_id)
        .filter(Users.type != "admin")
        .order_by(Solves.date.desc(), Solves.id.desc())
    )
    for solve in solves:
        if solve.challenge_id in skip:
            continue
        first = opened.get((_account(solve), solve.challenge_id))
        if first is None:
            if start is not None and solve.date >= start:
                found.append({"solve": solve, "opened": None, "seconds": None})
            continue
        seconds = max(0, int((solve.date - first).total_seconds()))
        durations.setdefault(solve.challenge_id, []).append(seconds)
        if seconds < limit:
            found.append({"solve": solve, "opened": first, "seconds": seconds})
    for row in found:
        times = durations.get(row["solve"].challenge_id)
        row["median"] = int(median(times)) if times else None
    return found
