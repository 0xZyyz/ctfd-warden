import json

from flask import request

from CTFd.models import Challenges, db
from CTFd.utils import get_config, set_config
from CTFd.utils.user import get_ip

from .models import HoneypotHit

KEY = "warden_honeypot_flags"
ATTEMPT_PATH = "/api/v1/challenges/attempt"


def load():
    try:
        data = json.loads(get_config(KEY) or "[]")
    except (TypeError, ValueError):
        return []
    out = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("flag"), str) or not item["flag"]:
            continue
        challenge_id = item.get("challenge_id")
        out.append(
            {
                "id": int(item.get("id") or 0),
                "flag": item["flag"],
                "challenge_id": challenge_id if isinstance(challenge_id, int) else None,
                "note": str(item.get("note") or ""),
            }
        )
    return out


def save(items):
    set_config(KEY, json.dumps(items))


def add(flag, challenge_id=None, note=""):
    flag = (flag or "").strip()[:255]
    items = load()
    if not flag or any(i["flag"] == flag and i["challenge_id"] == challenge_id for i in items):
        return False
    items.append(
        {
            "id": max((i["id"] for i in items), default=0) + 1,
            "flag": flag,
            "challenge_id": challenge_id,
            "note": (note or "").strip()[:200],
        }
    )
    save(items)
    return True


def remove(honeypot_id):
    save([i for i in load() if i["id"] != honeypot_id])


def match(flag, challenge_id):
    for item in load():
        if item["flag"] == flag and item["challenge_id"] in (None, challenge_id):
            return item
    return None


def before_request(path, user):
    if path != ATTEMPT_PATH or request.method != "POST":
        return
    body = request.get_json(silent=True) or request.form
    try:
        challenge_id = int(body.get("challenge_id"))
    except (TypeError, ValueError, AttributeError):
        return
    flag = str(body.get("submission") or "").strip()
    if not flag or match(flag, challenge_id) is None:
        return
    if Challenges.query.filter_by(id=challenge_id).first() is None:
        challenge_id = None
    try:
        db.session.add(
            HoneypotHit(
                challenge_id=challenge_id,
                team_id=user.team_id,
                user_id=user.id,
                flag=flag[:255],
                ip=get_ip(),
            )
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
