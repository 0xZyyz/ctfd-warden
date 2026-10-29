"""Per-account challenge blocks: bar one team (or user) from one challenge, e.g. after revoking a
solve for flag sharing. A blocked account no longer sees the challenge and cannot submit to it."""

import json
import re

from flask import jsonify, request

from CTFd.utils import get_config, set_config

from .common import account_key

BLOCKS_KEY = "warden_challenge_blocks"
ATTEMPT_PATH = "/api/v1/challenges/attempt"
CHALLENGE_DETAIL = re.compile(r"^/api/v1/challenges/(\d+)(?:/.*)?$")


def load_blocks():
    """{challenge_id (int): {account_key, ...}}"""
    try:
        data = json.loads(get_config(BLOCKS_KEY) or "{}")
    except (TypeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    out = {}
    for challenge_id, accounts in data.items():
        if str(challenge_id).isdigit() and isinstance(accounts, list):
            out[int(challenge_id)] = {str(a) for a in accounts}
    return out


def save_blocks(blocks):
    data = {str(c): sorted(a) for c, a in blocks.items() if a}
    set_config(BLOCKS_KEY, json.dumps(data, sort_keys=True))


def add_block(challenge_id, account):
    blocks = load_blocks()
    blocks.setdefault(int(challenge_id), set()).add(account)
    save_blocks(blocks)


def remove_block(challenge_id, account):
    blocks = load_blocks()
    blocks.get(int(challenge_id), set()).discard(account)
    save_blocks(blocks)


def blocked_for(user):
    account = account_key(user)
    if account is None:
        return set()
    return {c for c, accounts in load_blocks().items() if account in accounts}


def before_request(path, user):
    blocked = blocked_for(user)
    if not blocked:
        return None
    if path == ATTEMPT_PATH and request.method == "POST":
        body = request.get_json(silent=True) or request.form
        try:
            challenge_id = int(body.get("challenge_id"))
        except (TypeError, ValueError, AttributeError):
            return None
        if challenge_id in blocked:
            return (
                jsonify(
                    {
                        "success": True,
                        "data": {
                            "status": "disabled",
                            "message": "This challenge is disabled for your account.",
                        },
                    }
                ),
                403,
            )
        return None
    match = CHALLENGE_DETAIL.match(path)
    if match and int(match.group(1)) in blocked:
        return jsonify({"success": False, "errors": ["Not found."]}), 404
    return None


def after_request(path, user, response):
    """Drop blocked challenges from the challenge list a blocked account receives."""
    if request.method != "GET" or path.rstrip("/") != "/api/v1/challenges":
        return
    if response.status_code != 200:
        return
    blocked = blocked_for(user)
    if not blocked:
        return
    data = response.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        return
    data["data"] = [
        c for c in data["data"] if not (isinstance(c, dict) and c.get("id") in blocked)
    ]
    response.set_data(json.dumps(data))
