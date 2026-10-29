"""Regional brackets: every account is placed in the region bracket (e.g. "MENA") when all of its
members have a nationality from the region list, and in the outside bracket otherwise. Off by
default.

Placement runs at startup and after requests that can change accounts or teams, with one grouped
query. A bracket an admin sets by hand (Admin -> Teams/Users -> edit) is kept until it is reset
on the Warden page.
"""

import json
import re

import sqlalchemy as sa
from flask import g, request

from CTFd.cache import clear_standings, clear_team_session, clear_user_session
from CTFd.models import Brackets, Teams, Users, db
from CTFd.utils import get_config, set_config
from CTFd.utils.user import is_admin

from .common import SAFE_METHODS, teams_mode
from .settings import region_settings

OVERRIDES_KEY = "warden_bracket_overrides"
# Requests that can create users or teams, change membership or change a nationality.
ACCOUNT_CHANGE_PREFIXES = (
    "/register",
    "/oauth",
    "/redirect",
    "/setup",
    "/settings",
    "/teams",
    "/admin",
    "/api/v1/users",
    "/api/v1/teams",
)
ACCOUNT_PATCH = re.compile(r"^/api/v1/(teams|users)/(\d+)$")


def _type():
    return "teams" if teams_mode() else "users"


def _model():
    return Teams if teams_mode() else Users


def _prefix():
    return "t" if teams_mode() else "u"


def _bracket(name):
    return Brackets.query.filter_by(name=name, type=_type()).order_by(Brackets.id).first()


def brackets():
    region = region_settings()
    return _bracket(region["name"]), _bracket(region["outside_name"]), region


def ensure_brackets(old_names=None):
    """Create the two brackets, or rename them when the names changed on the admin page."""
    region = region_settings()
    wanted = {
        region["name"]: "All members have a nationality from the region",
        region["outside_name"]: "At least one member is from outside the region or has no nationality",
    }
    for old, new in zip(old_names or (), wanted):
        if old != new and _bracket(new) is None and _bracket(old) is not None:
            _bracket(old).name = new
    for name, description in wanted.items():
        bracket = _bracket(name)
        if bracket is None:
            db.session.add(Brackets(name=name, description=description, type=_type()))
        else:
            bracket.description = description
    db.session.commit()
    _merge_duplicates(wanted)
    classify_all()


def _merge_duplicates(names):
    """Several workers starting at once on a fresh database can each create a bracket; keep one."""
    model = _model()
    for name in names:
        rows = Brackets.query.filter_by(name=name, type=_type()).order_by(Brackets.id).all()
        for extra in rows[1:]:
            model.query.filter_by(bracket_id=extra.id).update({"bracket_id": rows[0].id})
            db.session.delete(extra)
    db.session.commit()


def overrides():
    """{"t<team_id>" | "u<user_id>": bracket_id or None} set by admins by hand."""
    try:
        data = json.loads(get_config(OVERRIDES_KEY) or "{}")
        return data if isinstance(data, dict) else {}
    except (TypeError, ValueError):
        return {}


def save_overrides(data):
    set_config(OVERRIDES_KEY, json.dumps(data, sort_keys=True))


def _inside_map(codes):
    """{account_id: True when every member has a nationality from the region}."""
    inside = sa.case((sa.func.upper(Users.country).in_(sorted(codes)), 1), else_=0)
    if teams_mode():
        rows = (
            db.session.query(Users.team_id, sa.func.count(Users.id), sa.func.sum(inside))
            .filter(Users.team_id.isnot(None))
            .group_by(Users.team_id)
            .all()
        )
        return {
            team_id: bool(total) and int(n or 0) == total for team_id, total, n in rows
        }
    rows = db.session.query(Users.id, Users.country).filter(Users.type == "user").all()
    return {user_id: (country or "").upper() in codes for user_id, country in rows}


def auto_bracket_id(account_id):
    inside, outside, region = brackets()
    if inside is None or outside is None:
        return None
    return inside.id if _inside_map(region["codes"]).get(account_id) else outside.id


def classify_all():
    inside, outside, region = brackets()
    if inside is None or outside is None:
        return
    model, prefix = _model(), _prefix()
    inside_map = _inside_map(region["codes"])
    pinned = overrides()
    query = db.session.query(model.id, model.bracket_id)
    if model is Users:
        query = query.filter(Users.type == "user")
    changed = []
    for account_id, current in query.all():
        if f"{prefix}{account_id}" in pinned:
            continue
        wanted = inside.id if inside_map.get(account_id) else outside.id
        if current != wanted:
            changed.append((account_id, wanted))
    if not changed:
        return
    for account_id, wanted in changed:
        model.query.filter_by(id=account_id).update({"bracket_id": wanted})
    db.session.commit()
    for account_id, _ in changed:
        if model is Teams:
            clear_team_session(team_id=account_id)
        else:
            clear_user_session(user_id=account_id)
    clear_standings()


def _remember_admin_bracket(kind, account_id, bracket_id):
    """Keep a bracket an admin chose by hand; choosing the automatic one returns the account to
    automatic placement."""
    if (kind == "teams") != teams_mode():
        return
    pinned = overrides()
    key = f"{_prefix()}{account_id}"
    if bracket_id in ("", None):
        bracket_id = None
    else:
        try:
            bracket_id = int(bracket_id)
        except (TypeError, ValueError):
            return
    if bracket_id is not None and bracket_id == auto_bracket_id(account_id):
        pinned.pop(key, None)
    else:
        pinned[key] = bracket_id
    save_overrides(pinned)


def before_request(path):
    if request.method == "PATCH" and is_admin():
        match = ACCOUNT_PATCH.match(path)
        body = request.get_json(silent=True)
        if match and isinstance(body, dict) and "bracket_id" in body:
            g.warden_bracket = (match.group(1), int(match.group(2)), body.get("bracket_id"))


def after_request(path, response):
    if request.method in SAFE_METHODS or response.status_code >= 400:
        return
    manual = g.pop("warden_bracket", None)
    if not (manual or path.startswith(ACCOUNT_CHANGE_PREFIXES)):
        return
    # Never turn the player's (already successful) request into an error page.
    try:
        if manual:
            _remember_admin_bracket(*manual)
        classify_all()
    except Exception:
        db.session.rollback()
