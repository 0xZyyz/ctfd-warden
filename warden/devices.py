"""Shared devices: a random device ID cookie per browser, recorded for every account it signs in as.

A device used by accounts on different teams is a strong account-sharing signal that a VPN does not
hide. Players can clear cookies, so it is evidence to look into, not proof.
"""

import re
import secrets
from datetime import datetime

from flask import request

from CTFd.cache import cache
from CTFd.models import db
from CTFd.utils.user import get_ip

from .models import DeviceSession

COOKIE = "warden_device"
TOUCH_WINDOW = 600
STATIC_ENDPOINTS = ("views.themes", "views.themes_beta", "views.files")


def device_id():
    value = request.cookies.get(COOKIE, "")
    return value if re.fullmatch(r"[0-9a-f]{32}", value) else None


def before_request(user):
    current = device_id()
    if not current:
        return
    if not cache.add(f"warden:device:{current}:{user.id}", 1, timeout=TOUCH_WINDOW):
        return
    try:
        now = datetime.utcnow()
        ua = (request.headers.get("User-Agent") or "")[:255]
        row = DeviceSession.query.filter_by(device_id=current, user_id=user.id).first()
        if row is None:
            db.session.add(
                DeviceSession(
                    device_id=current,
                    user_id=user.id,
                    user_agent=ua,
                    ip=get_ip(),
                    first_seen=now,
                    last_seen=now,
                )
            )
        else:
            row.last_seen, row.user_agent, row.ip = now, ua, get_ip()
        db.session.commit()
    except Exception:
        db.session.rollback()


def after_request(response):
    if device_id() is not None or request.endpoint in STATIC_ENDPOINTS:
        return
    response.set_cookie(
        COOKIE,
        secrets.token_hex(16),
        max_age=365 * 86400,
        httponly=True,
        secure=request.is_secure,
        samesite="Lax",
    )
