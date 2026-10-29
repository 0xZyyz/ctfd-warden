"""Client activity: requests from self-identified AI agents, automation libraries and API tokens.

These are hints, not proof: headers can be changed, and scripts and API tokens are normal CTF tools.
Similar requests are sampled once per user and client every ten minutes.
"""

import hashlib

from flask import jsonify, request

from CTFd.cache import cache
from CTFd.models import db
from CTFd.utils.user import authed, get_current_user, get_ip, is_admin

from . import settings
from .common import blueprint, request_path
from .detection import classify_client
from .models import ClientEvent

SAMPLE_WINDOW = 600
IGNORED_PREFIXES = ("/themes/", "/files/", "/static/", "/plugins/warden/assets/")


def _header(name, size=255):
    return (request.headers.get(name) or "")[:size] or None


def _record(user, kind, label, method=None, path=None):
    try:
        db.session.add(
            ClientEvent(
                user_id=user.id,
                team_id=user.team_id,
                kind=kind,
                label=label[:64],
                ip=get_ip(),
                user_agent=_header("User-Agent"),
                referer=_header("Referer"),
                method=method or request.method,
                path=(path or request_path())[:255],
            )
        )
        db.session.commit()
    except Exception:
        db.session.rollback()


def before_request(path, user):
    if request.endpoint == "views.files" or path.startswith(IGNORED_PREFIXES):
        return
    found = classify_client()
    if not found:
        return
    kind, label = found
    ua = request.headers.get("User-Agent") or ""
    key = f"warden:client:{user.id}:{kind}:{hashlib.sha256(ua.encode()).hexdigest()[:12]}"
    if cache.add(key, 1, timeout=SAMPLE_WINDOW):
        _record(user, kind, label)


def after_request(response):
    """A player creating a CTFd access token is logged even before the token is ever used."""
    if (
        request.method != "POST"
        or request_path().rstrip("/") != "/api/v1/tokens"
        or response.status_code != 200
        or not authed()
        or is_admin()
    ):
        return
    user = get_current_user()
    if user is None:
        return
    data = (response.get_json(silent=True) or {}).get("data") or {}
    note = (data.get("description") or "").strip()
    _record(
        user,
        "api-token",
        "API token created" + (f": {note}" if note else ""),
        method="POST",
        path="/api/v1/tokens",
    )


@blueprint.route("/warden/client-signal", methods=["POST"])
def client_signal():
    """warden.js reports in-page automation marks (navigator.webdriver, Selenium / Playwright /
    Puppeteer globals). They exist even when the tool drives a real browser with a normal
    User-Agent."""
    if not authed() or is_admin() or not settings.enabled("client_activity"):
        return jsonify({"success": True})
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict) or not isinstance(body.get("signals", []), list):
        return jsonify({"success": False, "message": "Expected a list of signals."}), 400
    signals = [s[:40] for s in body.get("signals", [])[:6] if isinstance(s, str)]
    if not signals:
        return jsonify({"success": True})
    user = get_current_user()
    if cache.add(f"warden:client:{user.id}:webdriver", 1, timeout=SAMPLE_WINDOW):
        page = str(body.get("page") or "").split("?", 1)[0]
        _record(
            user,
            "automation",
            "browser automation: " + ", ".join(signals),
            method="JS",
            path=page or "-",
        )
    return jsonify({"success": True})
