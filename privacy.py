import re

from flask import abort, jsonify, request

from CTFd.utils.user import authed, get_current_user, is_admin

from .common import SAFE_METHODS, teams_mode

ADMIN_ONLY_LISTS = {"/users", "/api/v1/users"}
ADMIN_ONLY_USER_PAGES = re.compile(r"^/(users|api/v1/users)/\d+(/.*)?$")
TEAM_DETAIL = re.compile(r"/api/v1/teams/(\d+)(?:/(solves|awards))?")
SCOREBOARD_TOP = re.compile(r"/api/v1/scoreboard/top/\d+")
HIDDEN_FIELDS = ("members", "captain_id", "country", "user", "user_id")


def before_request(path):
    if is_admin():
        return
    stripped = path.rstrip("/")
    if stripped == "/api/v1/teams" and (
        "country" in request.args or request.args.get("field") == "country"
    ):
        abort(403)
    if request.method in SAFE_METHODS and (
        stripped in ADMIN_ONLY_LISTS or ADMIN_ONLY_USER_PAGES.match(path)
    ):
        abort(404)


def _hide(item):
    if isinstance(item, dict):
        for key in HIDDEN_FIELDS:
            item.pop(key, None)


def after_request(path, response):
    path = path.rstrip("/")
    if (
        request.method not in SAFE_METHODS
        or not response.is_json
        or response.status_code != 200
        or is_admin()
    ):
        return
    team_match = TEAM_DETAIL.fullmatch(path)
    team_list = path == "/api/v1/teams"
    scoreboard = teams_mode() and (
        path == "/api/v1/scoreboard" or SCOREBOARD_TOP.fullmatch(path)
    )
    if not (team_match or team_list or scoreboard):
        return
    user = get_current_user() if authed() else None
    own_team = user.team_id if user else None
    body = response.get_json()
    data = body.get("data")

    if team_match:
        if int(team_match[1]) != own_team:
            for item in data if isinstance(data, list) else [data]:
                _hide(item)
    elif isinstance(data, (dict, list)):
        for item in data.values() if isinstance(data, dict) else data:
            if not isinstance(item, dict):
                continue
            if item.get("account_id", item.get("id")) != own_team:
                _hide(item)
                for solve in item.get("solves", []):
                    _hide(solve)
    response.set_data(jsonify(body).get_data())
    response.headers["Cache-Control"] = "private, no-store"
    response.vary.add("Cookie")
