"""Flag brute-force lockout: too many wrong flags on one challenge locks the account out of it.

This sits on top of CTFd's own per-IP limit. The account is the team in teams mode and the user in
users mode, so switching IPs or team members does not reset it. Counters are atomic with Redis;
with CTFd's filesystem cache they still work but several workers can each miss a few attempts.
"""

import logging
import time

from flask import g, jsonify, request

from CTFd.cache import cache
from CTFd.models import db
from CTFd.utils.user import get_ip

from .common import account_key
from .models import LockoutEvent
from .settings import lock_settings

ATTEMPT_PATH = "/api/v1/challenges/attempt"
log = logging.getLogger("warden")


def _redis():
    try:
        return cache.cache._write_client, cache.cache.key_prefix
    except AttributeError:
        return None, ""


def warn_without_redis():
    if _redis()[0] is None:
        log.warning(
            "warden: CTFd is not using Redis, flag lockout counters are per worker and not atomic"
        )


def _challenge_id():
    body = request.get_json(silent=True) or request.form
    try:
        return int(body.get("challenge_id"))
    except (TypeError, ValueError, AttributeError):
        return None


def before_request(path, user):
    if path != ATTEMPT_PATH or request.method != "POST":
        return None
    account, challenge_id = account_key(user), _challenge_id()
    if account is None or challenge_id is None:
        return None
    until = cache.get(f"warden:lock:{account}:{challenge_id}")
    if until and until > time.time():
        minutes = int((until - time.time()) // 60) + 1
        return (
            jsonify(
                {
                    "success": True,
                    "data": {
                        "status": "ratelimited",
                        "message": "Too many incorrect attempts on this challenge. "
                        f"Try again in {minutes} min.",
                    },
                }
            ),
            429,
        )
    g.warden_lockout = (account, challenge_id, user.id, user.team_id)
    return None


def after_request(response):
    info = g.pop("warden_lockout", None)
    if not info or response.status_code != 200:
        return
    data = response.get_json(silent=True)
    if not isinstance(data, dict) or (data.get("data") or {}).get("status") != "incorrect":
        return
    account, challenge_id, user_id, team_id = info
    settings = lock_settings()
    key = f"warden:wrong:{account}:{challenge_id}"
    client, prefix = _redis()
    if client is not None:
        count = client.incr(prefix + key)
        if count == 1:
            client.expire(prefix + key, settings["window"])
    else:
        count = (cache.get(key) or 0) + 1
        cache.set(key, count, timeout=settings["window"])
    if count < settings["threshold"]:
        return
    cache.set(
        f"warden:lock:{account}:{challenge_id}",
        time.time() + settings["duration"],
        timeout=settings["duration"],
    )
    if client is not None:
        client.delete(prefix + key)
    else:
        cache.delete(key)
    try:
        db.session.add(
            LockoutEvent(
                team_id=team_id,
                user_id=user_id,
                challenge_id=challenge_id,
                ip=get_ip(),
                attempts=count,
            )
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
